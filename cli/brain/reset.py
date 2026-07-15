import click
import os
import subprocess
from rich.console import Console
from cli.brain.db import execute, close

console = Console()


@click.command()
@click.confirmation_option(prompt="🚨 Вы уверены, что хотите очистить ВСЕ brain-таблицы?")
def reset():
    """Полная очистка brain-таблиц (с автоматическим дампом перед сбросом)"""

    # Аварийный дамп перед сбросом
    dump_path = os.path.expanduser("~/Ulysses/dump/pre_reset_backup.sql")
    os.makedirs(os.path.dirname(dump_path), exist_ok=True)

    console.print(f"[yellow]⚠[/] Создаю аварийный дамп перед сбросом: {dump_path}")

    try:
        from cli.db import db_dump
        # Вызываем db_dump вручную, передав путь
        ctx = click.Context(db_dump)
        ctx.invoke(db_dump, file=dump_path)
    except Exception as e:
        console.print(f"[red]❌ Не удалось создать дамп: {e}[/red]")
        console.print("[yellow]Продолжаю без дампа...[/yellow]")

    execute("TRUNCATE brain.shields, brain.telemetry, brain.incidents, brain.dns_state CASCADE")
    console.print("[green]✓[/] Все brain-таблицы очищены.")
    close()
