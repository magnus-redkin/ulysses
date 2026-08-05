"""
АГРЕГАЦИЯ СТАТИСТИКИ CLI STATS
Тонкий клиент — получает данные через защищённый API бэкенда.
"""

import asyncio
import os
import httpx
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from dotenv import load_dotenv
load_dotenv()

console = Console()
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000")
API_KEY = os.getenv("HOST_API_KEY", "")

CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)



@click.command(context_settings=CONTEXT_SETTINGS)
def stats():
    """Показать общую статистику Ulysses VPN и зависшие подписки.

    Пример: uadmin stats
    """
    async def _stats():
        try:
            headers = {"X-API-Key": API_KEY}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{BACKEND_API_URL}/api/admin/stats",
                    headers=headers,
                    params={"verbose": "true"}
                )

                if resp.status_code != 200:
                    console.print(f"[red]❌ Ошибка получения статистики: HTTP {resp.status_code}[/red]")
                    if resp.status_code == 401:
                        console.print("[dim]Проверьте HOST_API_KEY[/dim]")
                    return

                data = resp.json()
                stats_data = data.get("stats", {})

                console.print(Panel.fit(
                    "[bold blue]📊 Ulysses VPN - Статистика[/bold blue]",
                    border_style="blue"
                ))

                table = Table(title="Общая статистика")
                table.add_column("Показатель", style="cyan")
                table.add_column("Значение", style="green")

                pending_count = stats_data.get("pending_subscriptions", 0)
                table.add_row("👥 Всего пользователей", str(stats_data.get("total_users", 0)))
                table.add_row("✅ Активных подписок", str(stats_data.get("active_subscriptions", 0)))

                pending_style = "yellow" if pending_count > 0 else "green"
                table.add_row("⏳ В обработке (Ожидают/Зависли)", f"[{pending_style}]{pending_count}[/{pending_style}]")
                console.print(table)

                # Детализация, если есть
                pending_details = data.get("pending_details", [])
                if pending_details:
                    console.print("")
                    console.print("[bold yellow]⚠️ Обнаружены подписки, требующие внимания администратора:[/bold yellow]")

                    p_table = Table(title="🔍 Детализация зависших подписок")
                    p_table.add_column("Sub ID", style="dim", justify="center")
                    p_table.add_column("Пользователь (Контакты)", style="cyan")
                    p_table.add_column("Тариф", style="blue")
                    p_table.add_column("Статус в БД", style="magenta")
                    p_table.add_column("Попыток", style="yellow", justify="center")
                    p_table.add_column("Последняя ошибка ноды", style="red")

                    for item in pending_details:
                        tg_id = item.get("tg_user_id")
                        email = item.get("email")
                        contact_parts = []
                        if tg_id:
                            contact_parts.append(f"TG: {tg_id}")
                        if email:
                            contact_parts.append(email)
                        contact = " | ".join(contact_parts) or "—"

                        last_err = item.get("last_error") or "Ожидает первой попытки"
                        last_at = item.get("last_attempt_at")
                        if last_at:
                            last_err = f"[{last_at}] {last_err}"

                        p_table.add_row(
                            str(item.get("subscription_id", "—")),
                            contact,
                            item.get("tariff_slug", "—"),
                            item.get("status", "—"),
                            str(item.get("attempts", 0)),
                            last_err
                        )

                    console.print(p_table)
                    console.print("[yellow]➜ Используйте: uadmin fix process-pending[/yellow]")
                else:
                    if pending_count == 0:
                        console.print("\n[green]✅ Все подписки обработаны.[/green]")

        except httpx.ConnectError:
            console.print("[red]❌ Ошибка подключения к Backend API. Бэкенд запущен?[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка: {e}[/red]")

    asyncio.run(_stats())

if __name__ == "__main__":
    stats(prog_name="uadmin stats")
