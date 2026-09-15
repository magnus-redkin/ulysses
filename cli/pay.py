# cli/pay.py

import asyncio
import click
import uuid as uuid_lib
from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from app.database import AsyncSessionLocal

console = Console()

CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)


@click.group(context_settings=CONTEXT_SETTINGS)
def pay():
    """Управление платежными инвойсами и интеграцией Platega.io."""
    pass


pay.get_usage = lambda ctx: "uadmin pay [ОПЦИИ] КОМАНДА [ARGS]..."


@pay.command(name="invoice")
@click.option("--tg-id", type=int, required=True, help="Telegram ID пользователя")
@click.option("--tariff", default="sub_1m", help="Слаг тарифа (sub_1m, sub_3m, sub_12m)")
@click.option("--currency", default="RUB", help="Валюта платежа (RUB, USD, EUR, USDT)")
@click.option("--amount", type=float, default=None, help="Сумма (иначе из tariffs.json)")
def pay_invoice(tg_id, tariff, currency, amount):
    """Сгенерировать тестовую мультивалютную платежную ссылку для пользователя."""
    async def _invoice():
        import json
        import os
        from app.platega.platega_service import PlategaPaymentService

        async with AsyncSessionLocal() as session:
            res_user = await session.execute(
                text("SELECT id, email FROM users WHERE tg_user_id = :tg_id"),
                {"tg_id": tg_id}
            )
            user_row = res_user.fetchone()
            if not user_row:
                console.print(f"[red]❌ Пользователь с TG ID {tg_id} не найден.[/red]")
                return
            user_internal_id, db_email = user_row

            if amount is None:
                json_path = "app/tariffs.json"
                if not os.path.exists(json_path):
                    json_path = "../app/tariffs.json"
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        t_config = json.load(f)
                    amount = t_config[tariff.lower().strip()]["price"]
                except Exception:
                    amount = 199.0

            new_attempt_id = str(uuid_lib.uuid4())
            await session.execute(
                text("""
                    INSERT INTO payment_attempts
                        (id, email, user_id, tariff_slug, amount, currency, status, created_at, updated_at)
                    VALUES
                        (:id, :email, :uid, :tariff, :amount, :currency, 'pending', NOW(), NOW())
                """),
                {
                    "id": new_attempt_id,
                    "email": db_email or f"tg_{tg_id}@ulysses.internal",
                    "uid": user_internal_id,
                    "tariff": tariff,
                    "amount": amount,
                    "currency": currency.upper().strip()
                }
            )
            await session.commit()

            console.print(f"[yellow]⏳ Запрос к Platega API ({currency.upper()} {amount})...[/yellow]")
            pay_service = PlategaPaymentService()

            res_link = await pay_service.create_invoice_link(
                amount=amount,
                currency=currency,
                attempt_id=new_attempt_id,
                tariff_name=tariff,
                user_telegram_id=tg_id,
            )

            if res_link and "url" in res_link:
                # Сохраняем tx_id, чтобы потом можно было опросить статус
                await session.execute(
                    text("UPDATE payment_attempts SET provider_tx_id = :tx WHERE id = :id"),
                    {"tx": res_link.get("transactionId"), "id": new_attempt_id}
                )
                await session.commit()

                console.print(f"\n[bold green]🎉 Платежная сессия создана![/bold green]")
                console.print(f"🆔 ID инвойса: [cyan]{new_attempt_id}[/cyan]")
                console.print(f"🆔 Platega txId: [yellow]{res_link.get('transactionId')}[/yellow]")
                console.print(f"🔗 [bold magenta]{res_link.get('url')}[/bold magenta]\n")
            else:
                console.print("[red]❌ Platega отклонила запрос.[/red]")

    asyncio.run(_invoice())


@pay.command(name="check")
@click.argument("invoice_id", type=str)
def pay_check(invoice_id):
    """Опросить статус инвойса в Platega (если сохранён provider_tx_id)."""
    async def _check():
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                text("SELECT provider_tx_id, status FROM payment_attempts WHERE id = :id"),
                {"id": invoice_id}
            )
            row = res.fetchone()
            if not row:
                console.print(f"[red]❌ Инвойс {invoice_id} не найден.[/red]")
                return
            tx_id, local_status = row

            console.print(f"📊 Локальный статус: [bold cyan]{local_status}[/bold cyan]")
            console.print(f"🆔 provider_tx_id: [yellow]{tx_id or '—'}[/yellow]")
            if not tx_id:
                console.print("[yellow]⚠️ Нет tx_id — платёж не был инициализирован в Platega.[/yellow]")

    asyncio.run(_check())

@pay.command(name="show")
@click.argument("attempt_id", type=str)
def pay_show(attempt_id):
    """Полная информация о конкретном платеже (для разборок с Platega)."""
    async def _run():
        try:
            attempt_uuid = uuid_lib.UUID(attempt_id.strip())
        except (ValueError, AttributeError):
            console.print(f"[red]❌ Неверный UUID: {attempt_id}[/red]")
            return

        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("""
                SELECT pa.id, pa.status, pa.amount, pa.currency, pa.tariff_slug,
                       pa.email, pa.provider_tx_id, pa.created_at, pa.updated_at,
                       u.id AS user_id, u.tg_user_id, u.tg_username
                FROM payment_attempts pa
                LEFT JOIN users u ON u.id = pa.user_id
                WHERE pa.id = :id
            """), {"id": attempt_uuid})).fetchone()

            if not row:
                console.print(f"[red]❌ Платёж {attempt_id} не найден[/red]")
                return

            (pid, st, amt, cur, slug, email, tx_id,
             created, updated, uid, tg_id, uname) = row

            st_color = {
                "success": "[green]success[/green]",
                "pending": "[yellow]pending[/yellow]",
                "processing": "[cyan]processing[/cyan]",
                "cancelled": "[dim]cancelled[/dim]",
                "failed": "[red]failed[/red]",
            }.get(st, f"[italic]{st}[/italic]")

            console.print(f"\n💳 Платёж [cyan]{pid}[/cyan]\n")
            console.print(f"  Статус:           {st_color}")
            console.print(f"  Тариф:            {slug}")
            console.print(f"  Сумма:            {amt:.2f} {cur}")
            console.print(f"  Email:            {email or '-'}")
            console.print(f"  Пользователь:     ID {uid}, TG {tg_id or '-'} (@{uname or '-'})")
            console.print(f"  Platega txId:     [yellow]{tx_id or '—'}[/yellow]")
            if tx_id:
                console.print(
                    f"  Кабинет Platega:  https://app.platega.io/ "
                    f"[dim](искать транзакцию по txId)[/dim]"
                )
            console.print(
                f"  Создан:           {created.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                if created else "  Создан:           —"
            )
            console.print(
                f"  Обновлён:         {updated.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                if updated else "  Обновлён:         —"
            )
            console.print("")

    asyncio.run(_run())

@pay.command(name="activate")
@click.argument("attempt_id", type=str)
@click.option("--force", is_flag=True,
              help="Активировать без проверки в Platega (использовать ТОЛЬКО после ручной проверки в кабинете).")
@click.option("--tx-id", default=None, help="Platega transactionId (если не сохранён в БД).")
def pay_activate(attempt_id, force, tx_id):
    """Принудительно активировать подписку по застрявшему payment_attempt.

    Идемпотентно: если статус уже 'success' — ничего не делает.
    Использует ту же логику активации, что и вебхук Platega.
    """
    async def _activate():
        from app.services.platega_webhook_handler import _activate_subscription

        try:
            order_uuid = uuid_lib.UUID(attempt_id.strip())
        except (ValueError, AttributeError):
            console.print(f"[red]❌ Неверный UUID: {attempt_id}[/red]")
            return

        async with AsyncSessionLocal() as session:
            row = (await session.execute(
                text("""
                    SELECT id, status, user_id, tariff_slug, amount, provider_tx_id
                    FROM payment_attempts WHERE id = :id
                """),
                {"id": order_uuid}
            )).fetchone()

            if not row:
                console.print(f"[red]❌ Инвойс {attempt_id} не найден[/red]")
                return

            inv_id, status, user_id, tariff_slug, amount, db_tx_id = row
            console.print(
                f"📄 Инвойс: status=[bold cyan]{status}[/bold cyan], "
                f"user_id={user_id}, tariff={tariff_slug}, amount={amount}, tx_id={db_tx_id or '—'}"
            )

            if status == "success":
                console.print("[yellow]ℹ️ Инвойс уже success. Ничего не делаю.[/yellow]")
                return
            if status not in ("pending", "processing"):
                console.print(f"[red]❌ Статус '{status}' не подлежит активации.[/red]")
                return

            if not force:
                console.print(
                    "[red]❌ Без --force активация не выполняется.[/red]\n"
                    "[dim]Проверь оплату в кабинете Platega (CONFIRMED?) и запусти снова:\n"
                    f"    adm pay activate {attempt_id} --force[/dim]"
                )
                return

            effective_tx = tx_id or db_tx_id or f"manual-{order_uuid}"

            console.print(
                f"[yellow]🚀 Активация: user_id={user_id}, tariff={tariff_slug}, "
                f"provider_tx_id={effective_tx}[/yellow]"
            )
            await _activate_subscription(
                session,
                order_id=inv_id,
                user_id=user_id,
                tariff_slug=tariff_slug,
                provider_tx_id=effective_tx,
            )
            console.print("[bold green]✅ Подписка активирована.[/bold green]")

    asyncio.run(_activate())


if __name__ == "__main__":
    pay(prog_name="uadmin pay")
