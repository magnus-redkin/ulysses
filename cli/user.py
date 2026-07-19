# cli/user.py

# АРХИТЕКТУРА И ИНСТРУМЕНТЫ УПРАВЛЕНИЯ КЛИЕНТСКИМИ АККАУНТАМИ CLI USER
# Данный модуль инкапсулирует команды администратора для точечной работы с пользователями.
# Чтение списка и ручное создание выполняются прямыми транзакциями в PostgreSQL через AsyncSessionLocal,
# а каскадное удаление делегируется эндпоинтам бэкенда для обеспечения синхронности с нодами VPN.

import asyncio
import click
import httpx
import uuid
from rich.console import Console
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

# Импортируем движок и фабрику сессий прямо из вашего бэкенда
from app.database import AsyncSessionLocal

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"

# Жестко переопределяем имя исполняемого файла в хелпе Click на uadmin
CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

@click.group(context_settings=CONTEXT_SETTINGS, short_help="Управление пользователями")
def user():
    """Управление пользователями Ulysses VPN.

    Использование: uadmin user КОМАНДА [АРГУМЕНТЫ]...
    """
    pass

# Переопределяем отображение имени группы в хелпах нижнего уровня
user.get_usage = lambda ctx: "uadmin user [ОПЦИИ] КОМАНДА [ARGS]..."


@user.command(name="list")
def user_list():
    """Показать детальный список всех пользователей (прямой запрос к БД).

    Пример: uadmin user list
    """
    async def _list():
        async with AsyncSessionLocal() as session:
            query = text("SELECT id, tg_user_id, tg_username, email, hiddify_uuid, created_at FROM users ORDER BY id")
            result = await session.execute(query)
            rows = result.fetchall()

            if not rows:
                console.print("[yellow]⚠️ База данных пользователей пуста.[/yellow]")
                return

            table = Table(title="👥 Все пользователи системы")
            table.add_column("ID", style="dim", justify="center")
            table.add_column("Telegram ID", style="magenta")
            table.add_column("Username", style="blue")
            table.add_column("Email", style="cyan")
            table.add_column("Hiddify UUID", style="green")
            table.add_column("Создан", style="dim")

            for r in rows:
                u_id, tg_id, username, email, hf_uuid, created_at = r

                table.add_row(
                    str(u_id),
                    str(tg_id) if tg_id else "-",
                    f"@{username}" if username else "-",
                    email if email else "-",
                    str(hf_uuid) if hf_uuid else "-",
                    created_at.strftime("%Y-%m-%d %H:%M") if created_at else "-"
                )
            console.print(table)

    asyncio.run(_list())

# Внутри ulysses-backend/cli/user.py

@user.command(name="create")
@click.option("--tg-id", type=int, required=True, help="Telegram ID нового пользователя")
@click.option("--username", type=str, required=True, help="Telegram username (например, @magnus)")
def user_create(tg_id, username):
    """
    Создать нового пользователя в системе биллинга 'под ключ'.
    Автоматически генерирует UUID, каскадно создает запись в PostgreSQL,
    активирует 3-дневный триал (Free) и делает провижн на ноду Hiddify v2.
    """
    clean_username = username.lstrip("@").strip()

    async def _create_user_pipeline():
        import uuid as uuid_lib
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import text
        from app.database import AsyncSessionLocal
        from app.services.hiddify_client import HiddifyProvisioner

        new_uuid = str(uuid_lib.uuid4())
        console.print(f"[yellow]⏳ Запуск каскадного создания пользователя для TG ID {tg_id}...[/yellow]")

        async with AsyncSessionLocal() as session:
            try:
                # 1. Проверяем дубликаты в СУБД
                res_check = await session.execute(text("SELECT id FROM users WHERE tg_user_id = :tg_id"), {"tg_id": tg_id})
                if res_check.fetchone():
                    console.print(f"[red]❌ Ошибка: Пользователь с TG ID {tg_id} уже существует в базе биллинга![/red]")
                    return

                # 2. ТРАНЗАКЦИЯ А: Создаем аккаунт пользователя
                sql_user = """
                    INSERT INTO users (tg_user_id, tg_username, hiddify_uuid, created_at, updated_at)
                    VALUES (:tg_id, :username, :uuid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """
                res_user = await session.execute(text(sql_user), {
                    "tg_id": tg_id, "username": clean_username, "uuid": new_uuid
                })
                user_internal_id = res_user.scalar_one()

                # 3. ТРАНЗАКЦИЯ Б: Сразу же выдаем бесплатный тариф (Free на 3 дня)
                # Это жестко свяжет профиль биллинга и заставит HFM отобразить юзера в браузере!
                now = datetime.now(timezone.utc)
                expires_at = now + timedelta(days=3)

                sql_sub = """
                    INSERT INTO subscriptions (
                        user_id, tariff_slug, status, node_id, starts_at, expires_at, created_at, updated_at, provisioning_attempts
                    )
                    VALUES (
                        :uid, 'sub_free', 'active', 'main', :starts, :expires, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0
                    )
                """
                await session.execute(text(sql_sub), {
                    "uid": user_internal_id, "starts": now, "expires": expires_at
                })

                # Фиксируем обе записи в PostgreSQL одной неделимой транзакцией (ACID)
                await session.commit()
                console.print(f"[green]💾 Локальный контур СУБД успешно обновлен. Внутренний ID: {user_internal_id}[/green]")

            except Exception as db_err:
                await session.rollback()
                console.print(f"[red]❌ Критический сбой СУБД PostgreSQL: {db_err}[/red]")
                return

        # 4. СЕТЕВОЙ ШАГ: Физически создаем пользователя на удаленной ноде Hiddify Manager v2
        try:
            provisioner = HiddifyProvisioner()
            # Наш метод create_user отправит POST на /api/v2/admin/user/ и применит кэш
            hiddify_success = await provisioner.create_user(
                uuid=new_uuid,
                name=f"tg_{tg_id}"
            )

            if hiddify_success:
                console.print(f"[green]✅ Успешно: Профиль активирован в Hiddify Manager v2 под именем tg_{tg_id}![/green]")
                console.print(f"[magenta]🔗 Персональный UUID: {new_uuid}[/magenta]")
            else:
                console.print("[red]❌ Предупреждение: Нода Hiddify v2 отклонила POST-запрос создания.[/red]")
        except Exception as hf_err:
            console.print(f"[red]❌ Сетевой сбой транспорта при связи с API Hiddify v2: {hf_err}[/red]")

    import asyncio
    asyncio.run(_create_user_pipeline())

@user.command(name="delete")
@click.option("--id", type=int, help="Поиск и каскадное удаление по локальному ID базы")
@click.option("--email", help="Поиск по Email")
@click.option("--tg-id", type=int, help="Поиск по Telegram ID")
@click.option("--target", type=click.Choice(["all", "db", "hiddify"]), default="all", help="Что именно удалять (all - везде, db - только БД, hiddify - только нода)")
@click.confirmation_option(prompt="Вы уверены, что хотите полностью удалить пользователя?")
def user_delete(id, email, tg_id, target):
    """Удалить пользователя из БД и нод VPN (через API бэкенда).

    Пример: uadmin user delete --tg-id 8397318328
    """
    async def _delete():
        params = {"target": target}

        if id:
            async with AsyncSessionLocal() as session:
                res = await session.execute(text("SELECT tg_user_id, email, hiddify_uuid FROM users WHERE id = :id"), {"id": id})
                row = res.fetchone()
                if not row:
                    console.print(f"[red]❌ Пользователь с ID {id} не найден в БД.[/red]")
                    return

                db_tg_id, db_email, db_uuid = row
                if db_tg_id: params["tg_user_id"] = db_tg_id
                if db_email: params["email"] = db_email
                if db_uuid: params["uuid"] = str(db_uuid)
        else:
            if tg_id: params["tg_user_id"] = tg_id
            if email: params["email"] = email

        if len(params) == 1:
            console.print("[red]❌ Укажите --id, --email или --tg-id для удаления.[/red]")
            return

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(f"{BACKEND_API_URL}/api/admin/account", params=params)
                if response.status_code == 200:
                    data = response.json()
                    console.print(f"[green]✅ Результат удаления: {data}[/green]")
                else:
                    console.print(f"[red]❌ Ошибка API: HTTP {response.status_code} - {response.text}[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка запроса к API: {e}[/red]")

    asyncio.run(_delete())


@user.command(name="clean")
@click.option("--force", is_flag=True, help="Пропустить интерактивное подтверждение")
def user_clean(force):
    """Автоматическое каскадное удаление всех тестовых аккаунтов (example.com / internal).

    Пример: uadmin user clean
    """
    if not force:
        if not click.confirm("⚠️ Вы уверены, что хотите НАВСЕГДА удалить ВСЕХ тестовых пользователей (65+ записей)?"):
            console.print("[yellow]❌ Операция отменена пользователем.[/yellow]")
            return

    console.print("[yellow]⏳ Запуск процедуры глобальной очистки мусора на бэкенде...[/yellow]")

    async def _clean():
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(f"{BACKEND_API_URL}/api/admin/fix/cleanup-test-users")
                if response.status_code == 200:
                    data = response.json()
                    console.print(f"[green]✅ Глобальная чистка завершена успешно![/green]")
                    console.print(f"   Удалено тестовых аккаунтов: [bold]{data.get('deleted_count', 0)}[/bold]")
                else:
                    console.print(f"[red]❌ Ошибка бэкенда: HTTP {response.status_code} - {response.text}[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка подключения к бэкенду: {e}[/red]")

    asyncio.run(_clean())
