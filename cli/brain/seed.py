# cli/brain/seed.py
import random
from datetime import datetime, timedelta, timezone
import click
from rich.console import Console
from cli.brain.db import query, execute, close

console = Console()


@click.command()
@click.option('--clear', is_flag=True, help='Очистить brain-таблицы перед сидированием')
def seed(clear):
    """Заполнить brain-таблицы тестовыми данными (щиты + телеметрия)"""

    if clear:
        execute("TRUNCATE brain.shields, brain.telemetry, brain.incidents, brain.dns_state CASCADE")
        console.print("[green]✓[/] Таблицы brain очищены.")

    # --- Щиты ---
    existing = query("SELECT COUNT(*) as cnt FROM brain.shields")
    if existing[0]["cnt"] > 0:
        console.print(f"[yellow]⚠[/] В brain.shields уже {existing[0]['cnt']} записей. Пропускаем создание щитов.")
    else:
        shields_data = [
            {
                "ip": "83.147.216.201",
                "country": "DE",
                "datacenter": "aeza",
                "status": "active"       # Основной щит, который сейчас в DNS
            },
            {
                "ip": "62.60.249.53",
                "country": "FI",
                "datacenter": "aeza",
                "status": "reserve"      # Резервный щит, спит и ждет атаки
            },
            {
                "ip": "192.0.2.30",
                "country": "NL",
                "datacenter": "test",
                "status": "reserve"      # Второй резерв
            }
        ]
        for s in shields_data:
            execute(
                "INSERT INTO brain.shields (ip, country, datacenter, status) "
                "VALUES (%(ip)s, %(country)s, %(country)s, %(status)s)",
                s
            )
        console.print(f"[green]✓[/] Создано {len(shields_data)} щитов.")

    # --- Телеметрия ---
    shields = query("SELECT id FROM brain.shields")
    now = datetime.now(timezone.utc)

    total = 0
    for shield_row in shields:
        shield_id = shield_row["id"]
        for minutes_ago in range(0, 60, 2):
            t = now - timedelta(minutes=minutes_ago)
            active_clients = random.randint(80, 200)
            error_count = random.randint(0, 5)
            avg_latency = round(random.uniform(20.0, 60.0), 2)

            execute(
                "INSERT INTO brain.telemetry (shield_id, active_clients, error_count, avg_latency_ms, recorded_at) "
                "VALUES (%(sid)s, %(ac)s, %(ec)s, %(al)s, %(t)s)",
                {"sid": shield_id, "ac": active_clients, "ec": error_count, "al": avg_latency, "t": t}
            )
            total += 1

    console.print(f"[green]✓[/] Сгенерировано {total} записей телеметрии (по 30 на каждый из {len(shields)} щитов).")
    close()
