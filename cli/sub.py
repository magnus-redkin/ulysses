import asyncio
import click
from datetime import datetime, timedelta, timezone
from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from app.database import AsyncSessionLocal

console = Console()

@click.group()
def sub():
    """Управление подписками пользователей Ulysses VPN"""
    pass


@sub.command(name="list")
@click.option("--user-id", type=int, help="Фильтр по ID пользователя")
def sub_list(user_id):
    """Показать список всех подписок"""
    async def _list():
        async with AsyncSessionLocal() as session:
            sql = """
                SELECT id, user_id, tariff_slug, status, node_id, starts_at, expires_at
                FROM subscriptions
            """
            params = {}
            if user_id:
                sql += " WHERE user_id = :user_id"
                params["user_id"] = user_id
            sql += " ORDER BY id DESC"

            result = await session.execute(text(sql), params)
            rows = result.fetchall()

            if not rows:
                console.print("[yellow]⚠️ Подписок в системе не найдено.[/yellow]")
                return

            table = Table(title="💳 Подписки пользователей")
            table.add_column("ID подписки", style="dim", justify="center")
            table.add_column("User ID", style="magenta", justify="center")
            table.add_column("Тариф", style="blue")
            table.add_column("Статус", style="green")
            table.add_column("Нода", style="dim")
            table.add_column("Начало", style="white")
            table.add_column("Истекает", style="yellow")

            for r in rows:
                sub_id, u_id, tariff, status, node, starts, expires = r

                # Безопасное форматирование дат (защита от None / NULL в БД)
                starts_str = starts.strftime("%Y-%m-%d %H:%M") if hasattr(starts, "strftime") else "-"
                expires_str = expires.strftime("%Y-%m-%d %H:%M") if hasattr(expires, "strftime") else "-"

                # Раскрашиваем разные статусы для наглядности
                if status == "active":
                    status_colored = f"[green]{status}[/green]"
                elif status in ("provisioning", "pending_payment"):
                    status_colored = f"[yellow]{status}[/yellow]"
                else:
                    status_colored = f"[red]{status}[/red]"

                table.add_row(
                    str(sub_id), str(u_id), tariff, status_colored,
                    str(node or "-"), starts_str, expires_str
                )
            console.print(table)

    asyncio.run(_list())


@sub.command(name="active")
@click.option("--user-id", type=int, required=True, help="ID пользователя из таблицы users")
@click.option("--tariff", default="premium_1m", help="Слаг тарифа (например: premium_1m, VIP)")
@click.option("--days", type=int, default=30, help="Количество дней подписки (по умолчанию 30)")
def sub_active(user_id, tariff, days):
    """Активировать или продлить подписку пользователю вручную"""
    async def _active():
        async with AsyncSessionLocal() as session:
            # 1. Проверяем, существует ли пользователь
            res = await session.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id})
            if not res.fetchone():
                console.print(f"[red]❌ Ошибка: Пользователь с ID {user_id} не найден в базе данных.[/red]")
                return

            now = datetime.now(timezone.utc)

            # 2. Проверяем, есть ли уже активная подписка у пользователя, чтобы продлить её кумулятивно
            sql_check = """
                SELECT id, expires_at FROM subscriptions
                WHERE user_id = :user_id AND status = 'active' AND expires_at > :now
                LIMIT 1
            """
            sub_res = await session.execute(text(sql_check), {"user_id": user_id, "now": now})
            existing_sub = sub_res.fetchone()

            if existing_sub:
                # Продлеваем от даты окончания текущей подписки
                current_sub_id, current_expires = existing_sub
                new_expires = current_expires + timedelta(days=days)

                sql_update = """
                    UPDATE subscriptions
                    SET expires_at = :new_expires, updated_at = :now
                    WHERE id = :sub_id
                """
                await session.execute(text(sql_update), {"new_expires": new_expires, "now": now, "sub_id": current_sub_id})
                await session.commit()
                console.print(f"[green]✅ Активная подписка (ID: {current_sub_id}) успешно продлена на {days} дней![/green]")
                console.print(f"📅 Новая дата окончания: [yellow]{new_expires.strftime('%Y-%m-%d %H:%M')}[/yellow]")
            else:
                # Создаем новую чистую активную подписку
                starts_at = now
                expires_at = now + timedelta(days=days)

                sql_insert = """
                    INSERT INTO subscriptions (user_id, tariff_slug, status, starts_at, expires_at, activated_at, node_id)
                    VALUES (:user_id, :tariff, 'active', :starts_at, :expires_at, :now, 'main')
                    RETURNING id
                """
                res_insert = await session.execute(text(sql_insert), {
                    "user_id": user_id,
                    "tariff": tariff,
                    "starts_at": starts_at,
                    "expires_at": expires_at,
                    "now": now
                })
                await session.commit()
                new_sub_id = res_insert.scalar_one()
                console.print(f"[green]✅ Создана новая активная подписка для User ID {user_id}! (ID подписки: {new_sub_id})[/green]")
                console.print(f"⏱ Срок действия: c [white]{starts_at.strftime('%Y-%m-%d')}[/white] по [yellow]{expires_at.strftime('%Y-%m-%d %H:%M')}[/yellow]")

    asyncio.run(_active())

@sub.command(name="pending")
@click.option("--user-id", type=int, required=True, help="ID пользователя из таблицы users")
@click.option("--tariff", default="premium_1m", help="Слаг тарифа")
@click.option("--error", default="Hiddify API Connection Refused (Timeout)", help="Текст искусственной ошибки ноды")
@click.option("--attempts", type=int, default=1, help="Количество неудачных попыток")
def sub_pending(user_id, tariff, error, attempts):
    """Создать 'проблемную' или зависшую подписку в обработке для тестов"""
    async def _pending():
        async with AsyncSessionLocal() as session:
            # Проверяем, существует ли пользователь
            res = await session.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id})
            if not res.fetchone():
                console.print(f"[red]❌ Ошибка: Пользователь с ID {user_id} не найден.[/red]")
                return

            now = datetime.now(timezone.utc)

            # Создаем запись в статусе provisioning БЕЗ дат начала и конца (они еще не активированы)
            sql_insert = """
                INSERT INTO subscriptions (
                    user_id, tariff_slug, status, node_id,
                    provisioning_attempts, last_provisioning_at, provisioning_error, created_at, updated_at
                )
                VALUES (
                    :user_id, :tariff, 'provisioning', 'main',
                    :attempts, :now, :error, :now, :now
                )
                RETURNING id
            """
            res_insert = await session.execute(text(sql_insert), {
                "user_id": user_id,
                "tariff": tariff,
                "attempts": attempts,
                "error": error,
                "now": now
            })
            await session.commit()
            new_sub_id = res_insert.scalar_one()

            console.print(f"[yellow]⚠️ Успешно смоделирована зависшая подписка! ID подписки: {new_sub_id}[/yellow]")
            console.print(f"➜ Статус: [magenta]provisioning[/magenta] | Попыток: {attempts} | Ошибка: [red]{error}[/red]")
            console.print("[yellow]➜ Теперь вы можете запустить 'uadmin stats' для проверки отображения проблемы.[/yellow]")

    asyncio.run(_pending())


@sub.command(name="revoke")
@click.option("--user-id", type=int, required=True, help="ID пользователя")
def sub_revoke(user_id):
    """Принудительно отозвать (аннулировать) все активные подписки пользователя"""
    async def _revoke():
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)

            # Проверяем наличие активных подписок
            sql_check = "SELECT id FROM subscriptions WHERE user_id = :user_id AND status = 'active'"
            res = await session.execute(text(sql_check), {"user_id": user_id})
            rows = res.fetchall()

            if not rows:
                console.print(f"[yellow]⚠️ У пользователя с ID {user_id} нет active подписок для отзыва.[/yellow]")
                return

            # Переводим в статус cancelled
            sql_update = """
                UPDATE subscriptions
                SET status = 'cancelled', updated_at = :now
                WHERE user_id = :user_id AND status = 'active'
            """
            await session.execute(text(sql_update), {"user_id": user_id, "now": now})
            await session.commit()

            sub_ids = [str(r[0]) for r in rows]
            console.print(f"[green]✅ Успешно отозваны подписки со статусом active (ID: {', '.join(sub_ids)}) для пользователя {user_id}.[/green]")
            console.print("[yellow]➜ Напоминание: Если интеграция с Hiddify настроена в фоне, синхронизируйте ноду через uadmin fix sync.[/yellow]")

    asyncio.run(_revoke())
