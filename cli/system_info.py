# cli/system_info.py

# МОНИТОРИНГ РЕСУРСОВ И ДИАГНОСТИКА СЕРВИСОВ СЕРВЕРА CLI SYSTEM
# Модуль собирает и структурирует телеметрию операционной системы Linux.
# Выполняет сканирование памяти, дискового пространства, системных slices,
# проверяет доступность портов через сокеты и извлекает логи journalctl,
# изолируя конфликты ручных запусков от фоновых демонов systemd.

import asyncio
import subprocess
import socket
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
BACKEND_API_URL = "http://127.0.0.1:8000"

# Настройки контекста для жесткого переопределения кнопок хелпа Click на uadmin
CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

def check_port_status(port: int) -> bool:
    """Проверка доступности локального порта через сокеты"""
    if not port:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('127.0.0.1', port)) == 0


def find_manual_conflicting_processes(port: int = None, search_term: str = None):
    """Поиск ручных процессов, запущенных вне system.slice (логика из bash)"""
    conflicts = []
    pids = []
    try:
        if port:
            out_lsof = subprocess.check_output(f"sudo lsof -t -i:{port} 2>/dev/null", shell=True, text=True).strip()
            if out_lsof:
                pids.extend(out_lsof.split())
        if search_term:
            out_pgrep = subprocess.check_output(f"pgrep -f '{search_term}' 2>/dev/null", shell=True, text=True).strip()
            if out_pgrep:
                pids.extend(out_pgrep.split())

        pids = list(set(pids))
        for pid in pids:
            if not pid.isdigit() or pid == str(subprocess.os.getpid()):
                continue
            try:
                with open(f"/proc/{pid}/cgroup", "r") as f:
                    cgroup = f.read()
                if "system.slice" not in cgroup:
                    cmd_line = subprocess.check_output(f"ps -p {pid} -o command=", shell=True, text=True).strip()
                    conflicts.append({"pid": pid, "cmd": cmd_line[:70]})
            except FileNotFoundError:
                continue
    except Exception:
        pass
    return conflicts


def get_detailed_process_info(search_term: str):
    """Вспомогательная функция для сбора расширенных данных о процессах"""
    try:
        cmd = f"ps aux | grep '{search_term}' | grep -v grep | grep -v 'uadmin' | head -n 5"
        output = subprocess.check_output(cmd, shell=True, text=True).strip()
        if not output:
            return "[yellow]Процессы не найдены[/yellow]"

        table = Table(box=None, padding=(0, 2))
        table.add_column("USER", style="dim")
        table.add_column("PID", style="cyan")
        table.add_column("CPU%", style="magenta")
        table.add_column("MEM%", style="magenta")
        table.add_column("COMMAND", style="white")

        for line in output.split("\n"):
            parts = line.split(None, 10)
            if len(parts) >= 11:
                # Исправлено: корректная распаковка индексов массива вместо дублей
                table.add_row(parts[0], parts[1], f"{parts[2]}%", f"{parts[3]}%", parts[10][:70])
        return table
    except Exception as e:
        return f"[red]Ошибка сбора данных: {e}[/red]"


def get_service_logs(service_name: str, lines: int = 10):
    """Получение последних строк логов сервиса через journalctl"""
    try:
        cmd = f"sudo journalctl -u {service_name} -n {lines} --no-pager"
        output = subprocess.check_output(cmd, shell=True, text=True).strip()
        return output if output else "Логи пусты."
    except Exception:
        return "[dim]Не удалось получить логи через journalctl. Проверьте конфигурацию сервиса.[/dim]"


@click.command(context_settings=CONTEXT_SETTINGS)
@click.argument('component', type=click.Choice(['all', 'bot', 'back', 'web', 'db', 'ram']), default='all')
@click.option('--logs', '-l', is_flag=True, help="Показать последние логи выбранного компонента")
@click.option('--lines', '-n', default=10, help="Количество строк логов (по умолчанию 10)")
def system_info(component, logs, lines):
    """Выводит системные метрики сервера или подробный анализ конкретного компонента.

    Доступные компоненты: all, bot, back, web, db, ram\n
    Пример: uadmin system all --logs
    """
    async def _show():
        from app.system_info import collect_system_metrics
        metrics = await collect_system_metrics()

        has_manual_bot = len(find_manual_conflicting_processes(search_term="ulysses-bot/main.py")) > 0
        has_manual_back = len(find_manual_conflicting_processes(port=8000)) > 0

        # --- СЦЕНАРИЙ 1: ALL (Базовый дашборд) ---
        if component == 'all':
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
            if bot != "RUNNING" and has_manual_bot:
                bot_display, bot_status = "RUNNING (Manual)", "🟢"
            else:
                bot_display, bot_status = bot, ("🟢" if bot == "RUNNING" else "🔴")
            table.add_row("🤖 Telegram Bot", bot_display, bot_status)

            api = metrics.get("backend_status", "UNKNOWN")
            if api != "ONLINE" and has_manual_back:
                api_display, api_status = "ONLINE (Manual)", "🟢"
            else:
                api_display, api_status = api, ("🟢" if api == "ONLINE" else "🔴")
            table.add_row("⚙️ Backend API", api_display, api_status)

            is_bot_ok = (bot == "RUNNING" or has_manual_bot)
            is_back_ok = (api == "ONLINE" or has_manual_back)
            is_db_ok = (pg == "RUNNING")

            overall = "✅ Здорова" if (is_bot_ok and is_back_ok and is_db_ok) else "🚨 Проблемы"
            table.add_row("", "", "")
            table.add_row("🏥 Общий статус", overall, "")

            console.print(table)
            console.print("")

            proc_table = Table(title="🧠 ТОП-3 процесса по потреблению RAM")
            proc_table.add_column("PID", style="dim")
            proc_table.add_column("Процент RAM", style="magenta")
            proc_table.add_column("Команда", style="white")

            try:
                cmd = "ps aux --sort=-rss | head -n 4 | tail -n 3 | awk '{print $2 \"|\" $4 \"%|\" $11}'"
                output = subprocess.check_output(cmd, shell=True, text=True)
                for line in output.strip().split("\n"):
                    if line:
                        pid, mem, command = line.split("|")
                        short_cmd = command.split("/")[-1]
                        proc_table.add_row(pid, mem, short_cmd)
            except Exception:
                proc_table.add_row("-", "-", "Ошибка получения данных")

            console.print(proc_table)
            return

        # --- СЦЕНАРИЙ 2: ДЕТАЛЬНЫЙ АНАЛИЗ ОТДЕЛЬНЫХ КОМПОНЕНТОВ ---
        if component == 'bot':
            status = metrics.get("telegram_bot_status", "UNKNOWN")
            if status != "RUNNING" and has_manual_bot:
                status_text, color = "RUNNING (Вручную в консоли)", "green"
            else:
                status_text, color = status, ("green" if status == "RUNNING" else "red")

            console.print(Panel(f"Статус: [{color}]{status_text}[/{color}]", title="🤖 Подробный анализ Telegram Bot", expand=False))

            conflicts = find_manual_conflicting_processes(search_term="ulysses-bot/main.py")
            if conflicts and status == "RUNNING":
                console.print("[bold red]🚨 Конфликт: Бот запущен и в systemd, и вручную в консоли![/bold red]")
                for c in conflicts:
                    console.print(f"  ➜ PID: [cyan]{c['pid']}[/cyan] | Команда: {c['cmd']}")

            console.print("\n[bold cyan]🔍 Связанные процессы в системе:[/bold cyan]")
            console.print(get_detailed_process_info("ulysses-bot/main.py"))

            if logs:
                console.print(f"\n[bold yellow]📋 Последние {lines} строк логов (ulysses-bot.service):[/bold yellow]")
                console.print(get_service_logs("ulysses-bot", lines))

        elif component == 'back':
            status = metrics.get("backend_status", "UNKNOWN")
            if status != "ONLINE" and has_manual_back:
                status_text, color = "ONLINE (Вручную в консоли)", "green"
            else:
                status_text, color = status, ("green" if status == "ONLINE" else "red")

            console.print(Panel(f"Статус API: [{color}]{status_text}[/{color}]", title="⚙️ Подробный анализ Backend API", expand=False))

            is_open = check_port_status(8000)
            port_text = "[bold green]✅ ОТКРЫТ[/bold green]" if is_open else "[bold red]❌ ЗАКРЫТ[/bold red]"
            console.print(f"Сетевой порт 8000: {port_text}")

            conflicts = find_manual_conflicting_processes(port=8000)
            if conflicts and status == "ONLINE":
                console.print("[bold red]🚨 Конфликт: Порт 8000 занят и службой, и ручным процессом:[/bold red]")
                for c in conflicts:
                    console.print(f"  ➜ PID: [cyan]{c['pid']}[/cyan] | Команда: {c['cmd']}")

            console.print("\n[bold cyan]🔍 Связанные процессы (FastAPI / Gunicorn / Uvicorn):[/bold cyan]")
            console.print(get_detailed_process_info("uvicorn"))

            if logs:
                console.print(f"\n[bold yellow]📋 Последние {lines} строк логов (ulysses-backend.service):[/bold yellow]")
                console.print(get_service_logs("ulysses-backend", lines))

        elif component == 'web':
            is_open = check_port_status(5173)
            port_text = "[bold green]✅ ОТКРЫТ[/bold green]" if is_open else "[bold red]❌ ЗАКРЫТ[/bold red]"
            console.print(Panel(f"Интерфейс доступен: {port_text}", title="🌐 Подробный анализ Web Admin Frontend", expand=False))

            console.print("\n[bold cyan]🔍 Связанные процессы (pnpm / node / vite):[/bold cyan]")
            console.print(get_detailed_process_info("node"))

            if logs:
                console.print(f"\n[bold yellow]📋 Последние {lines} строк логов (ulysses-web.service):[/bold yellow]")
                console.print(get_service_logs("ulysses-web", lines))

        elif component == 'db':
            status = metrics.get("postgres_status", "UNKNOWN")
            color = "green" if status == "RUNNING" else "red"
            console.print(Panel(f"Статус БД: [{color}]{status}[/{color}]", title="🐘 Подробный анализ PostgreSQL", expand=False))

            is_open = check_port_status(5432)
            port_text = "[bold green]✅ ОТКРЫТ[/bold green]" if is_open else "[bold red]❌ ЗАКРЫТ[/bold red]"
            console.print(f"Сетевой порт 5432: {port_text}")

            console.print("\n[bold cyan]🔍 Активные процессы PostgreSQL:[/bold cyan]")
            console.print(get_detailed_process_info("postgres"))

            if logs:
                console.print(f"\n[bold yellow]📋 Последние {lines} строк логов (postgresql.service):[/bold yellow]")
                console.print(get_service_logs("postgresql", lines))

        elif component == 'ram':
            ram_pct = metrics.get("ram_available_percent", 0)
            console.print(Panel(f"Доступно памяти: [bold green]{ram_pct}%[/bold green]", title="🧠 Расширенный анализ RAM", expand=False))

            console.print("\n[bold cyan]📊 ТОП-10 процессов по потреблению оперативной памяти:[/bold cyan]")
            ram_table = Table()
            ram_table.add_column("PID", style="cyan")
            ram_table.add_column("USER", style="dim")
            ram_table.add_column("RAM %", style="magenta")
            ram_table.add_column("COMMAND", style="white")

            try:
                cmd = "ps aux --sort=-rss | head -n 11 | tail -n 10 | awk '{print $2 \"|\" $1 \"|\" $4 \"%|\" $11}'"
                output = subprocess.check_output(cmd, shell=True, text=True)
                for line in output.strip().split("\n"):
                    if line:
                        pid, user, mem, command = line.split("|")
                        ram_table.add_row(pid, user, mem, command[:80])
                console.print(ram_table)
            except Exception as e:
                console.print(f"[red]Ошибка при получении топа RAM: {e}[/red]")

    asyncio.run(_show())


if __name__ == "__main__":
    system_info(prog_name="uadmin system")
