import asyncio
import subprocess
import click
from rich.console import Console
from rich.table import Table
# from app.system_info import collect_system_metrics
from app.system_info import collect_system_metrics

console = Console()


@click.command()
def system_info():
    """Показать системные метрики сервера (диск, RAM, статусы сервисов и топ процессов)"""

    async def _show():
        metrics = await collect_system_metrics()

        # Первая таблица: Общие метрики
        table = Table(title="🖥️ Системные метрики сервера")
        table.add_column("Показатель", style="cyan")
        table.add_column("Значение", style="green")
        table.add_column("Статус", style="yellow")

        disk_pct = metrics.get("disk_free_percent", 0)
        disk_status = "🔴" if disk_pct < 10 else "🟡" if disk_pct < 25 else "🟢"
        table.add_row("💾 Свободно на диске", f"{disk_pct}%", disk_status)

        ram_pct = metrics.get("ram_available_percent", 0)
        ram_status = "🔴" if ram_pct < 10 else "🟡" if ram_pct < 25 else "🟢"
        table.add_row("🧠 Доступно RAM", f"{ram_pct}%", ram_status)

        pg = metrics.get("postgres_status", "UNKNOWN")
        pg_status = "🟢" if pg == "RUNNING" else "🔴"
        table.add_row("🐘 PostgreSQL", pg, pg_status)

        bot = metrics.get("telegram_bot_status", "UNKNOWN")
        bot_status = "🟢" if bot == "RUNNING" else "🔴"
        table.add_row("🤖 Telegram Bot", bot, bot_status)

        api = metrics.get("backend_status", "UNKNOWN")
        api_status = "🟢" if api == "ONLINE" else "🔴"
        table.add_row("⚙️ Backend API", api, api_status)

        overall = "✅ Здорова" if metrics.get("status") == "ok" else "🚨 Проблемы"
        table.add_row("", "", "")
        table.add_row("🏥 Общий статус", overall, "")

        console.print(table)
        console.print("")

        # Вторая таблица: Топ по RAM
        proc_table = Table(title="🧠 ТОП-3 процесса по потреблению RAM")
        proc_table.add_column("PID", style="dim")
        proc_table.add_column("Процент RAM", style="magenta")
        proc_table.add_column("Команда", style="white")

        try:
            # Получаем топ 3 процесса через ps
            cmd = "ps aux --sort=-rss | head -n 4 | tail -n 3 | awk '{print $2 \"|\" $4 \"%|\" $11}'"
            output = subprocess.check_output(cmd, shell=True, text=True)
            for line in output.strip().split("\n"):
                if line:
                    pid, mem, command = line.split("|")
                    # Обрезаем слишком длинный путь команды для красоты
                    short_cmd = command.split("/")[-1]
                    proc_table.add_row(pid, mem, short_cmd)
        except Exception:
            proc_table.add_row("-", "-", "Ошибка получения данных")

        console.print(proc_table)

    asyncio.run(_show())
