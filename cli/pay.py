# cli/pay.py

# МОНИТОРИНГ ТРАНЗАКЦИЙ И СТАТУСОВ ПЛАТЕЖНЫХ СЧЕТОВ CLI PAY
# Данный модуль предоставляет инструменты оператора для проверки статуса инвойсов.
# Выполняет HTTP-запросы к административному контуру бэкенда для сверки локального
# состояния счетов с реальными ответами шлюзов эквайринга в режиме реального времени.

import asyncio
import httpx
import click
from rich.console import Console
from rich.panel import Panel

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"

# Настройки контекста для жесткого переопределения ключей хелпа Click на uadmin
CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

@click.group(name="pay", context_settings=CONTEXT_SETTINGS)
def pay():
    """Управление платежами и интеграцией с эквайрингом.

    Использование: uadmin pay КОМАНДА [АРГУМЕНТЫ]...
    """
    pass

# Переопределяем отображение имени группы в подсказках хелпа нижнего уровня
pay.get_usage = lambda ctx: "uadmin pay [ОПЦИИ] КОМАНДА [ARGS]..."


@pay.command(name="info")
@click.argument("order_id", required=True)
def pay_info(order_id):
    """Запросить актуальный статус инвойса у платёжной системы через бэкенд.

    Пример: uadmin pay info 3c9a41b5-6f8d-4be4-96f1-65a2a89d36f0
    """
    console.print(f"[yellow]⏳ Запрос статуса платежа {order_id}...[/yellow]")

    async def _info():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{BACKEND_API_URL}/api/admin/pay/info/{order_id}"
                )

                if response.status_code == 404:
                    console.print(f"[red]❌ Инвойс {order_id} не найден.[/red]")
                    return
                elif response.status_code != 200:
                    console.print(f"[red]❌ Ошибка: HTTP {response.status_code}[/red]")
                    return

                data = response.json()

                # Корректируем под реальные ключи нашего эндпоинта admin.py
                status = data.get("gateway_status", data.get("local_status", "unknown")).lower()
                amount = data.get("local_amount", "-")
                currency = data.get("currency", "RUB")
                provider = data.get("provider", "Platega / Gate")
                created_at = data.get("checked_at", "-")
                local_status = data.get("local_status", "-")

                if status in ("success", "paid"):
                    status_str = "[bold green]✅ ОПЛАЧЕН[/bold green]"
                elif status in ("wait", "pending"):
                    status_str = "[bold yellow]⏳ ОЖИДАЕТ ОПЛАТЫ[/bold yellow]"
                else:
                    status_str = f"[bold red]❌ {status.upper()}[/bold red]"

                content = (
                    f"[cyan]Платёжный шлюз :[/cyan] {provider}\n"
                    f"[cyan]ID Инвойса     :[/cyan] {order_id}\n"
                    f"[cyan]Сумма          :[/cyan] {amount} {currency}\n"
                    f"[cyan]Дата проверки  :[/cyan] {created_at}\n"
                    f"[cyan]Статус у кассы :[/cyan] {status_str}\n"
                    f"[cyan]Локальный статус:[/cyan] {local_status}"
                )

                console.print(Panel(content, title="💳 Информация о платеже", border_style="cyan", expand=False))

        except httpx.ConnectError:
            console.print("[red]❌ Бэкенд не запущен.[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка: {e}[/red]")

    asyncio.run(_info())


if __name__ == "__main__":
    pay(prog_name="uadmin pay")
