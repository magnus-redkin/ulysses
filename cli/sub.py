# cli/sub.py

# УПРАВЛЕНИЕ УЧЕТНЫМИ ПЕРИОДАМИ И ПОДПИСКАМИ КЛИЕНТОВ CLI SUB
# Модуль инкапсулирует команды администратора для прямого изменения сроков доступа в БД.
# Реализует кумулятивное продление дней от текущей даты окончания активного периода,
# моделирование проблемных состояний для тестов и принудительный отзыв прав доступа.

import asyncio
import click
from datetime import datetime, timedelta, timezone
from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from app.database import AsyncSessionLocal

console = Console()

# Настройки контекста для жесткого переопределения ключей хелпа Click на uadmin
CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

@click.group(context_settings=CONTEXT_SETTINGS)
def sub():
    """Управление подписками пользователей Ulysses VPN.

    Использование: uadmin sub КОМАНДА [АРГУМЕНТЫ]...
    """
    pass

# Переопределяем отображение имени группы в подсказках хелпа нижнего уровня
sub.get_usage = lambda ctx: "uadmin sub [ОПЦИИ] КОМАНДА [ARGS]..."


@sub.command(name="list")
@click.argument('query', required=False)
def sub_list(query):
    """Показать детальный список подписок с привязкой к контактам.

    Без аргументов — полный список всех подписок в системе.\n
    С аргументом — фильтрация по Telegram ID, Email или Hiddify UUID.\n
    Пример: uadmin sub list 8397318328
    """
    async def _list():
        async with AsyncSessionLocal() as session:
            # Делаем JOIN с таблицей пользователей, чтобы вытащить контакты вместо сухих ID
            sql = """
                SELECT s.id, u.tg_user_id, u.tg_username, u.email,
                       s.tariff_slug, s.status, s.node_id, s.starts_at, s.expires_at, u.hiddify_uuid
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
            """
            params = {}

            # Если передан поисковый запрос, активируем умный фильтр по всем полям
            if query:
                clean_query = str(query).strip().lower()
                sql += """
                    WHERE CAST(u.tg_user_id AS TEXT) = :q
                       OR LOWER(u.email) = :q
                       OR CAST(u.hiddify_uuid AS TEXT) = :q
                       OR LOWER(u.tg_username) = :q_no_at
                """
                params["q"] = clean_query
                params["q_no_at"] = clean_query.replace("@", "")

            sql += " ORDER BY s.id DESC"

            result = await session.execute(text(sql), params)
            rows = result.fetchall()

            if not rows:
                console.print(f"[yellow]⚠️ Подписок по запросу '{query or 'ALL'}' не найдено.[/yellow]")
                return

            table = Table(title="💳 Подписки пользователей")
            table.add_column("Sub ID", style="dim", justify="center")
            table.add_column("Пользователь (Контакты)", style="cyan")
            table.add_column("Тариф", style="blue")
            table.add_column("Статус", style="green")
            table.add_column("Нода", style="dim")
            table.add_column("Начало", style="white")
            table.add_column("Истекает", style="yellow")

            for r in rows:
                sub_id, tg_id, username, email, tariff, status, node, starts, expires, hf_uuid = r

                # Собираем красивую понятную строчку контактов юзера
                contact_parts = []
                if tg_id:
                    contact_parts.append(f"TG: {tg_id}")
                if username:
                    contact_parts.append(f"@{username}")
                if email and not email.endswith("@ulysses.internal"):
                    contact_parts.append(email)

                # Если у пользователя нет ТГ и почты (например, чистый UUID с сайта), пишем кусок UUID
                contact_str = " | ".join(contact_parts) if contact_parts else f"UUID: {str(hf_uuid)[:8]}..."

                starts_str = starts.strftime("%Y-%m-%d %H:%M") if hasattr(starts, "strftime") else "-"
                expires_str = expires.strftime("%Y-%m-%d %H:%M") if hasattr(expires, "strftime") else "-"

                if status == "active":
                    status_colored = f"[green]{status}[/green]"
                elif status in ("provisioning", "pending_payment"):
                    status_colored = f"[yellow]{status}[/yellow]"
                else:
                    status_colored = f"[red]{status}[/red]"

                table.add_row(
                    str(sub_id), contact_str, tariff, status_colored,
                    str(node or "-"), starts_str, expires_str
                )
            console.print(table)

    asyncio.run(_list())


@sub.command(name="active")
@click.option("--user-id", type=int, required=True, help="ID пользователя из таблицы users")
@click.option("--tariff", default="premium_1m", help="Слаг тарифа (например: premium_1m, VIP)")
@click.option("--days", type=int, default=30, help="Количество добавляемых дней подписки")
def sub_active(user_id, tariff, days):
    """Активировать или продлить подписку пользователю вручную.

    Пример: uadmin sub active --user-id 1 --days 30
    """
    async def _active():
        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id})
            if not res.fetchone():
                console.print(f"[red]❌ Ошибка: Пользователь с ID {user_id} не найден в базе данных.[/red]")
                return

            now = datetime.now(timezone.utc)

            sql_check = """
                SELECT id, expires_at FROM subscriptions
                WHERE user_id = :user_id AND status = 'active' AND expires_at > :now
                LIMIT 1
            """
            sub_res = await session.execute(text(sql_check), {"user_id": user_id, "now": now})
            existing_sub = sub_res.fetchone()

            if existing_sub:
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
@click.option("--user-id", type=int, help="ID пользователя из таблицы users (для создания)")
@click.option("--tariff", default="premium_1m", help="Слаг тарифа для новой тестовой записи")
@click.option("--error", default="Hiddify API Connection Refused (Timeout)", help="Текст искусственной ошибки ноды")
@click.option("--attempts", type=int, default=1, help="Количество неудачных попыток")
@click.option("--create", is_flag=True, help="Активировать режим моделирования новой ошибки")
def sub_pending(user_id, tariff, error, attempts, create):
    """Показать зависшие подписки или смоделировать новую проблему для тестов.

    Без флагов — выводит список всех подписок со статусом 'provisioning'.\n
    Пример: uadmin sub pending\n
    С флагом --create — моделирует аварийную запись: uadmin sub pending --create --user-id 148
    """
    async def _pending_logic():
        async with AsyncSessionLocal() as session:

            # РЕЖИМ 1: Моделирование новой зависшей подписки
            if create:
                if not user_id:
                    raise click.UsageError("❌ Ошибка: для режима создания необходимо указать --user-id")

                res = await session.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id})
                if not res.fetchone():
                    console.print(f"[red]❌ Ошибка: Пользователь с ID {user_id} не найден.[/red]")
                    return

                now = datetime.now(timezone.utc)
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
                    "user_id": user_id, "tariff": tariff, "attempts": attempts, "error": error, "now": now
                })
                await session.commit()
                new_sub_id = res_insert.scalar_one()

                console.print(f"[yellow]⚠️ Успешно смоделирована зависшая подписка! ID подписки: {new_sub_id}[/yellow]")
                console.print(f"➜ Статус: [magenta]provisioning[/magenta] | Попыток: {attempts} | Ошибка: [red]{error}[/red]")
                return

            # РЕЖИМ 2: Вывод всех зависших подписок по умолчанию
            sql_select = """
                SELECT s.id, u.tg_user_id, u.tg_username, u.email,
                       s.tariff_slug, s.provisioning_attempts, s.provisioning_error, s.created_at
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
                WHERE s.status = 'provisioning'
                ORDER BY s.id DESC
            """
            result = await session.execute(text(sql_select))
            rows = result.fetchall()

            if not rows:
                console.print("[green]✅ Зависших подписок (provisioning) в системе не обнаружено.[/green]")
                return

            table = Table(title="🚨 Зависшие подписки в обработке")
            table.add_column("Sub ID", style="dim", justify="center")
            table.add_column("Пользователь (Контакты)", style="cyan")
            table.add_column("Тариф", style="blue")
            table.add_column("Попыток", style="yellow", justify="center")
            table.add_column("Текст ошибки ноды", style="red")
            table.add_column("Создана", style="dim")

            for r in rows:
                s_id, tg_id, username, email, tariff_slug, atts, err, created_at = r

                contact_parts = []
                if tg_id: contact_parts.append(f"TG: {tg_id}")
                if username: contact_parts.append(f"@{username}")
                if email and not email.endswith("@ulysses.internal"): contact_parts.append(email)
                contact_str = " | ".join(contact_parts) if contact_parts else "Анонимный профиль"

                created_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "-"

                table.add_row(
                    str(s_id), contact_str, tariff_slug, str(atts or 0),
                    str(err or "Ожидает выдачи"), created_str
                )
            console.print(table)
            console.print("[yellow]➜ Подсказка: Вы можете протолкнуть их командой: uadmin fix pending --force[/yellow]")

    asyncio.run(_pending_logic())


@sub.command(name="revoke")
@click.option("--user-id", type=int, required=True, help="ID пользователя из таблицы users")
def sub_revoke(user_id):
    """Принудительно отозвать (аннулировать) все active подписки пользователя.

    Пример: uadmin sub revoke --user-id 153
    """
    async def _revoke():
        async with AsyncSessionLocal() as session:
            now = datetime.now(timezone.utc)

            sql_check = "SELECT id FROM subscriptions WHERE user_id = :user_id AND status = 'active'"
            res = await session.execute(text(sql_check), {"user_id": user_id})
            rows = res.fetchall()

            if not rows:
                console.print(f"[yellow]⚠️ У пользователя с ID {user_id} нет active подписок для отзыва.[/yellow]")
                return

            sql_update = """
                UPDATE subscriptions
                SET status = 'cancelled', updated_at = :now
                WHERE user_id = :user_id AND status = 'active'
            """
            await session.execute(text(sql_update), {"user_id": user_id, "now": now})
            await session.commit()

            sub_ids = [str(r[0]) for r in rows]
            console.print(f"[green]✅ Успешно отозваны подписки со статусом active (ID: {', '.join(sub_ids)}) для пользователя {user_id}.[/green]")
            console.print("[yellow]➜ Напоминание: Синхронизируйте изменения с нодой через uadmin fix sync.[/yellow]")

    asyncio.run(_revoke())


if __name__ == "__main__":
    sub(prog_name="uadmin sub")
