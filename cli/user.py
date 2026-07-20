# ulysses-backend/cli/user.py

import click
from rich.console import Console
from rich.table import Table

console = Console()

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
        hiddify_success = False
        try:
            provisioner = HiddifyProvisioner()
            hiddify_success = await provisioner.create_user(
                uuid=new_uuid,
                name=f"tg_{tg_id}"
            )

            if hiddify_success:
                console.print(f"[green]✅ Успешно: Профиль активирован в Hiddify Manager v2 под именем tg_{tg_id}![/green]")
            else:
                console.print("[red]❌ Предупреждение: Нода Hiddify v2 отклонила POST-запрос создания.[/red]")
        except Exception as hf_err:
            console.print(f"[red]❌ Сетевой сбой транспорта при связи с API Hiddify v2: {hf_err}[/red]")

        # 5. ОКОНЧАТЕЛЬНАЯ СБОРКА И ВЫВОД ПАРАДНОЙ ССЫЛКИ ПОДПИСКИ
        base_domain = "ulysses.best"
        client_sub_url = f"https://{base_domain}/subscription/{new_uuid}/"

        console.print(f"\n[bold green]🎉 Каскад создания пользователя полностью завершен![/bold green]")
        console.print(f"👤 Telegram ID: [cyan]{tg_id}[/cyan] | Юзернейм: [cyan]@{clean_username}[/cyan]")
        console.print(f"🔑 Персональный UUID: [yellow]{new_uuid}[/yellow]")
        console.print(f"🔗 [bold magenta]ФИНАЛЬНАЯ ССЫЛКА ДЛЯ КЛИЕНТА (Hiddify/Sing-box):[/bold magenta]")
        console.print(f"[bold white on magenta] {client_sub_url} [/bold white on magenta]\n")

        # 6. УВЕДОМЛЕНИЕ ПОЛЬЗОВАТЕЛЯ В ТЕЛЕГРАМ-БОТ
        if hiddify_success:
            try:
                from app.services.telegram_bot import send_telegram_message

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

    import asyncio
    asyncio.run(_create_user_pipeline())


# ============================================================
# 📋 КОМАНДА: ПРОСМОТР СПИСКА ПОЛЬЗОВАТЕЛЕЙ (LIST)
# ============================================================
@user.command(name="list")
def user_list():
    """Вывести список всех зарегистрированных пользователей биллинга."""
    async def _list_users():
        from sqlalchemy import text
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT id, tg_user_id, tg_username, email, hiddify_uuid, created_at FROM users ORDER BY id ASC"))
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

    import asyncio
    asyncio.run(_list_users())


# ============================================================
# ❌ КОМАНДА: УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ (DELETE)
# ============================================================
@user.command(name="delete")
@click.option("--tg-id", type=int, required=True, help="Telegram ID удаляемого пользователя")
def user_delete(tg_id):
    """Удалить пользователя из СУБД и каскадно аннулировать его на ноде HFM."""
    async def _delete_user_pipeline():
        from sqlalchemy import text
        from app.database import AsyncSessionLocal
        from app.services.hiddify_client import HiddifyProvisioner

        console.print(f"[yellow]⏳ Запуск удаления пользователя с TG ID {tg_id}...[/yellow]")

        async with AsyncSessionLocal() as session:
            # Ищем UUID перед удалением для синхронизации с HFM
            res = await session.execute(text("SELECT hiddify_uuid FROM users WHERE tg_user_id = :tg_id"), {"tg_id": tg_id})
            user_row = res.fetchone()

            if not user_row:
                console.print(f"[red]❌ Ошибка: Пользователь с TG ID {tg_id} не найден в СУБД биллинга.[/red]")
                return

            uuid_to_delete = user_row[0]

            try:
                # Каскадно удаляем из локальной PostgreSQL
                await session.execute(text("DELETE FROM users WHERE tg_user_id = :tg_id"), {"tg_id": tg_id})
                await session.commit()
                console.print("[green]🗑️ Запись успешно удалена из локальной PostgreSQL.[/green]")
            except Exception as e:
                await session.rollback()
                console.print(f"[red]❌ Сбой СУБД при удалении: {e}[/red]")
                return

        # Удаляем с удаленной ноды Hiddify Manager v2
        try:
            provisioner = HiddifyProvisioner()
            hiddify_success = await provisioner.delete_user(uuid=uuid_to_delete)
            if hiddify_success:
                console.print("[green]✅ Успешно: Пользователь деактивирован и удален из ядра Hiddify Manager v2![/green]")
            else:
                console.print("[yellow]⚠️ Предупреждение: Панель HFM не смогла удалить UUID (возможно, он уже был стерт).[/yellow]")
        except Exception as hf_err:
            console.print(f"[red]❌ Сетевой сбой при связи с API Hiddify v2: {hf_err}[/red]")

    import asyncio
    asyncio.run(_delete_user_pipeline())

# ============================================================
# 🔗 КОМАНДА: ПОЛУЧИТЬ ССЫЛКУ ПОДПИСКИ (LINK)
# ============================================================
@user.command(name="link")
@click.option("--tg-id", type=int, required=True, help="Telegram ID пользователя")
def user_link(tg_id):
    """Получить окончательную парадную ссылку подписки для существующего пользователя."""
    async def _get_user_link():
        from sqlalchemy import text
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            # Ищем UUID пользователя по его Telegram ID
            res = await session.execute(
                text("SELECT tg_username, hiddify_uuid FROM users WHERE tg_user_id = :tg_id"),
                {"tg_id": tg_id}
            )
            row = res.fetchone()

            if not row:
                console.print(f"[red]❌ Ошибка: Пользователь с TG ID {tg_id} не найден в базе биллинга![/red]")
                return

            tg_username, hiddify_uuid = row

            # Собираем эталонную парадную ссылку подписки
            base_domain = "ulysses.best"
            client_sub_url = f"https://{base_domain}/subscription/{hiddify_uuid}/"

            console.print(f"\n[bold green]🔑 Сетевой паспорт пользователя успешно извлечен![/bold green]")
            console.print(f"👤 Пользователь: [cyan]@{tg_username if tg_username else '—'}[/cyan] (TG ID: {tg_id})")
            console.print(f"🆔 UUID в системе: [yellow]{hiddify_uuid}[/yellow]")
            console.print(f"🔗 [bold magenta]ДЕЙСТВУЮЩАЯ ССЫЛКА ДЛЯ ИМПОРТА В HIDDIFY NEXT:[/bold magenta]")
            console.print(f"[bold white on magenta] {client_sub_url} [/bold white on magenta]\n")

    import asyncio
    asyncio.run(_get_user_link())
