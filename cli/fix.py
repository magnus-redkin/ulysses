# cli/fix.py

import os
import httpx
import click
from rich.console import Console

console = Console()
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("HOST_API_KEY", "")


def _post(path: str, params: dict | None = None, timeout: float = 30.0) -> dict | None:
    """Общий вызов админских эндпоинтов. Возвращает JSON или None при ошибке."""
    try:
        resp = httpx.post(
            f"{BACKEND_API_URL}{path}",
            headers={"X-API-Key": API_KEY},
            params=params or {},
            timeout=timeout,
        )
    except httpx.RequestError as e:
        console.print(f"[red]❌ Ошибка подключения к API: {e}[/red]")
        return None

    if resp.status_code == 200:
        return resp.json()

    console.print(f"[red]❌ API {path}: HTTP {resp.status_code}[/red]")
    if resp.status_code == 401:
        console.print("[dim]Проверьте HOST_API_KEY[/dim]")
    else:
        try:
            detail = resp.json().get("detail")
            if detail:
                console.print(f"[dim]{detail}[/dim]")
        except Exception:
            pass
    return None


@click.group()
def fix():
    """Инструменты автоматического исправления и синхронизации Ulysses VPN."""


@fix.command(name="cleanup-invoices")
def cleanup_invoices():
    """Удалить все просроченные инвойсы (pending старше 24 часов)."""
    data = _post("/api/admin/fix/cleanup-invoices", timeout=15.0)
    if data is not None:
        console.print(
            f"[green]✅ Инвойсы очищены. Удалено: {data.get('deleted_count', 0)}[/green]"
        )


@fix.command(name="process-pending")
@click.option("--limit", default=50, show_default=True, help="Максимальное число подписок для обработки")
def process_pending(limit):
    """Принудительно обработать зависшие подписки."""
    data = _post("/api/admin/fix/process-pending", params={"limit": limit})
    if data is not None:
        console.print(
            f"[green]✅ Обработано подписок: {data.get('processed_count', 0)}[/green]"
        )

@fix.command(name="sync-payments")
@click.option("--age", "min_age_minutes", default=15, show_default=True,
              help="Минимальный возраст платежа в минутах")
@click.option("--limit", default=50, show_default=True,
              help="Максимум платежей к обработке")
def sync_payments(min_age_minutes, limit):
    """Опросить Platega API по зависшим платежам и дотянуть их статусы."""
    data = _post(
        "/api/admin/fix/sync-payments",
        params={"min_age_minutes": min_age_minutes, "limit": limit},
        timeout=120.0,
    )
    if data is None:
        return

    console.print(
        f"[green]✅ Проверено: {data.get('checked', 0)}, "
        f"активировано: {data.get('activated', 0)}, "
        f"отменено: {data.get('cancelled', 0)}, "
        f"failed: {data.get('failed', 0)}, "
        f"пропущено: {data.get('skipped', 0)}, "
        f"ошибок: {data.get('errors', 0)}[/green]"
    )

    details = data.get("details") or []
    if details:
        from rich.table import Table
        t = Table(title="Детали сверки")
        t.add_column("Attempt", style="dim")
        t.add_column("Platega", style="yellow")
        t.add_column("Действие")
        for d in details:
            t.add_row(
                d.get("attempt_id", "")[:8],
                d.get("platega_status", "-"),
                d.get("action", d.get("error", "-"))[:60],
            )
        console.print(t)
