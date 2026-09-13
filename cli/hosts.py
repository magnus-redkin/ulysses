# cli/hosts.py

"""
Управление HFM-нодами.

Использование:
    uadmin hosts             — список нод (brain + HFM)
    uadmin hosts <name>      — запустить check_hiddify.sh на ноде по SSH
"""

import subprocess
import click
from rich.console import Console
from rich.table import Table

from app.services.node_manager import node_manager

console = Console()


@click.command(name="hosts")
@click.argument("name", required=False)
def hosts(name):
    """HFM-ноды: без аргумента — список, с именем — check_hiddify.sh."""
    if name:
        _check_node(name)
    else:
        _list_nodes()


def _list_nodes():
    table = Table(title="🌐 Узлы Ulysses")
    table.add_column("ID", style="cyan")
    table.add_column("Код", style="green")
    table.add_column("Домен", style="blue")
    table.add_column("IP", style="yellow")
    table.add_column("Версия", style="magenta")

    # Первой строкой — brain (сам Ulysses)
    table.add_row("brain", "—", "ulysses.best", "2.59.219.100", "—")

    # Далее — HFM-ноды из кэша
    nodes = node_manager.get_active_hfm_nodes()
    if not nodes:
        console.print("[red]❌ HFM-нод нет в кэше. Запустите backend для обновления.[/red]")
    for n in nodes:
        table.add_row(
            n.get("id", "—"),
            n.get("code", "—"),
            n.get("domain", "—"),
            n.get("ip", "—"),
            n.get("version", "—"),
        )

    console.print(table)


def _check_node(name: str):
    console.print(f"[yellow]🔍 Проверка ноды '{name}' через SSH...[/yellow]\n")
    try:
        # Стримим stdout/stderr напрямую в терминал пользователя
        result = subprocess.run(["ssh", name, "bash ~/check_hiddify.sh"])
        if result.returncode != 0:
            console.print(f"\n[yellow]⚠️ check_hiddify.sh вернул код {result.returncode}[/yellow]")
    except FileNotFoundError:
        console.print("[red]❌ ssh не найден в PATH[/red]")
    except Exception as e:
        console.print(f"[red]❌ Ошибка: {e}[/red]")


if __name__ == "__main__":
    hosts(prog_name="uadmin hosts")
