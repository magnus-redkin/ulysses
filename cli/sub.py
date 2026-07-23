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
from app.services.hiddify_client import HiddifyProvisioner

import json
import os

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


# ============================================================
# 📋 КОМАНДА: СПИСОК ПОДПИСОК (LIST)
# ============================================================
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
            # показать всех
            # sql = """
            #    SELECT s.id, u.tg_user_id, u.tg_username, u.email,
            #    s.tariff_slug, s.status, s.node_id, s.starts_at, s.expires_at, u.hiddify_uuid
            #    FROM users u
            #    LEFT JOIN subscriptions s ON s.user_id = u.id
            # """

            sql = """
                SELECT s.id, u.tg_user_id, u.tg_username, u.email,
                       s.tariff_slug, s.status, s.node_id, s.starts_at, s.expires_at, u.hiddify_uuid
                FROM subscriptions s
                JOIN users u ON s.user_id = u.id
            """
            params = {}

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

                contact_parts = []
                if tg_id:
                    contact_parts.append(f"TG: {tg_id}")
                if username:
                    contact_parts.append(f"@{username}")
                if email and not email.endswith("@ulysses.internal"):
                    contact_parts.append(email)

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


# ============================================================
# 🟢 КОМАНДА: АКТИВАЦИЯ ИЛИ ПРОДЛЕНИЕ (ACTIVE)
# ============================================================
# adm sub active --tg-id 5294854527 --tariff sub_free
# adm sub active --tg-id 5294854527 --tariff sub_12m

@sub.command(name="active")
@click.option("--tg-id", type=int, required=True, help="Telegram ID пользователя")
@click.option("--tariff", default="sub_1m", help="Слаг тарифа (например: sub_free, sub_1m, sub_3m)")
@click.option("--days", type=int, default=None, help="Количество дней подписки (перекрывает значение из конфига тарифов)")
def sub_active(tg_id, tariff, days):
    """Активировать или продлить подписку пользователю по Telegram ID с авторасчетом дней из tariffs.json."""

    clean_tariff = tariff.strip().lower()

    # 1. ДИНАМИЧЕСКИЙ РАСЧЕТ ДНЕЙ ИЗ ВАШЕГО TARIFFS.JSON
    if days is None:
        # Пытаемся найти файл тарифов по относительным путям проекта
        json_paths = [
            "ulysses-backend/app/tariffs.json",
            "app/tariffs.json",
            "../app/tariffs.json"
        ]
        tariff_config = None
        for path in json_paths:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    tariff_config = json.load(f)
                break

        if tariff_config and clean_tariff in tariff_config:
            days = tariff_config[clean_tariff]["days"]
            console.print(f"[dim]⚙️ Из tariffs.json автоматически загружен срок: {days} дней для тарифа {clean_tariff}[/dim]")
        else:
            days = 30  # Безопасный дефолт, если файл не найден или слаг не совпал
            console.print(f"[yellow]⚠️ Тариф '{clean_tariff}' не найден в tariffs.json. Применен дефолт: {days} дней.[/yellow]")

    async def _active():
        from app.services.hiddify_client import HiddifyProvisioner

        async with AsyncSessionLocal() as session:
            try:
                # 2. Извлекаем паспортные данные пользователя по TG ID
                res_user = await session.execute(
                    text("SELECT id, tg_username, hiddify_uuid FROM users WHERE tg_user_id = :tg_id"),
                    {"tg_id": tg_id}
                )
                user_row = res_user.fetchone()

                if not user_row:
                    console.print(f"[red]❌ Ошибка: Пользователь с Telegram ID {tg_id} не найден в СУБД биллинга.[/red]")
                    return

                user_internal_id, tg_username, hiddify_uuid = user_row
                hiddify_uuid_str = str(hiddify_uuid)
                hfm_name = f"tg_{tg_id}"

                now = datetime.now(timezone.utc)

                # 3. Проверяем наличие текущей активной подписки для кумулятивного продления
                sql_check = """
                    SELECT id, expires_at FROM subscriptions
                    WHERE user_id = :user_id AND status = 'active' AND expires_at > :now
                    LIMIT 1
                """
                sub_res = await session.execute(text(sql_check), {"user_id": user_internal_id, "now": now})
                existing_sub = sub_res.fetchone()

                # Считаем целевые дни и даты для отправки на ноду
                if existing_sub:
                    current_sub_id, current_expires = existing_sub
                    new_expires = current_expires + timedelta(days=days)
                    total_remaining_days = (new_expires - now).days
                    if total_remaining_days <= 0:
                        total_remaining_days = days
                else:
                    new_expires = now + timedelta(days=days)
                    total_remaining_days = days

                # 4. СЕТЕВОЙ ШАГ: Синхронизация состояния с ядром Hiddify Manager v2
                console.print(f"[yellow]⏳ Проверка и синхронизация UUID {hiddify_uuid_str} на ноде HFM...[/yellow]")
                provisioner = HiddifyProvisioner()

                # Проверяем физическое наличие пользователя на VPN-сервере
                user_exists_on_node = await provisioner.check_user_exists(hiddify_uuid_str)

                if user_exists_on_node:
                    console.print(f"[cyan]🔄 Профиль найден на ноде. Обновляем лимиты: +{days} дней (всего: {total_remaining_days})...[/cyan]")
                    hiddify_success = await provisioner.create_user(
                        uuid=hiddify_uuid_str,
                        name=hfm_name,
                        package_days=total_remaining_days,
                        usage_limit_gb=500
                    )
                    if hiddify_success:
                        await provisioner.enable_user(hiddify_uuid_str)
                else:
                    console.print(f"[magenta]➕ Профиль отсутствует на ноде (битый/сирота). Физически создаем с нуля на {days} дней...[/magenta]")
                    hiddify_success = await provisioner.create_user(
                        uuid=hiddify_uuid_str,
                        name=hfm_name,
                        package_days=total_remaining_days,
                        usage_limit_gb=500
                    )

                if not hiddify_success:
                    console.print("[red]❌ Ошибка: Нода Hiddify v2 отклонила API-запрос. Отмена изменений в СУБД.[/red]")
                    return

                # 5. ТРАНЗАКЦИЯ СУБД: Фиксируем изменения локально только после успеха в API ноды
                if existing_sub:
                    sql_update = """
                        UPDATE subscriptions
                        SET expires_at = :new_expires, updated_at = :now
                        WHERE id = :sub_id
                    """
                    await session.execute(text(sql_update), {"new_expires": new_expires, "now": now, "sub_id": current_sub_id})
                    console.print(f"[green]✅ Активная подписка (ID: {current_sub_id}) успешно продлена на {days} дней![/green]")
                else:
                    sql_insert = """
                        INSERT INTO subscriptions (user_id, tariff_slug, status, starts_at, expires_at, activated_at, node_id)
                        VALUES (:user_id, :tariff, 'active', :now, :new_expires, :now, 'main')
                    """
                    await session.execute(text(sql_insert), {
                        "user_id": user_internal_id, "tariff": clean_tariff, "new_expires": new_expires, "now": now
                    })
                    console.print(f"[green]✅ Создана новая активная подписка для @{tg_username or tg_id} и синхронизирована с VPN![/green]")

                await session.commit()
                console.print(f"📅 Новая дата окончания доступа: [bold yellow]{new_expires.strftime('%Y-%m-%d %H:%M')}[/bold yellow]")

            except Exception as err:
                await session.rollback()
                console.print(f"[red]❌ Критический сбой при активации подписки: {err}[/red]")

    asyncio.run(_active())

# ========================


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
            try:
                result = await session.execute(text(sql_select))
                rows = list(result.fetchall())  # Явно приводим к обычному list

                # Жесткая и надежная проверка на пустоту списка
                if len(rows) == 0:
                    console.print("\n[green]✅ Зависших подписок (provisioning) в системе не обнаружено.[/green]\n")
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

            except Exception as select_err:
                console.print(f"[red]❌ Ошибка при чтении из СУБД: {select_err}[/red]")

    asyncio.run(_pending_logic())



@sub.command(name="revoke")
@click.option("--user-id", type=int, required=True, help="ID пользователя из таблицы users")
def sub_revoke(user_id):
    """Принудительно отозвать (аннулировать) все active подписки пользователя.

    Пример: uadmin sub revoke --user-id 153
    """
    async def _revoke():
        from app.services.hiddify_client import HiddifyProvisioner

        async with AsyncSessionLocal() as session:
            try:
                # 1. Проверяем наличие активных подписок и забираем UUID для API
                sql_check = """
                    SELECT s.id, u.hiddify_uuid
                    FROM subscriptions s
                    JOIN users u ON s.user_id = u.id
                    WHERE s.user_id = :user_id AND s.status = 'active'
                """
                res = await session.execute(text(sql_check), {"user_id": user_id})
                rows = res.fetchall()

                if not rows:
                    console.print(f"[yellow]⚠️ У пользователя с ID {user_id} нет active подписок для отзыва.[/yellow]")
                    return

                # Извлекаем UUID из первой записи (он один на всю жизнь пользователя)
                hiddify_uuid = str(rows[0][1])

                # 2. СЕТЕВОЙ ШАГ: Сначала удаляем/блокируем пользователя в Hiddify Manager
                console.print(f"[yellow]⏳ Отзыв прав доступа на ноде Hiddify для UUID {hiddify_uuid}...[/yellow]")
                provisioner = HiddifyProvisioner()
                hiddify_success = await provisioner.delete_user(uuid=hiddify_uuid)

                if not hiddify_success:
                    console.print("[red]❌ Ошибка: Нода Hiddify v2 отклонила запрос на отзыв подписки. Отмена транзакции СУБД.[/red]")
                    return

                # 3. ТРАНЗАКЦИЯ СУБД: Меняем статус локально только после успешного сетевого ответа
                now = datetime.now(timezone.utc)
                sql_update = """
                    UPDATE subscriptions
                    SET status = 'cancelled', updated_at = :now
                    WHERE user_id = :user_id AND status = 'active'
                """
                await session.execute(text(sql_update), {"user_id": user_id, "now": now})
                await session.commit()

                sub_ids = [str(r[0]) for r in rows]
                console.print(f"[green]✅ Успешно отозваны подписки со статусом active (ID: {', '.join(sub_ids)}) для пользователя {user_id}.[/green]")
                console.print("[green]🔒 Доступ на VPN-серверах заблокирован синхронно.[/green]")

            except Exception as err:
                await session.rollback()
                console.print(f"[red]❌ Критический сбой при отзыве подписки: {err}[/red]")

    asyncio.run(_revoke())

# ============================================================
# 👻 КОМАНДА: БИТЫЕ ПРОФИЛИ БЕЗ ПОДПИСОК (ORPHANS)
# ============================================================
@sub.command(name="orphans")
def sub_orphans():
    """Вывести список 'битых' пользователей, у которых нет ни одной подписки в БД."""
    async def _find_orphans():
        async with AsyncSessionLocal() as session:
            # Ищем пользователей, для которых нет совпадений в таблице subscriptions
            sql_orphans = """
                SELECT u.id, u.tg_user_id, u.tg_username, u.email, u.created_at, u.hiddify_uuid
                FROM users u
                LEFT JOIN subscriptions s ON s.user_id = u.id
                WHERE s.id IS NULL
                ORDER BY u.id DESC
            """
            try:
                result = await session.execute(text(sql_orphans))
                rows = list(result.fetchall())

                if len(rows) == 0:
                    console.print("\n[green]✨ Идеально! 'Битых' пользователей без подписок в системе не обнаружено.[/green]\n")
                    return

                table = Table(title="👻 Битые профили (Пользователи без подписок)")
                table.add_column("User ID", style="dim", justify="center")
                table.add_column("Telegram ID", style="cyan")
                table.add_column("Username", style="green")
                table.add_column("Email", style="blue")
                table.add_column("Hiddify UUID", style="yellow")
                table.add_column("Зарегистрирован", style="magenta")

                for r in rows:
                    u_id, tg_id, username, email, created_at, hf_uuid = r

                    created_str = created_at.strftime("%Y-%m-%d %H:%M") if created_at else "-"

                    table.add_row(
                        str(u_id),
                        str(tg_id or "-"),
                        f"@{username}" if username else "-",
                        email if email else "-",
                        str(hf_uuid),
                        created_str
                    )
                console.print(table)
                console.print("[yellow]➜ Подсказка: Вы можете починить их, выдав подписку вручную:[/yellow]")
                console.print("[yellow]   adm sub active --user-id ID --days 30[/yellow]\n")

            except Exception as err:
                console.print(f"[red]❌ Ошибка при поиске битых профилей: {err}[/red]")

    asyncio.run(_find_orphans())
