import asyncio
import httpx
import click
from rich.console import Console
from rich.panel import Panel

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"


@click.group(name="pay")
def pay():
    """Управление платежами и интеграцией с эквайрингом"""
    pass


@pay.command(name="info")
@click.argument("order_id", required=True)
def pay_info(order_id):
    """Запросить актуальный статус инвойса у платёжной системы через бэкенд"""
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

                status = data.get("status", "unknown").lower()
                amount = data.get("amount", data.get("local_amount", "-"))
                currency = data.get("currency", "RUB")
                provider = data.get("provider", "Enot.io")
                created_at = data.get("created_at", "-")
                local_status = data.get("local_status", "-")

                if status == "success":
                    status_str = "[bold green]✅ ОПЛАЧЕН[/bold green]"
                elif status in ("wait", "pending"):
                    status_str = "[bold yellow]⏳ ОЖИДАЕТ ОПЛАТЫ[/bold yellow]"
                else:
                    status_str = f"[bold red]❌ {status.upper()}[/bold red]"

                content = (
                    f"[cyan]Платёжный шлюз :[/cyan] {provider}\n"
                    f"[cyan]ID Инвойса     :[/cyan] {order_id}\n"
                    f"[cyan]Сумма          :[/cyan] {amount} {currency}\n"
                    f"[cyan]Дата создания  :[/cyan] {created_at}\n"
                    f"[cyan]Статус у кассы :[/cyan] {status_str}\n"
                    f"[cyan]Локальный статус:[/cyan] {local_status}"
                )

                console.print(Panel(content, title="💳 Информация о платеже", border_style="cyan", expand=False))

        except httpx.ConnectError:
            console.print("[red]❌ Бэкенд не запущен.[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка: {e}[/red]")

    asyncio.run(_info())
