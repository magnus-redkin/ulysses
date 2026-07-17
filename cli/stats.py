# cli/stats.py

# АГРЕГАЦИЯ СТАТИСТИКИ И МОНИТОРИНГ ОЧЕРЕДЕЙ ВЫДАЧИ CLI STATS
# Модуль собирает верхнеуровневые бизнес-метрики системы через API бэкенда.
# При обнаружении зависших подписок или транзакций в карантине, выполняет прямой
# запрос к PostgreSQL для вывода детальной таблицы инцидентов с логами ошибок нод.

import asyncio
import httpx
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from sqlalchemy import text
from app.database import AsyncSessionLocal

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"

# Настройки контекста для жесткого переопределения ключей хелпа Click на uadmin
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
            # 1. Запрашиваем агрегированные данные из API бэкенда
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{BACKEND_API_URL}/api/admin/stats")

                if response.status_code != 200:
                    console.print(f"[red]❌ Ошибка получения статистики: HTTP {response.status_code}[/red]")
                    return

                data = response.json()
                pending_count = data.get("pending_subscriptions", 0)

                console.print(Panel.fit(
                    "[bold blue]📊 Ulysses VPN - Статистика[/bold blue]",
                    border_style="blue"
                ))

                table = Table(title="Общая статистика")
                table.add_column("Показатель", style="cyan")
                table.add_column("Значение", style="green")

                table.add_row("👥 Всего пользователей", str(data.get("total_users", 0)))
                table.add_row("✅ Активных подписок", str(data.get("active_subscriptions", 0)))

                # Подсвечиваем желтым/красным, если есть зависшие
                pending_style = "yellow" if pending_count > 0 else "green"
                table.add_row("⏳ В обработке (Ожидают/Зависли)", f"[{pending_style}]{pending_count}[/{pending_style}]")

                console.print(table)
                console.print("")

                # 2. Если есть подписки в обработке, выводим детализацию напрямую из БД
                if pending_count > 0:
                    console.print("[bold yellow]⚠️ Обнаружены подписки, требующие внимания администратора:[/bold yellow]")

                    async with AsyncSessionLocal() as session:
                        sql = """
                            SELECT s.id, s.user_id, u.email, u.tg_user_id, s.tariff_slug, s.status,
                                   s.provisioning_attempts, s.last_provisioning_at, s.provisioning_error
                            FROM subscriptions s
                            JOIN users u ON s.user_id = u.id
                            WHERE s.status IN ('provisioning', 'pending_payment')
                            ORDER BY s.id DESC
                        """
                        result = await session.execute(text(sql))
                        pending_rows = result.fetchall()

                        p_table = Table(title="🔍 Детализация зависших подписок")
                        p_table.add_column("Sub ID", style="dim", justify="center")
                        p_table.add_column("User ID (Контакты)", style="cyan")
                        p_table.add_column("Тариф", style="blue")
                        p_table.add_column("Статус в БД", style="magenta")
                        p_table.add_column("Попыток", style="yellow", justify="center")
                        p_table.add_column("Последняя ошибка ноды", style="red")

                        for row in pending_rows:
                            s_id, u_id, email, tg_id, tariff, status, attempts, last_at, error = row

                            # Формируем контактную информацию
                            contact = f"ID {u_id} ("
                            if tg_id: contact += f"TG: {tg_id}"
                            if email: contact += f" | {email}"
                            contact += ")"

                            err_msg = error if error else "Ожидает первой попытки / Оплаты"
                            if last_at:
                                err_msg = f"[{last_at.strftime('%m-%d %H:%M')}] {err_msg}"

                            p_table.add_row(
                                str(s_id), contact, tariff, status,
                                str(attempts or 0), err_msg
                            )

                        console.print(p_table)
                        console.print("[yellow]➜ Подсказка: Попробуйте протолкнуть их командой: uadmin fix pending --force[/yellow]")

        except httpx.ConnectError:
            console.print("[red]❌ Ошибка подключения к Backend API. Убедитесь, что бэкенд запущен.[/red]")
        except Exception as e:
            console.print(f"[red]❌ Ошибка выполнения CLI команды: {e}[/red]")

    asyncio.run(_stats())


if __name__ == "__main__":
    # Настройка автономного запуска под именем uadmin
    stats(prog_name="uadmin stats")
