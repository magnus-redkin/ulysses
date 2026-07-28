import asyncio
from datetime import datetime, timedelta, timezone
import click
from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.services.hiddify_client import HiddifyProvisioner

from .db_utils import find_user_by_identifier

import uuid as uuid_lib
import json

console = Console()

def async_cmd(f):
    """Декоратор для автоматического запуска асинхронных CLI команд Click."""
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


# ============================================================
# ➕ КОМАНДА: СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ (CREATE)
# ============================================================
@user.command(name="create")
@click.option("--tg-id", type=int, required=True, help="Telegram ID нового пользователя")
@click.option("--username", type=str, required=True, help="Telegram username (например, @magnus)")
@async_cmd
async def user_create(tg_id, username):
    """
    Создать нового пользователя в системе биллинга 'под ключ'.
    Безопасно генерирует UUID, создает запись в PostgreSQL,
    активирует 3-дневный триал и делает провижн на ноду Hiddify v2.
    """
    from app.services.telegram_bot import send_telegram_message

    clean_username = username.lstrip("@").strip()
    new_uuid = str(uuid_lib.uuid4())
    base_domain = "ulysses.best"
    client_sub_url = f"https://{base_domain}/subscription/{new_uuid}/"

    console.print(f"[yellow]⏳ Запуск каскадного создания пользователя для TG ID {tg_id}...[/yellow]")

    async with AsyncSessionLocal() as session:
        try:
            # 1. Проверяем дубликаты
            res_check = await session.execute(
                text("SELECT id FROM users WHERE tg_user_id = :tg_id"), {"tg_id": tg_id}
            )
            if res_check.fetchone():
                console.print(f"[red]❌ Ошибка: Пользователь с TG ID {tg_id} уже существует в базе![/red]")
                return

            # 2. СЕТЕВОЙ ШАГ (Раньше коммита СУБД): Физически создаем в Hiddify Manager v2
            provisioner = HiddifyProvisioner()
            hiddify_success = await provisioner.create_user(
                uuid=new_uuid,
                name=f"tg_{tg_id}",
                package_days=3,
                usage_limit_gb=500
            )

            if not hiddify_success:
                console.print("[red]❌ Ошибка: Удаленная нода Hiddify v2 отклонила запрос создания. Локальная СУБД не изменялась.[/red]")
                return

            console.print(f"[green]✅ Профиль успешно создан в Hiddify Manager v2 под именем tg_{tg_id}![/green]")

            # 3. ТРАНЗАКЦИЯ А: Создаем аккаунт пользователя в БД
            sql_user = """
                INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, created_at, updated_at)
                VALUES (:tg_id, :username, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
            """
            res_user = await session.execute(text(sql_user), {
                "tg_id": tg_id, "username": clean_username, "uuid": new_uuid
            })
            user_internal_id = res_user.scalar_one()

            # 4. ТРАНЗАКЦИЯ Б: Выдаем бесплатный тариф (Free на 3 дня)
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(days=3)

            sql_sub = """
                INSERT INTO subscriptions (
                    user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at,
                    provisioning_attempts, activated_at
                )
                VALUES (
                    :uid, 'sub_free', 'active', 'main', :starts, :expires, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, :starts
                )
            """
            await session.execute(text(sql_sub), {
                "uid": user_internal_id, "starts": now, "expires": expires_at
            })

            # Фиксируем изменения в СУБД только после успешного ответа от VPN-сервера
            await session.commit()
            console.print(f"[green]💾 СУБД успешно обновлена. Внутренний ID: {user_internal_id}[/green]")

        except Exception as err:
            await session.rollback()
            console.print(f"[red]❌ Критический сбой при создании пользователя: {err}[/red]")
            return

    # 5. ВЫВОД ССЫЛКИ ПОДПИСКИ
    console.print(f"\n[bold green]🎉 Каскад создания пользователя полностью завершен![/bold green]")
    console.print(f"👤 Telegram ID: [cyan]{tg_id}[/cyan] | Юзернейм: [cyan]@{clean_username}[/cyan]")
    console.print(f"🔑 Персональный UUID: [yellow]{new_uuid}[/yellow]")
    console.print(f"🔗 [bold magenta]ФИНАЛЬНАЯ ССЫЛКА ДЛЯ КЛИЕНТА (Hiddify/Sing-box):[/bold magenta]")
    console.print(f"[bold white on magenta] {client_sub_url} [/bold white on magenta]\n")

    # 6. УВЕДОМЛЕНИЕ ПОЛЬЗОВАТЕЛЯ В ТЕЛЕГРАМ-БОТ
    try:
        message_text = (
            f"🎉 **Ваш бесплатный тест-драйв Ulysses VPN активирован на 3 дня!**\n\n"
            f"🔑 Ваша персональная ссылка подписки (Sing-box JSON):\n"
            f"`{client_sub_url}`\n\n"
            f"📥 **Инструкция по подключению:**\n"
            f"1. Полностью скопируйте ссылку выше.\n"
            f"2. Скачайте и откройте приложение **Hiddify Next**.\n"
            f"3. Нажмите 'Добавить профиль' ➔ вставьте скопированную ссылку.\n"
            f"4. Нажмите кнопку подключения.\n\n"
            f"🚀 Приятного и безопасного полета!"
        )

        bot_sent = await send_telegram_message(tg_id=tg_id, text=message_text)
        if bot_sent:
            console.print(f"[green]✉️ Ссылка автоматически отправлена пользователю в Telegram-бот![/green]")
        else:
            console.print(f"[yellow]⚠️ Бот не смог отправить сообщение. Возможно, юзер еще не нажимал /start.[/yellow]")
    except Exception as tg_err:
        console.print(f"[yellow]⚠️ Не удалось отправить сообщение через бота: {tg_err}[/yellow]")


# ============================================================
# 📋 КОМАНДА: ПРОСМОТР СПИСКА ПОЛЬЗОВАТЕЛЕЙ (LIST)
# ============================================================
@user.command(name="list")
@async_cmd
async def user_list():
    """Вывести список всех зарегистрированных пользователей биллинга."""
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            text("SELECT id, tg_user_id, tg_username, email, hiddify_uuid, created_at FROM users ORDER BY id ASC")
        )
        users = res.fetchall()

        if not users:
            console.print("[yellow]⚠️ База данных пользователей пуста.[/yellow]")
            return

        table = Table(title="👥 Зарегистрированные пользователи Ulysses")
        table.add_column("ID", justify="center", style="dim")
        table.add_column("Telegram ID", style="cyan")
        table.add_column("Username", style="green")
        table.add_column("Email", style="blue")
        table.add_column("Hiddify UUID", style="yellow")
        table.add_column("Создан", style="magenta")

        for row in users:
            table.add_row(
                str(row[0]),
                str(row[1]),
                f"@{row[2]}" if row[2] else "-",
                row[3] if row[3] else "-",
                str(row[4]),
                row[5].strftime("%Y-%m-%d %H:%M") if row[5] else "-"
            )
        console.print(table)
# ============================================================
# ❌ КОМАНДА: УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ (DELETE)
# ============================================================
@user.command(name="delete")
@click.argument("identifier")
@async_cmd
async def user_delete(identifier):
    """Удалить пользователя по любому идентификатору (TG ID, email, UUID, DB ID)."""
    async with AsyncSessionLocal() as session:
        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print(f"[red]❌ Пользователь с идентификатором '{identifier}' не найден.[/red]")
            return
        tg_username, tg_user_id, hiddify_uuid, db_id = row

        # Сначала удаляем на HFM
        provisioner = HiddifyProvisioner()
        hiddify_success = await provisioner.delete_user(uuid=str(hiddify_uuid))
        if not hiddify_success:
            console.print("[red]❌ Ошибка удаления на HFM.[/red]")
            return

        # Удаляем из локальной БД
        await session.execute(text("DELETE FROM users WHERE id = :db_id"), {"db_id": db_id})
        await session.commit()
        console.print(f"[green]✅ Пользователь успешно удалён.[/green]")


# ============================================================
# 🔗 КОМАНДА: ПОЛУЧИТЬ ССЫЛКУ ПОДПИСКИ (LINK)
# ============================================================
@user.command(name="link")
@click.argument("identifier")
def user_link(identifier):
    """Получить ссылку подписки для пользователя по любому идентификатору."""
    async def _get_user_link():
        async with AsyncSessionLocal() as session:
            row = await find_user_by_identifier(session, identifier)
            if not row:
                console.print(f"[red]❌ Пользователь с идентификатором '{identifier}' не найден.[/red]")
                return
            tg_username, tg_user_id, hiddify_uuid, db_id = row
            base_domain = "ulysses.best"
            client_sub_url = f"https://{base_domain}/subscription/{hiddify_uuid}/#Ulysses"
            console.print(f"\n[bold green]🔑 Сетевой паспорт пользователя успешно извлечен![/bold green]")
            if tg_username:
                console.print(f"👤 Пользователь: [cyan]@{tg_username}[/cyan]", end="")
            else:
                console.print(f"👤 Пользователь: [cyan]email?[/cyan]", end="")
            if tg_user_id:
                console.print(f" (TG ID: {tg_user_id})", end="")
            console.print(f" (DB ID: {db_id})")
            console.print(f"🆔 UUID в системе: [yellow]{hiddify_uuid}[/yellow]")
            console.print(f"🔗 [bold magenta]ДЕЙСТВУЮЩАЯ ССЫЛКА ДЛЯ ИМПОРТА В HIDDIFY NEXT:[/bold magenta]")
            console.print(f"[bold white on magenta]{client_sub_url}[/bold white on magenta]\n")
    asyncio.run(_get_user_link())


# ============================================================
# 🔮 КОМАНДА: ИНСПЕКТОР СТРОК ПОДПИСКИ (USER JSON/TXT)
# ============================================================
# Найти команду @user.command(name="json") в cli/user.py и заменить её внутреннюю часть:

@user.command(name="json")
@click.argument("identifier")
def user_json(identifier):
    """Вывести JSON-конфиг для пользователя по любому идентификатору."""

    async def _render_json():
        async with AsyncSessionLocal() as session:
            row = await find_user_by_identifier(session, identifier)
            if not row:
                console.print(f"[red]❌ Пользователь с идентификатором '{identifier}' не найден.[/red]")
                return
            tg_username, tg_user_id, hiddify_uuid, db_id = row

            # Получаем статус подписки
            sub_result = await session.execute(
                text("SELECT status, expires_at FROM subscriptions WHERE user_id = :uid ORDER BY expires_at DESC LIMIT 1"),
                {"uid": db_id}
            )
            sub_row = sub_result.fetchone()
            status = sub_row[0] if sub_row else "unknown"
            expires_at = sub_row[1] if sub_row else None

            console.print(f"\n📋 [bold white]Профиль инспекции для '{identifier}':[/bold white]")
            if tg_username:
                console.print(f"   • TG: @{tg_username} (ID: {tg_user_id})")
            else:
                console.print(f"   • DB ID: {db_id}")
            console.print(f"   • Статус в БД: [{'green' if status == 'active' else 'red'}]{status}[/]")
            console.print(f"   • Ключ UUID: [cyan]{hiddify_uuid}[/cyan]\n")

            from app.routers.sub_render import generate_singbox_json
            json_config = await generate_singbox_json(str(hiddify_uuid), session)

            console.print("[bold magenta]📄 СТРУКТУРИРОВАННЫЙ JSON-КОНФИГ SING-BOX (Reality + xHTTP):[/bold magenta]")
            console.print("─" * 100)
            console.print(json.dumps(json_config, indent=2, ensure_ascii=False))
            console.print("─" * 100 + "\n")

    asyncio.run(_render_json())
