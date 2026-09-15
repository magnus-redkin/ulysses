import asyncio
from datetime import datetime, timezone
import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services.hiddify_client import HiddifyProvisioner

from .db_utils import find_user_by_identifier

import json
from app.services.activation_manager import get_or_create_user
from app.services.free_subscription import create_free_subscription

console = Console()

def async_cmd(f):
    import functools
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

@click.group(name="user")
def user():
    """Управление пользователями биллинга Ulysses VPN."""
    pass

user.get_usage = lambda ctx: "uadmin user [ОПЦИИ] КОМАНДА [ARGS]..."


@user.command(name="create")
@click.option("--tg-id", type=int, required=True)
@click.option("--username", type=str, required=True)
@async_cmd
async def user_create(tg_id, username):
    """Создать пользователя и активировать ему бесплатный тариф sub_free."""
    clean_username = username.lstrip("@").strip()
    console.print(f"[yellow]⏳ Создание пользователя для TG ID {tg_id}...[/yellow]")

    async with AsyncSessionLocal() as session:
        try:
            user = await get_or_create_user(session, tg_user_id=tg_id)

            sub_check = await session.execute(
                text("SELECT id FROM subscriptions WHERE user_id = :uid LIMIT 1"),
                {"uid": user["user_id"]}
            )
            if sub_check.fetchone():
                console.print(f"[red]❌ Пользователь с TG ID {tg_id} уже существует и имеет подписку![/red]")
                return

            result = await create_free_subscription(session, user)

            domain = "ulysses.best"
            subscription_link = f"https://{domain}/subscription/{user['hiddify_uuid']}/#Ulysses"
            console.print(f"\n[bold green]🎉 Пользователь создан![/bold green]")
            console.print(f"👤 TG ID: [cyan]{tg_id}[/cyan] | Username: [cyan]@{clean_username}[/cyan]")
            console.print(f"🔑 UUID: [yellow]{user['hiddify_uuid']}[/yellow]")
            console.print(f"🔗 Ссылка: [bold magenta]{subscription_link}[/bold magenta]\n")
        except Exception as err:
            console.print(f"[red]❌ Ошибка: {err}[/red]")


@user.command(name="list")
@async_cmd
async def user_list():
    """Показать список всех пользователей биллинга."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT id, tg_user_id, tg_username, email, hiddify_uuid, created_at FROM users ORDER BY id ASC")
        )
        users = res.fetchall()

        if not users:
            console.print("[yellow]⚠️ База пуста[/yellow]")
            return

        table = Table(title="👥 Пользователи Ulysses")
        table.add_column("ID", style="dim")
        table.add_column("TG ID", style="cyan")
        table.add_column("Username", style="green")
        table.add_column("Email", style="blue")
        table.add_column("UUID", style="yellow")
        table.add_column("Создан", style="magenta")

        for row in users:
            table.add_row(
                str(row[0]), str(row[1]), f"@{row[2]}" if row[2] else "-",
                row[3] or "-", str(row[4]),
                row[5].strftime("%Y-%m-%d %H:%M") if row[5] else "-"
            )
        console.print(table)


@user.command(name="delete")
@click.argument("identifier")
@async_cmd
async def user_delete(identifier):
    """Удалить пользователя из БД и со всех HFM-нод."""
    async with AsyncSessionLocal() as session:
        console.print(f"[yellow]⏳ Поиск пользователя '{identifier}'...[/yellow]")
        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print(f"[red]❌ Пользователь не найден[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row
        hiddify_uuid_str = str(hiddify_uuid).strip() if hiddify_uuid else ""

        if hiddify_uuid_str and hiddify_uuid_str not in ("", "None", "-"):
            from app.services.node_manager import node_manager
            nodes = node_manager.get_hfm_nodes()
            if not nodes:
                console.print("[red]Нет нод в конфигурации[/red]")
                return

            delete_success = True
            provisioner = HiddifyProvisioner()
            result = await provisioner.delete_user(uuid=hiddify_uuid_str)

            if result.get("not_found"):
                console.print(f"[yellow]ℹ️ Пользователь не найден на нодах, считаем удалённым.[/yellow]")
            elif not result["success"]:
                console.print(f"[red]❌ Не удалось удалить на нодах[/red]")
                delete_success = False
            else:
                console.print(f"[green]✅ Удалён на всех нодах[/green]")

            if not delete_success:
                console.print("[red]⚠️ Удаление не на всех нодах. Локальная запись НЕ удалена.[/red]")
                return

        try:
            await session.execute(text("DELETE FROM users WHERE id = :db_id"), {"db_id": db_id})
            await session.commit()
            console.print(f"[bold green]✅ Пользователь {identifier} удалён из БД[/bold green]")
        except Exception as e:
            await session.rollback()
            console.print(f"[red]❌ Ошибка удаления из БД: {e}[/red]")


@user.command(name="link")
@click.argument("identifier")
@async_cmd
async def user_link(identifier):
    """Показать ссылку подписки пользователя."""
    async with AsyncSessionLocal() as session:
        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print(f"[red]❌ Пользователь не найден[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row
        if not hiddify_uuid or str(hiddify_uuid).strip() in ("None", "-"):
            console.print(f"[red]❌ У пользователя ID {db_id} отсутствует UUID[/red]")
            return

        base_domain = "ulysses.best"
        client_sub_url = f"https://{base_domain}/subscription/{hiddify_uuid}/#Ulysses"

        console.print(f"\n[bold green]🔑 Ссылка подписки[/bold green]")
        if tg_username:
            console.print(f"👤 @{tg_username} (TG ID: {tg_user_id})", end="")
        else:
            console.print(f"👤 email/no_username", end="")
        console.print(f" (DB ID: {db_id})")
        console.print(f"🆔 UUID: [yellow]{hiddify_uuid}[/yellow]")
        console.print(f"🔗 [bold magenta]{client_sub_url}[/bold magenta]\n")


@user.command(name="json")
@click.argument("identifier")
@async_cmd
async def user_json(identifier):
    """Сгенерировать объединённый sing-box JSON со всех нод для пользователя."""
    async with AsyncSessionLocal() as session:
        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print(f"[red]❌ Пользователь не найден[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row
        if not hiddify_uuid or str(hiddify_uuid).strip() in ("None", "-"):
            console.print("[red]❌ UUID отсутствует[/red]")
            return

        # Статус подписки
        sub_result = await session.execute(
            text("SELECT status, expires_at FROM subscriptions WHERE user_id = :uid ORDER BY expires_at DESC LIMIT 1"),
            {"uid": db_id}
        )
        sub_row = sub_result.fetchone()
        status = sub_row[0] if sub_row else "unknown"
        expires_at = sub_row[1] if sub_row else None
        expires_str = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "infinity"

        console.print(f"\n📋 Профиль {identifier}")
        if tg_username:
            console.print(f"   • TG: @{tg_username} (ID: {tg_user_id})")
        else:
            console.print(f"   • DB ID: {db_id}")
        status_color = "green" if status == "active" else "yellow" if status == "provisioning" else "red"
        console.print(f"   • Статус: [{status_color}]{status}[/]")
        console.print(f"   • Истекает: [magenta]{expires_str}[/magenta]")
        console.print(f"   • UUID: [cyan]{hiddify_uuid}[/cyan]\n")

        try:
            from app.services.subscription_aggregator import aggregate_subscriptions
            json_config = await aggregate_subscriptions(str(hiddify_uuid))

            console.print("📄 ОБЪЕДИНЁННЫЙ SING-BOX JSON (Все ноды):")
            console.print("─" * 100)
            if json_config:
                raw = json.dumps(json_config, ensure_ascii=False, indent=2)
                from rich.syntax import Syntax
                syntax = Syntax(raw, "json", theme="monokai_", line_numbers=True)
                console.print(syntax)
            else:
                console.print("[yellow]⚠️ Пустой конфиг[/yellow]")
            console.print("─" * 100 + "\n")
        except Exception as e:
            console.print(f"[bold red]❌ Ошибка генерации: {e}[/bold red]")


@user.command(name="sub")
@click.argument("identifier")
@click.option("--history", is_flag=True, help="Показать историю подписок и платежей.")
@click.option("--all", "show_all", is_flag=True, help="Без лимита (подразумевает --history).")
@click.option("--limit", default=20, type=int, help="Лимит записей истории (по умолчанию 20).")
@async_cmd
async def user_subscription_status(identifier, history, show_all, limit):
    """Подписки и платежи пользователя. С --history — история, с --all — без лимита."""
    if show_all:
        history = True
        limit = None

    async with AsyncSessionLocal() as session:
        console.print(f"[yellow]⏳ Поиск подписок для '{identifier}'...[/yellow]")
        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print("[red]❌ Пользователь не найден[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row
        hiddify_uuid_str = str(hiddify_uuid).strip() if hiddify_uuid else ""

        # Проверка на нодах (как было)
        if hiddify_uuid_str and hiddify_uuid_str not in ("None", "-"):
            from app.services.node_manager import node_manager
            nodes = node_manager.get_hfm_nodes()
            found_on_nodes = []
            provisioner = HiddifyProvisioner()
            for node in nodes:
                try:
                    exists = await provisioner.check_user_exists(hiddify_uuid_str)
                    if exists:
                        found_on_nodes.append(node.get("id", node.get("name", "unknown")))
                except Exception as e:
                    console.print(f"[amber]⚠️ Ошибка проверки на ноде {node.get('id', node.get('name'))}: {e}[/amber]")

            if found_on_nodes:
                hfm_status_str = f"[green]🟢 Найден на нодах: {', '.join(found_on_nodes)}[/green]"
            else:
                hfm_status_str = "[yellow]⚪ Отсутствует на всех нодах[/yellow]"
        else:
            hfm_status_str = "[red]Нет UUID[/red]"

        # --- Основной профиль ---
        console.print(f"\n👤 Профиль ID {db_id}")
        if tg_username:
            console.print(f"   • Telegram: @{tg_username} (ID: {tg_user_id})")
        else:
            console.print(f"   • email_only")
        console.print(f"   • UUID: [yellow]{hiddify_uuid_str}[/yellow]")
        console.print(f"   • Статус на Ноде: {hfm_status_str}\n")

        # --- Активная подписка (как было) ---
        sql_active = """
            SELECT id, tariff_slug, status, node_id, starts_at, expires_at,
                   provisioning_attempts, provisioning_error
            FROM subscriptions
            WHERE user_id = :uid AND status = 'active'
            ORDER BY expires_at DESC NULLS FIRST, id DESC
        """
        res_subs = await session.execute(text(sql_active), {"uid": db_id})
        subscriptions = res_subs.fetchall()

        if not subscriptions:
            console.print("[yellow]ℹ️ Активных подписок нет[/yellow]")
        else:
            table = Table(title=f"📅 Активные подписки ({len(subscriptions)})")
            table.add_column("Sub ID", style="dim")
            table.add_column("Тариф", style="blue")
            table.add_column("Статус")
            table.add_column("Нода", style="magenta")
            table.add_column("Начало", justify="center")
            table.add_column("Истекает", justify="center")
            table.add_column("Ошибки", style="red")

            for sub in subscriptions:
                sub_id, tariff_slug, status, node_id, starts_at, expires_at, attempts, error = sub
                status_formatted = {
                    "active": "[green]🟢 active[/green]",
                    "provisioning": "[yellow]⏳ provisioning[/yellow]",
                    "expired": "[red]🔴 expired[/red]",
                    "cancelled": "[dim]⚪ cancelled[/dim]"
                }.get(status, f"[italic]{status}[/italic]")

                starts_str = starts_at.strftime("%Y-%m-%d %H:%M") if starts_at else "-"
                expires_str = expires_at.strftime("%Y-%m-%d %H:%M") if expires_at else "[blue]Infinity[/blue]"
                if status == "active" and expires_at and expires_at < datetime.now(timezone.utc):
                    status_formatted = "[red]🚨 active (ПРОТУХЛА)[/red]"

                error_info = "-"
                if error or attempts:
                    error_info = f"[{attempts} поп.] {error[:25] if error else 'API error'}"

                table.add_row(str(sub_id), tariff_slug, status_formatted, node_id, starts_str, expires_str, error_info)

            console.print(table)

        # --- История ---
        if not history:
            console.print("")
            return

        limit_sql = "" if limit is None else f"LIMIT {int(limit)}"

        # Все подписки (включая активные)
        sql_all_subs = f"""
            SELECT id, tariff_slug, status, node_id, starts_at, expires_at,
                   provisioning_attempts, provisioning_error
            FROM subscriptions
            WHERE user_id = :uid
            ORDER BY created_at DESC NULLS LAST, id DESC
            {limit_sql}
        """
        all_subs = (await session.execute(text(sql_all_subs), {"uid": db_id})).fetchall()

        console.print(f"\n📅 История подписок ({len(all_subs)}):")
        if all_subs:
            t_subs = Table()
            t_subs.add_column("Sub ID", style="dim")
            t_subs.add_column("Тариф", style="blue")
            t_subs.add_column("Статус")
            t_subs.add_column("Нода", style="magenta")
            t_subs.add_column("Начало", justify="center")
            t_subs.add_column("Истекает", justify="center")

            for sub in all_subs:
                sub_id, tariff_slug, status, node_id, starts_at, expires_at, _, _ = sub
                status_formatted = {
                    "active": "[green]🟢 active[/green]",
                    "provisioning": "[yellow]⏳ provisioning[/yellow]",
                    "provisioning_failed": "[red]❌ provisioning_failed[/red]",
                    "expired": "[red]🔴 expired[/red]",
                    "cancelled": "[dim]⚪ cancelled[/dim]",
                }.get(status, f"[italic]{status}[/italic]")

                starts_str = starts_at.strftime("%Y-%m-%d %H:%M") if starts_at else "-"
                expires_str = expires_at.strftime("%Y-%m-%d %H:%M") if expires_at else "—"
                t_subs.add_row(
                    str(sub_id), tariff_slug, status_formatted, node_id or "-",
                    starts_str, expires_str,
                )
            console.print(t_subs)
        else:
            console.print("[dim](пусто)[/dim]")

        # Все платежи
        sql_pays = f"""
            SELECT id, status, amount, currency, tariff_slug, created_at
            FROM payment_attempts
            WHERE user_id = :uid
            ORDER BY created_at DESC NULLS LAST
            {limit_sql}
        """
        all_pays = (await session.execute(text(sql_pays), {"uid": db_id})).fetchall()

        console.print(f"\n💳 История платежей ({len(all_pays)}):")
        if all_pays:
            t_pays = Table()
            t_pays.add_column("ID (short)", style="dim")
            t_pays.add_column("Статус")
            t_pays.add_column("Оплачено", justify="right")
            t_pays.add_column("Тариф", style="blue")
            t_pays.add_column("Создан", justify="center")

            for p in all_pays:
                pid, st, amt, cur, slug, created = p
                st_color = {
                    "success": "[green]success[/green]",
                    "pending": "[yellow]pending[/yellow]",
                    "processing": "[cyan]processing[/cyan]",
                    "cancelled": "[dim]cancelled[/dim]",
                    "failed": "[red]failed[/red]",
                }.get(st, f"[italic]{st}[/italic]")

                t_pays.add_row(
                    str(pid)[:8],
                    st_color,
                    f"{amt:.2f} {cur}",
                    slug,
                    created.strftime("%Y-%m-%d %H:%M") if created else "-",
                )
            console.print(t_pays)
            console.print(
                "\n[dim]ℹ️ Детали конкретного платежа: "
                "uadmin pay show <полный-uuid>[/dim]"
            )
        else:
            console.print("[dim](пусто)[/dim]")

        console.print("")

@user.command(name="rf-sync")
@async_cmd
async def user_rf_sync():
    """Полный ре-синк UUID: все активные подписки → RF-нода."""
    from app.services.rf_node_client import sync_users
    from app.config import settings

    if not getattr(settings, "RF_NODE_ENABLED", False):
        console.print("[yellow]⚠️ RF_NODE_ENABLED=false, синк пропущен[/yellow]")
        return

    async with AsyncSessionLocal() as session:
        res = await session.execute(text("""
            SELECT DISTINCT u.hiddify_uuid
            FROM subscriptions s
            JOIN users u ON u.id = s.user_id
            WHERE s.status = 'active'
              AND s.expires_at > NOW()
              AND u.hiddify_uuid IS NOT NULL
        """))
        uuids = [str(row[0]) for row in res.fetchall()]

    console.print(f"[yellow]⏳ Синхронизация {len(uuids)} UUID → RF-нода...[/yellow]")
    ok = await sync_users(uuids)
    if ok:
        console.print(f"[green]✅ Синхронизировано: {len(uuids)} UUID[/green]")
    else:
        console.print("[red]❌ Не удалось синхронизировать (см. логи)[/red]")
