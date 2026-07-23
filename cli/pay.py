# ulysses-backend/cli/pay.py

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
@click.option("--amount", type=float, default=None, help="Сумма (опционально, иначе берется из tariffs.json)")
def pay_invoice(tg_id, tariff, currency, amount):
    """Сгенерировать тестовую мультивалютную платежную ссылку для пользователя."""
    async def _invoice():
        import json
        import os
        from app.private.platega_service import PlategaPaymentService

        async with AsyncSessionLocal() as session:
            # 1. Находим пользователя
            res_user = await session.execute(text("SELECT id, email FROM users WHERE tg_user_id = :tg_id"), {"tg_id": tg_id})
            user_row = res_user.fetchone()
            if not user_row:
                console.print(f"[red]❌ Ошибка: Пользователь с TG ID {tg_id} не найден в СУБД.[/red]")
                return
            user_internal_id, db_email = user_row

            # 2. Определяем цену из tariffs.json, если не передана вручную
            if amount is None:
                json_path = "ulysses-backend/app/tariffs.json"
                if not os.path.exists(json_path): json_path = "app/tariffs.json"

                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        t_config = json.load(f)
                    amount = t_config[tariff.lower().strip()]["price"]
                except:
                    amount = 199.0  # Дефолт

            # 3. Создаем запись инвойса в PostgreSQL
            new_attempt_id = str(uuid_lib.uuid4())
            sql_insert = """
                INSERT INTO payment_attempts (id, email, user_id, tariff_slug, amount, currency, status, created_at, updated_at)
                VALUES (:id, :email, :uid, :tariff, :amount, :currency, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
            await session.execute(text(sql_insert), {
                "id": new_attempt_id,
                "email": db_email if db_email else f"tg_{tg_id}@ulysses.internal",
                "uid": user_internal_id,
                "tariff": tariff,
                "amount": amount,
                "currency": currency.upper().strip()
            })
            await session.commit()

            # 4. Вызываем наш асинхронный платежный сервис
            console.print(f"[yellow]⏳ Запрос к Platega API на генерацию ссылки ({currency.upper()} {amount})...[/yellow]")
            pay_service = PlategaPaymentService()

            # Для тестов мультивалютности выберем метод КРИПТА (13) или МЕЖДУНАРОДНЫЕ (12), если валюта не RUB
            pay_method = 10 if currency.upper() == "RUB" else 13

            res_link = await pay_service.create_invoice_link(
                amount=amount,
                currency=currency,
                attempt_id=new_attempt_id,
                tariff_name=tariff,
                method=pay_method
            )

            if res_link and "redirect" in res_link:
                console.print(f"\n[bold green]🎉 Платежная сессия успешно инициализирована![/bold green]")
                console.print(f"🆔 ID Инвойса (Ulysses): [cyan]{new_attempt_id}[/cyan]")
                console.print(f"🆔 ID Транзакции (Platega): [yellow]{res_link.get('transactionId')}[/yellow]")
                console.print(f"🔗 [bold magenta]ССЫЛКА НА СТРАНИЦУ ОПЛАТЫ:[/bold magenta]")
                console.print(f"[bold white on magenta] {res_link.get('redirect')} [/bold white on magenta]\n")
            else:
                console.print("[red]❌ Ошибка: Агрегатор Platega отклонил запрос на генерацию ссылки.[/red]")

    asyncio.run(_invoice())


@pay.command(name="check")
@click.argument("invoice_id", type=str)
def pay_check(invoice_id):
    """Принудительно опросить статус инвойса напрямую в API Platega."""
    async def _check():
        from app.private.platega_service import PlategaPaymentService

        async with AsyncSessionLocal() as session:
            res = await session.execute(text("SELECT provider_tx_id, status FROM payment_attempts WHERE id = :id"), {"id": invoice_id})
            row = res.fetchone()
            if not row:
                console.print(f"[red]❌ Ошибка: Инвойс {invoice_id} не найден в СУБД Ulysses.[/red]")
                return
            tx_id, local_status = row

            if not tx_id:
                console.print("[yellow]⚠️ У инвойса нет привязанного ID транзакции провайдера (платеж не начинался).[/yellow]")
                return

            pay_service = PlategaPaymentService()
            status_data = await pay_service.verify_payment_status(tx_id)

            if status_data:
                console.print(f"\n📊 [Platega API] Статус транзакции {tx_id}:")
                console.print(f"   • Статус в Platega: [bold yellow]{status_data.get('status')}[/bold yellow]")
                console.print(f"   • Локальный статус в СУБД: [bold cyan]{local_status}[/bold cyan]")
            else:
                console.print("[red]❌ Не удалось получить данные от Platega API.[/red]")

    asyncio.run(_check())


if __name__ == "__main__":
    pay(prog_name="uadmin pay")
