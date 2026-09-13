# cli/sync.py

"""
Синхронизация пользователей brain → HFM-ноды.

Использование:
    uadmin sync                  — компактная сводка (изменения не вносятся)
    uadmin sync --apply          — выполнить синхронизацию (создать отсутствующих)
    uadmin sync --user <id>      — только один пользователь (UUID/email/tg_id), сразу создаётся
"""

import asyncio
import click
import httpx
from rich.console import Console
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.node_manager import node_manager

console = Console()


def async_cmd(f):
    import functools
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


# ---------- вспомогательное ----------

async def _fetch_node_user_uuids(node: dict) -> set[str] | None:
    """Возвращает множество UUID пользователей на ноде, или None при ошибке."""
    url = f"https://{node['domain']}/{node['proxy_path_admin']}/api/v2/admin/user/"
    headers = {"Hiddify-API-Key": node.get("admin_uuid", "")}
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                console.print(f"[red]  ❌ {node['id']}: HTTP {r.status_code}[/red]")
                return None
            data = r.json()
            if isinstance(data, dict):
                data = data.get("users", data.get("data", []))
            return {str(u.get("uuid", "")).lower() for u in data if u.get("uuid")}
    except Exception as e:
        console.print(f"[red]  ❌ {node['id']}: {e}[/red]")
        return None


async def _create_user_on_node(node: dict, uuid: str, name: str, package_days: int = 3, usage_limit_gb: int = 500) -> bool:
    url = f"https://{node['domain']}/{node['proxy_path_admin']}/api/v2/admin/user/"
    headers = {
        "Hiddify-API-Key": node.get("admin_uuid", ""),
        "Content-Type": "application/json",
    }
    payload = {
        "uuid": str(uuid),
        "name": str(name),
        "usage_limit_GB": usage_limit_gb,
        "package_days": package_days,
        "mode": "no_reset",
        "enable": True,
        "current_usage_GB": 0,
        "comment": "",
        "telegram_id": None,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code in (200, 201):
                return True
            if r.status_code == 400 and "exists" in r.text.lower():
                return True
            console.print(f"[red]  ❌ {node['id']} create {uuid}: HTTP {r.status_code} {r.text[:150]}[/red]")
            return False
    except Exception as e:
        console.print(f"[red]  ❌ {node['id']} create {uuid}: {e}[/red]")
        return False


async def _brain_active_uuids() -> dict[str, dict]:
    """Возвращает {uuid: {"name": ..., "user_id": ...}} только для активных подписок."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(text("""
            SELECT DISTINCT u.hiddify_uuid, u.email, u.tg_user_id, u.id
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE s.status = 'active'
              AND (s.expires_at IS NULL OR s.expires_at > NOW())
              AND u.hiddify_uuid IS NOT NULL
        """))
        out = {}
        for row in res.fetchall():
            u = str(row[0]).lower()
            name = (row[1] or f"user_{row[3]}").split("@")[0][:30]
            out[u] = {"name": name, "user_id": row[3]}
        return out


# ---------- сама команда ----------

@click.command(name="sync")
@click.option("--apply", is_flag=True, help="Выполнить синхронизацию (создать отсутствующих)")
@click.option("--user", default=None, help="Только один пользователь (UUID/email/tg_id), создаётся сразу")
@async_cmd
async def sync(apply: bool, user: str):
    """Синхронизация brain → HFM-ноды.

    По умолчанию только показывает расхождения (компактно).
    С --apply создаёт отсутствующих пользователей на нодах.
    """
    nodes = node_manager.get_active_hfm_nodes()
    if not nodes:
        console.print("[red]❌ Нет активных HFM-нод[/red]")
        return

    # Один пользователь — упрощённый путь
    if user:
        await _sync_single(user, nodes)
        return

    brain = await _brain_active_uuids()
    if not brain:
        console.print("[yellow]⚠️ В brain нет активных подписок[/yellow]")
        return

    # Опрашиваем ноды параллельно
    tasks = [_fetch_node_user_uuids(n) for n in nodes]
    node_sets = await asyncio.gather(*tasks)

    brain_count = len(brain)
    console.print(f"[bold]Ulysses: {brain_count}[/bold]")
    for n, uuids in zip(nodes, node_sets):
        if uuids is None:
            continue
        diff = len(uuids) - brain_count
        sign = f"+{diff}" if diff > 0 else (f"{diff}" if diff < 0 else "0")
        console.print(f"{n['id']}: {len(uuids)}, {sign}")

    if not apply:
        console.print("\n[dim]--apply — создать отсутствующих пользователей на нодах.[/dim]")
        return

    # ---- применяем ----
    console.print("\n[yellow]⏳ Синхронизация...[/yellow]")
    for n, uuids in zip(nodes, node_sets):
        if uuids is None:
            continue
        missing = set(brain.keys()) - uuids
        if not missing:
            console.print(f"[green]✓ {n['id']}: всё на месте[/green]")
            continue
        console.print(f"[yellow]{n['id']}: создать {len(missing)}[/yellow]")
        ok = 0
        for u in missing:
            name = brain[u]["name"]
            if await _create_user_on_node(n, u, name):
                ok += 1
        console.print(f"[green]✓ {n['id']}: создано {ok}/{len(missing)}[/green]")


async def _sync_single(identifier: str, nodes):
    """Создать конкретного пользователя на всех нодах."""
    async with AsyncSessionLocal() as session:
        if "@" in identifier:
            q = text("SELECT id, email, tg_user_id, hiddify_uuid FROM users WHERE email = :v")
        else:
            q = text(
                "SELECT id, email, tg_user_id, hiddify_uuid FROM users "
                "WHERE CAST(hiddify_uuid AS TEXT) = :v OR CAST(tg_user_id AS TEXT) = :v"
            )
        res = await session.execute(q, {"v": identifier})
        row = res.fetchone()

    if not row:
        console.print(f"[red]❌ Пользователь '{identifier}' не найден в brain[/red]")
        return

    _id, email, tg_id, uuid = row
    name = (email or f"user_{_id}").split("@")[0][:30]
    console.print(f"👤 {uuid} — {name}")
    for n in nodes:
        ok = await _create_user_on_node(n, str(uuid), name)
        mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {mark} {n['id']}")


if __name__ == "__main__":
    sync(prog_name="uadmin sync")
