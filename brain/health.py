import click
import socket
import os
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from cli.brain.db import query, execute, close

console = Console()

TIMEOUT = 5          # секунд на соединение
CHECK_PORT = 443     # порт прокси на щите
FAIL_THRESHOLD = 3   # последовательных провалов для статуса offline


def check_tcp(ip, port, timeout=TIMEOUT):
    """TCP-проверка: возвращает True если порт открыт"""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except (socket.timeout, socket.error, OSError):
        return False


@click.command()
@click.option('--shield-id', type=int, default=None, help='Проверить только один щит')
@click.option('--port', default=CHECK_PORT, help=f'Порт для проверки (по умолчанию: {CHECK_PORT})')
@click.option('--verbose', '-v', is_flag=True, help='Подробный вывод')
def health(shield_id, port, verbose):
    """Health Checker: проверка доступности щитов по TCP"""

    sql = "SELECT id, ip, country, status, datacenter FROM brain.shields"
    params = {}
    if shield_id:
        sql += " WHERE id = %(sid)s"
        params["sid"] = shield_id

    shields = query(sql, params)

    if not shields:
        console.print("[yellow]⚠[/] Нет щитов для проверки.")
        close()
        return

    now = datetime.now(timezone.utc)
    alerts = []

    table = Table(title="🏥 Health Checker")
    table.add_column("ID", style="cyan", width=4)
    table.add_column("IP", style="white")
    table.add_column("Страна", style="green")
    table.add_column("Порт", style="yellow")
    table.add_column("TCP", style="bold")
    table.add_column("Статус", style="yellow")

    for s in shields:
        sid = s["id"]
        ip = s["ip"]
        country = s["country"]
        current_status = s["status"]

        tcp_ok = check_tcp(ip, port)
        tcp_display = "[green]OPEN[/green]" if tcp_ok else "[red]CLOSED[/red]"

        # Обновляем last_health_check
        execute(
            "UPDATE brain.shields SET last_health_check = %(now)s WHERE id = %(sid)s",
            {"now": now, "sid": sid}
        )

        new_status = current_status

        if not tcp_ok:
            # Получаем статус последних 3-х записей телеметрии по времени
            last_telemetry = query(
                "SELECT error_count FROM brain.telemetry "
                "WHERE shield_id = %(sid)s "
                "ORDER BY recorded_at DESC LIMIT %(limit)s",
                {"sid": sid, "limit": FAIL_THRESHOLD}
            )

            # Проверяем, что все последние записи содержат ошибки
            all_failed = len(last_telemetry) >= FAIL_THRESHOLD and all(t["error_count"] > 0 for t in last_telemetry)

            # Если щит активен, порт закрыт и телеметрия подтверждает падение — уводим в offline
            if current_status == "active":
                alerts.append(s)
                new_status = "offline"
        else:
            # Если был offline, а порт открылся — возвращаем в reserve
            if current_status == "offline":
                new_status = "reserve"

        if new_status != current_status:
            execute(
                "UPDATE brain.shields SET status = %(status)s WHERE id = %(sid)s",
                {"status": new_status, "sid": sid}
            )

        status_display = {
            "active": "[green]active[/green]",
            "blocked": "[red]blocked[/red]",
            "reserve": "[blue]reserve[/blue]",
            "offline": "[dim]offline[/dim]",
        }.get(new_status, new_status)

        if verbose or not tcp_ok:
            table.add_row(str(sid), ip, country, str(port), tcp_display, status_display)

    if not verbose and not alerts:
        console.print(f"[green]✓[/] Все щиты живы (проверено: {len(shields)})")
        close()
        return

    console.print(table)

    if alerts:
        console.print(f"\n[red]⚠[/] Обнаружены проблемы на щитах: {', '.join(str(s['id']) for s in alerts)}")
        console.print("[dim]Статус изменён на 'offline'. Проверьте серверы.[/dim]")
        # TODO: отправить уведомление в Telegram/email
    else:
        console.print(f"\n[green]✓[/] Все {len(shields)} щитов отвечают.")

    close()
