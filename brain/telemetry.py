# cli/brain/telemetry.py
import random
from datetime import datetime, timezone
import click
from rich.console import Console
from cli.brain.db import query, execute, close

console = Console()


@click.command()
@click.option('--shield-id', type=int, default=None, help='ID конкретного щита (если не указан — все активные)')
@click.option('--anomaly', is_flag=True, help='Сгенерировать аномалию (0 клиентов, много ошибок)')
def telemetry(shield_id, anomaly):
    """Сгенерировать один цикл телеметрии (имитация Telemetry Collector)"""

    sql = "SELECT id, country FROM brain.shields WHERE status = 'active'"
    params = {}
    if shield_id:
        sql += " AND id = %(sid)s"
        params["sid"] = shield_id

    shields = query(sql, params)

    if not shields:
        console.print("[yellow]⚠[/] Нет активных щитов.")
        close()
        return

    now = datetime.now(timezone.utc)

    for s in shields:
        sid = s["id"]
        country = s["country"]

        if anomaly:
            active_clients = 0
            error_count = random.randint(50, 100)
            avg_latency = 999.99
        else:
            active_clients = random.randint(80, 200)
            error_count = random.randint(0, 5)
            avg_latency = round(random.uniform(20.0, 60.0), 2)

        execute(
            "INSERT INTO brain.telemetry (shield_id, active_clients, error_count, avg_latency_ms, recorded_at) "
            "VALUES (%(sid)s, %(ac)s, %(ec)s, %(al)s, %(t)s)",
            {"sid": sid, "ac": active_clients, "ec": error_count, "al": avg_latency, "t": now}
        )

        status = "[red]АНОМАЛИЯ![/red]" if anomaly else "OK"
        console.print(f"  Щит {sid} ({country}): {active_clients} клиентов, {error_count} ошибок, {avg_latency} мс  {status}")

    close()
    console.print(f"\n[green]✓[/] Цикл телеметрии сгенерирован для {len(shields)} щитов.")
