import asyncio
from datetime import datetime, timedelta, timezone
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
from app.database import AsyncSessionLocal
import uuid as uuid_lib


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
    """Создать нового пользователя и активировать бесплатный тест-драйв."""

    clean_username = username.lstrip("@").strip()
    console.print(f"[yellow]⏳ Запуск создания пользователя для TG ID {tg_id}...[/yellow]")

    async with AsyncSessionLocal() as session:
        try:
            # 1. Проверяем, существует ли пользователь
            user = await get_or_create_user(session, tg_user_id=tg_id)
            if user.get("user_id"):
                console.print(f"[red]❌ Ошибка: Пользователь с TG ID {tg_id} уже существует в базе![/red]")
                return

            # 2. Создаём нового пользователя (get_or_create_user это сделает)
            # Но мы хотим явно контролировать процесс, поэтому передаём email=None
            user = await get_or_create_user(session, tg_user_id=tg_id, email=None)
            # Если пользователь уже был, get_or_create_user вернул бы его, но мы проверили выше.

            # 3. Активируем бесплатный тариф
            result = await create_free_subscription(session, user)

            # 4. Вывод результата
            domain = "ulysses.best"
            subscription_link = f"https://{domain}/subscription/{user['hiddify_uuid']}/#Ulysses"
            console.print(f"\n[bold green]🎉 Каскад создания пользователя полностью завершен![/bold green]")
            console.print(f"👤 Telegram ID: [cyan]{tg_id}[/cyan] | Юзернейм: [cyan]@{clean_username}[/cyan]")
            console.print(f"🔑 Персональный UUID: [yellow]{user['hiddify_uuid']}[/yellow]")
            console.print(f"🔗 [bold magenta]ФИНАЛЬНАЯ ССЫЛКА ДЛЯ КЛИЕНТА (Hiddify/Sing-box):[/bold magenta]")
            console.print(f"[bold white on magenta] {subscription_link} [/bold white on magenta]\n")

        except Exception as err:
            console.print(f"[red]❌ Критический сбой при создании пользователя: {err}[/red]")

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
# ❌ КОМАНДА: УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ (DELETE) - ТОТАЛЬНЫЙ КОНТРОЛЬ
# ============================================================
@user.command(name="delete")
@click.argument("identifier")
@async_cmd
async def user_delete(identifier):
    """
    Удалить пользователя по любому идентификатору (TG ID, email, UUID, DB ID).
    Удаление из локальной БД происходит ТОЛЬКО после успешного удаления на HFM.
    """
    async with AsyncSessionLocal() as session:
        console.print(f"[yellow]⏳ Поиск пользователя по идентификатору '{identifier}'...[/yellow]")
        row = await find_user_by_identifier(session, identifier)

        if not row:
            console.print(f"[red]❌ Ошибка: Пользователь с идентификатором '{identifier}' не найден в биллинге.[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row
        hiddify_uuid_str = str(hiddify_uuid).strip() if hiddify_uuid else ""

        # Проверяем, есть ли что удалять на HFM
        if hiddify_uuid_str and hiddify_uuid_str not in ("", "None", "-"):
            console.print(f"[yellow]📡 Отправка запроса на удаление профиля {hiddify_uuid_str} с HFM...[/yellow]")
            provisioner = HiddifyProvisioner()

            # ЗАЩИТА 1: Проверяем физическое наличие метода в коде
            if not hasattr(provisioner, "delete_user"):
                console.print("[bold red]⛔ КРИТИЧЕСКАЯ ОШИБКА БИБЛИОТЕКИ:[/bold red]")
                console.print("[red]В классе HiddifyProvisioner отсутствует метод 'delete_user'![/red]")
                console.print("[red]Локальная база данных НЕ изменена. Обновите app/services/hiddify_client.py.[/red]")
                return

            # Вызываем удаление на сервере
            result = await provisioner.delete_user(uuid=hiddify_uuid_str)

            # ЗАЩИТА 2: Если HFM ответил отказом или упала сеть
            if not result["success"]:
                console.print("[bold red]⛔ СБОЙ СИНХРОНИЗАЦИИ ИНФРАСТРУКТУРЫ:[/bold red]")
                console.print("[red]Не удалось удалить пользователя на удаленном сервере HFM (сетевой сбой или ошибка API).[/red]")
                console.print("[yellow]🔄 Локальная запись сохранены в СУБД. Сначала почините связь с нодой VPN.[/yellow]")
                return

            if result["not_found"]:
                console.print("[yellow]⚠️ Профиль отсутствовал на сервере HFM (404), но операция признана успешной.[/yellow]")
            else:
                console.print("[green]✨ Профиль успешно стерт из памяти Hiddify Manager.[/green]")
        else:
            console.print("[cyan]ℹ️ У записи нет UUID подписки в локальной БД. Удаление на HFM не требуется.[/cyan]")

        # Финальный шаг: Удаление из локальной БД (выполняется только если прошли верхние фильтры)
        console.print(f"[yellow]🗑️ Очистка локальной записи ID {db_id} из базы данных Ulysses...[/yellow]")
        try:
            await session.execute(text("DELETE FROM users WHERE id = :db_id"), {"db_id": db_id})
            await session.commit()
            console.print(f"[bold green]✅ Полный цикл удаления завершен. Пользователь {identifier} стерт отовсюду.[/bold green]")
        except Exception as e:
            await session.rollback()
            console.print(f"[bold red]❌ Ошибка при фиксации изменений в СУБД: {e}[/bold red]")
from rich.syntax import Syntax  # <-- ДОБАВЛЕНО для красивой подсветки кода
from rich.json import JSON      # <-- ДОБАВЛЕНО для валидации и вывода JSON

# ============================================================
# 🔗 КОМАНДА: ПОЛУЧИТЬ ССЫЛКУ ПОДПИСКИ (LINK) - ИСПРАВЛЕНА
# ============================================================
@user.command(name="link")
@click.argument("identifier")
@async_cmd  # ИСПРАВЛЕНО: Заменили ручной asyncio.run на безопасный декларативный декоратор
async def user_link(identifier):
    """Получить ссылку подписки для пользователя по любому идентификатору."""
    async with AsyncSessionLocal() as session:
        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print(f"[red]❌ Пользователь с идентификатором '{identifier}' не найден.[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row

        # ИСПРАВЛЕНО: Защитный барьер от пустых UUID
        if not hiddify_uuid or str(hiddify_uuid).strip() in ("None", "-"):
            console.print(f"[red]❌ Ошибка: У пользователя ID {db_id} отсутствует UUID в базе данных![/red]")
            return

        base_domain = "ulysses.best"
        client_sub_url = f"https://{base_domain}/subscription/{hiddify_uuid}/#Ulysses"

        console.print(f"\n[bold green]🔑 Сетевой паспорт пользователя успешно извлечен![/bold green]")
        if tg_username:
            console.print(f"👤 Пользователь: [cyan]@{tg_username}[/cyan]", end="")
        else:
            console.print(f"👤 Пользователь: [cyan]email/no_username[/cyan]", end="")

        if tg_user_id:
            console.print(f" (TG ID: {tg_user_id})", end="")
        console.print(f" (DB ID: {db_id})")
        console.print(f"🆔 UUID в системе: [yellow]{hiddify_uuid}[/yellow]")
        console.print(f"🔗 [bold magenta]ДЕЙСТВУЮЩАЯ ССЫЛКА ДЛЯ ИМПОРТА В HIDDIFY NEXT / SING-BOX:[/bold magenta]")
        console.print(f"[bold white on magenta] {client_sub_url} [/bold white on magenta]\n")


# ============================================================
# 🔮 КОМАНДА: ИНСПЕКТОР СТРОК ПОДПИСКИ (USER JSON) - ИСПРАВЛЕНА
# ============================================================
@user.command(name="json")
@click.argument("identifier")
@async_cmd  # ИСПРАВЛЕНО: Заменили ручной asyncio.run на декоратор
async def user_json(identifier):
    """Вывести JSON-конфиг для пользователя по любому идентификатору."""
    async with AsyncSessionLocal() as session:
        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print(f"[red]❌ Пользователь с идентификатором '{identifier}' не найден.[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row

        if not hiddify_uuid or str(hiddify_uuid).strip() in ("None", "-"):
            console.print(f"[red]❌ Ошибка: Невозможно сгенерировать конфиг, так как UUID равен NULL.[/red]")
            return

        # Получаем статус подписки
        sub_result = await session.execute(
            text("SELECT status, expires_at FROM subscriptions WHERE user_id = :uid ORDER BY expires_at DESC LIMIT 1"),
            {"uid": db_id}
        )
        sub_row = sub_result.fetchone()
        status = sub_row[0] if sub_row else "unknown"
        expires_at = sub_row[1] if sub_row else None

        # Красивое форматирование даты
        expires_str = expires_at.strftime("%Y-%m-%d %H:%M UTC") if expires_at else "infinity"

        console.print(f"\n📋 [bold white]Профиль инспекции для '{identifier}':[/bold white]")
        if tg_username:
            console.print(f"   • TG: @{tg_username} (ID: {tg_user_id})")
        else:
            console.print(f"   • DB ID: {db_id}")

        status_color = "green" if status == "active" else "yellow" if status == "provisioning" else "red"
        console.print(f"   • Статус в БД: [{status_color}]{status}[/]")
        console.print(f"   • Истекает: [magenta]{expires_str}[/magenta]")
        console.print(f"   • Ключ UUID: [cyan]{hiddify_uuid}[/cyan]\n")

        # Вызов внешнего рендерера
        try:
            from app.routers.sub_render import generate_singbox_json
            json_config = await generate_singbox_json(str(hiddify_uuid), session)

            console.print("[bold magenta]📄 СТРУКТУРИРОВАННЫЙ JSON-КОНФИГ SING-BOX (Reality + xHTTP):[/bold magenta]")
            console.print("─" * 100)

            # ИСПРАВЛЕНО: Вместо json.dumps используем встроенный Rich-компонент,
            # который автоматически раскрасит ключи, строки и числа для удобства чтения в терминале
            if isinstance(json_config, dict):
                raw_json_str = json.dumps(json_config, ensure_ascii=False, indent=2)
                syntax = Syntax(raw_json_str, "json", theme="monokai", line_numbers=True)
                console.print(syntax)
            else:
                console.print(f"[yellow]⚠️ Рендерер вернул не словарь, а: {type(json_config)}[/yellow]")
                console.print(str(json_config))

            console.print("─" * 100 + "\n")

        except Exception as e:
            console.print(f"[bold red]❌ Ошибка вызова генератора singbox конфигурации: {e}[/bold red]")

# ============================================================
# ⏳ КОМАНДА: ИНСПЕКТОР СТАТУСА ПОДПИСОК (SUB) + LIVE API HFM
# ============================================================
@user.command(name="sub")
@click.argument("identifier")
@async_cmd
async def user_subscription_status(identifier):
    """Посмотреть детальную историю подписок и LIVE статус профиля на ноде VPN."""
    async with AsyncSessionLocal() as session:
        console.print(f"[yellow]⏳ Поиск пользователя и истории подписок для '{identifier}'...[/yellow]")

        row = await find_user_by_identifier(session, identifier)
        if not row:
            console.print(f"[red]❌ Пользователь с идентификатором '{identifier}' не найден в биллинге.[/red]")
            return

        tg_username, tg_user_id, hiddify_uuid, db_id = row
        hiddify_uuid_str = str(hiddify_uuid).strip() if hiddify_uuid else ""

        # 1. LIVE-диагностика: Проверяем физическое наличие юзера на сервере VPN по API
        hfm_status_str = "[bold red]❓ Невозможно проверить (Нет UUID)[/bold red]"
        if hiddify_uuid_str and hiddify_uuid_str not in ("None", "-"):
            console.print(f"[yellow]📡 LIVE API: Проверка профиля {hiddify_uuid_str} на сервере Hiddify...[/yellow]")
            provisioner = HiddifyProvisioner()
            try:
                # ИСПРАВЛЕНО: Защитная проверка наличия метода в классе
                if hasattr(provisioner, "check_user_exists"):
                    user_exists_on_hfm = await provisioner.check_user_exists(hiddify_uuid_str)
                    if user_exists_on_hfm:
                        hfm_status_str = "[bold green]🟢 СИНХРОНИЗИРОВАН (Профиль создан на ноде VPN)[/bold green]"
                    else:
                        hfm_status_str = "[bold yellow]⚪ ОТСУТСТВУЕТ НА СЕРВЕРЕ (В базе Ulysses есть, на ноде VPN профиля нет)[/bold yellow]"
                else:
                    # Резервный вариант, если метода нет, но есть fetch_all_users
                    if hasattr(provisioner, "fetch_all_users"):
                        users = await provisioner.fetch_all_users()
                        if users and any(str(u.get("uuid", "")).lower() == hiddify_uuid_str.lower() for u in users):
                            hfm_status_str = "[bold green]🟢 СИНХРОНИЗИРОВАН (Найден через полный список)[/bold green]"
                        else:
                            hfm_status_str = "[bold yellow]⚪ ОТСУТСТВУЕТ НА СЕРВЕРЕ (Не найден в полном списке)[/bold yellow]"
                    else:
                        hfm_status_str = "[bold amber]⚠️ Ошибка: Метод check_user_exists отсутствует в клиенте[/bold amber]"
            except Exception as e:
                hfm_status_str = f"[bold amber]⚠️ Ошибка API ноды: {e}[/bold amber]"


        # 2. Вытаскиваем историю подписок из базы
        sql_subs = """
            SELECT id, tariff_slug, status, node_id, starts_at, expires_at, provisioning_attempts, provisioning_error
            FROM subscriptions
            WHERE user_id = :uid
            ORDER BY expires_at DESC NULLS FIRST, id DESC
        """
        res_subs = await session.execute(text(sql_subs), {"uid": db_id})
        subscriptions = res_subs.fetchall()

        # Вывод паспорта
        console.print(f"\n👤 [bold white]Профиль пользователя ID {db_id}:[/bold white]")
        console.print(f"   • Telegram: [cyan]@{tg_username if tg_username else 'email_only'}[/cyan] (ID: {tg_user_id if tg_user_id else '-'})")
        console.print(f"   • VPN UUID: [yellow]{hiddify_uuid_str if hfm_status_str else 'ОТСУТСТВУЕТ!'}[/yellow]")
        console.print(f"   • Статус на Ноде: {hfm_status_str}\n") # <-- НАШ ЛАЙВ СТАТУС

        if not subscriptions:
            console.print("[yellow]ℹ️ У этого пользователя еще нет ни одной созданной или оплаченной подписки.[/yellow]")
            console.print("[dim]Это нормальное состояние, если пользователь только зашел в бота, но еще не выбрал тариф.[/dim]\n")
            return

        # 3. Строим таблицу подписок
        table = Table(title=f"📅 История подписок в СУБД Ulysses (Всего: {len(subscriptions)})")
        table.add_column("Sub ID", justify="center", style="dim")
        table.add_column("Тариф (Slug)", style="blue")
        table.add_column("Статус", justify="center")
        table.add_column("Нода", style="magenta")
        table.add_column("Начало (UTC)", justify="center")
        table.add_column("Истекает (UTC)", justify="center")
        table.add_column("Ошибки / Попытки", style="red")

        for sub in subscriptions:
            sub_id, tariff_slug, status, node_id, starts_at, expires_at, attempts, error = sub

            if status == "active":
                status_formatted = "[bold green]🟢 active[/bold green]"
            elif status == "provisioning":
                status_formatted = "[bold yellow]⏳ provisioning[/bold yellow]"
            elif status == "expired":
                status_formatted = "[bold red]🔴 expired[/bold red]"
            elif status == "cancelled":
                status_formatted = "[dim white]⚪ cancelled[/dim white]"
            else:
                status_formatted = f"[italic]{status}[/italic]"

            starts_str = starts_at.strftime("%Y-%m-%d %H:%M") if starts_at else "-"
            expires_str = expires_at.strftime("%Y-%m-%d %H:%M") if expires_at else "[bold blue]Infinity[/bold blue]"

            # Индикатор рассинхронизации (Критический баг-трекер для админа)
            if status == "active" and expires_at and expires_at < datetime.now(timezone.utc):
                status_formatted = "[bold red]🚨 active (ПРОТУХЛА)[/bold red]"

            error_info = "-"
            if error or (attempts and attempts > 0):
                error_info = f"[{attempts} поп.] {error[:25] if error else 'API error'}"

            table.add_row(
                str(sub_id),
                str(tariff_slug),
                status_formatted,
                str(node_id),
                starts_str,
                expires_str,
                error_info
            )

        console.print(table)
        console.print("")
