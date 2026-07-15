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

@click.group()
def user():
    """Управление пользователями Ulysses VPN"""
    pass

@user.command(name="list")
def user_list():
    """Показать детальный список всех пользователей (прямой запрос к БД)"""
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
                # Распаковываем полученную строку для безопасного вывода
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


@user.command(name="create")
@click.option("--email", help="Email пользователя")
@click.option("--tg-id", type=int, help="Telegram User ID")
@click.option("--username", help="Telegram Username (без @)")
def user_create(email, tg_id, username):
    """Создать пользователя вручную (прямой запрос к БД)"""
    if not email and not tg_id:
        raise click.UsageError("❌ Ошибка: необходимо указать хотя бы --email или --tg-id")

    async def _create():
        new_uuid = str(uuid.uuid4())
        async with AsyncSessionLocal() as session:
            # Проверяем дубликаты по Email
            if email:
                res = await session.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
                if res.fetchone():
                    console.print(f"[red]❌ Пользователь с email {email} уже существует.[/red]")
                    return

            # Проверяем дубликаты по Telegram ID
            if tg_id:
                res = await session.execute(text("SELECT id FROM users WHERE tg_user_id = :id"), {"id": tg_id})
                if res.fetchone():
                    console.print(f"[red]❌ Пользователь с Telegram ID {tg_id} уже существует.[/red]")
                    return

            query = text("""
                INSERT INTO users (tg_user_id, tg_username, email, hiddify_uuid)
                VALUES (:tg_id, :username, :email, :uuid)
                RETURNING id
            """)
            result = await session.execute(query, {
                "tg_id": tg_id,
                "username": username,
                "email": email,
                "uuid": new_uuid
            })
            await session.commit()
            new_id = result.scalar_one()
            console.print(f"[green]✅ Пользователь успешно создан! ID: {new_id} | UUID: {new_uuid}[/green]")

    asyncio.run(_create())


@user.command(name="delete")
@click.option("--id", type=int, help="Поиск по локальному ID базы данных")
@click.option("--email", help="Поиск по Email")
@click.option("--tg-id", type=int, help="Поиск по Telegram ID")
@click.option("--target", type=click.Choice(["all", "db", "hiddify"]), default="all", help="Что именно удалять")
@click.confirmation_option(prompt="Вы уверены, что хотите удалить пользователя?")
def user_delete(id, email, tg_id, target):
    """Удалить пользователя из БД и Hiddify (через API бэкенда)"""
    async def _delete():
        params = {"target": target}

        # Если передан внутренний ID, сначала найдем контакты в БД прямым запросом
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
