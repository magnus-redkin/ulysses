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
            for node in nodes:
                api_url = f"https://{node.get('domain')}/{node.get('admin_path')}"
                provisioner = HiddifyProvisioner(api_url=api_url, api_key=node.get('api_key'))
                result = await provisioner.delete_user(uuid=hiddify_uuid_str)
                if result.get("not_found"):
                    console.print(f"[yellow]ℹ️ Пользователь не найден на ноде {node.get('id')}, считаем удалённым.[/yellow]")
                    continue
                if not result["success"]:
                    console.print(f"[red]❌ Не удалось удалить на ноде {node.get('id')}[/red]")
                    delete_success = False
                else:
                    console.print(f"[green]✅ Удалён на ноде {node.get('id')}[/green]")

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
@async_cmd
async def user_subscription_status(identifier):
    async with AsyncSessionLocal() as session:
        console.print(f"[yellow]⏳ Поиск подписок для '{identifier}'...[/yellow]")
        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print("[red]❌ Пользователь не найден[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row
        hiddify_uuid_str = str(hiddify_uuid).strip() if hiddify_uuid else ""

        if hiddify_uuid_str and hiddify_uuid_str not in ("None", "-"):
            from app.services.node_manager import node_manager
            nodes = node_manager.get_hfm_nodes()
            found_on_nodes = []
            for node in nodes:
                api_url = f"https://{node.get('domain')}/{node.get('admin_path')}"
                provisioner = HiddifyProvisioner(api_url=api_url, api_key=node.get('api_key'))
                try:
                    exists = await provisioner.check_user_exists(hiddify_uuid_str)
                    if exists:
                        found_on_nodes.append(node.get("id"))
                except Exception as e:
                    console.print(f"[amber]⚠️ Ошибка проверки на ноде {node.get('id')}: {e}[/amber]")

            if found_on_nodes:
                hfm_status_str = f"[green]🟢 Найден на нодах: {', '.join(found_on_nodes)}[/green]"
            else:
                hfm_status_str = "[yellow]⚪ Отсутствует на всех нодах[/yellow]"
        else:
            hfm_status_str = "[red]Нет UUID[/red]"

        sql_subs = """
            SELECT id, tariff_slug, status, node_id, starts_at, expires_at, provisioning_attempts, provisioning_error
            FROM subscriptions
            WHERE user_id = :uid
            ORDER BY expires_at DESC NULLS FIRST, id DESC
        """
        res_subs = await session.execute(text(sql_subs), {"uid": db_id})
        subscriptions = res_subs.fetchall()

        console.print(f"\n👤 Профиль ID {db_id}")
        if tg_username:
            console.print(f"   • Telegram: @{tg_username} (ID: {tg_user_id})")
        else:
            console.print(f"   • email_only")
        console.print(f"   • UUID: [yellow]{hiddify_uuid_str}[/yellow]")
        console.print(f"   • Статус на Ноде: {hfm_status_str}\n")

        if not subscriptions:
            console.print("[yellow]ℹ️ Нет подписок[/yellow]")
            return

        table = Table(title=f"📅 Подписки ({len(subscriptions)})")
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
        console.print("")
