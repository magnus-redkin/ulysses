import asyncio
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.config import settings  # Импортируем конфиг бэкенда

console = Console()

@click.group()
def vpn():
    """Управление VPN-ключами и интеграцией с нодами (Hiddify)"""
    pass


@vpn.command(name="link")
@click.option("--id", type=int, help="Поиск по локальному ID пользователя")
@click.option("--email", help="Поиск по Email пользователя")
@click.option("--tg-id", type=int, help="Поиск по Telegram ID")
def vpn_link(id, email, tg_id):
    """Сгенерировать и показать ссылку доступа (конфиг) для пользователя"""
    if not id and not email and not tg_id:
        raise click.UsageError("❌ Ошибка: укажите хотя бы один фильтр (--id, --email или --tg-id)")

    async def _link():
        async with AsyncSessionLocal() as session:
            sql = "SELECT id, tg_user_id, email, hiddify_uuid FROM users WHERE "
            params = {}

            if id:
                sql += "id = :id"
                params["id"] = id
            elif email:
                sql += "email = :email"
                params["email"] = email
            elif tg_id:
                sql += "tg_user_id = :tg_id"
                params["tg_id"] = tg_id

            result = await session.execute(text(sql), params)
            user_row = result.fetchone()

            if not user_row:
                console.print("[red]❌ Пользователь по указанным критериям не найден.[/red]")
                return

            u_id, u_tg_id, u_email, u_uuid = user_row

            if not u_uuid:
                console.print("[yellow]⚠️ У этого пользователя еще не сгенерирован Hiddify UUID.[/yellow]")
                return

            # Безопасно вытягиваем домен из конфига бэкенда или берем IP из HIDDIFY_API_URL
            domain = getattr(settings, "HIDDIFY_DOMAIN", None)
            if not domain and hasattr(settings, "HIDDIFY_API_URL"):
                # Парсим IP-адрес из урла 'http://193.188.22.128/X6CbExbUw2/...'
                url_parts = settings.HIDDIFY_API_URL.split("/")
                if len(url_parts) > 2:
                    domain = url_parts[2]

            domain = domain or "193.188.22.128"

            # Формируем подписку с ПРОБЕЛОМ после двоеточия, чтобы терминал/браузер не прятал текст
            sub_link = f"https://{domain}/X6CbExbUw2/sub/{u_uuid}/"

            identity = u_email if u_email else f"Telegram: {u_tg_id}"

            card_content = (
                f"[cyan]Пользователь ID:[/cyan] {u_id}\n"
                f"[cyan]Идентификатор:[/cyan] {identity}\n"
                f"[cyan]Hiddify UUID :[/cyan] [green]{u_uuid}[/green]\n\n"
                f"[bold yellow]🔗 Ссылка для импорта в приложение (Sing-box/V2ray):[/bold yellow]\n"
                f"[underline green]{sub_link}[/underline green]\n\n"
            )

            console.print(Panel(card_content, title="🔑 Ulysses VPN Ключ Доступа", border_style="yellow", expand=False))

    asyncio.run(_link())


@vpn.command(name="status")
def vpn_status():
    """Проверить статус настройки интеграции с Hiddify API"""
    table = Table(title="📡 Статус настроек интеграции VPN")
    table.add_column("Параметр API", style="cyan")
    table.add_column("Значение / Статус", style="green")

    url = getattr(settings, "HIDDIFY_API_URL", "Не задан")
    key = getattr(settings, "HIDDIFY_API_KEY", None)
    key_status = "✅ Установлен" if key else "❌ Отсутствует"

    table.add_row("🔗 Hiddify URL", str(url))
    table.add_row("🔑 Hiddify API Key", key_status)

    console.print(table)
