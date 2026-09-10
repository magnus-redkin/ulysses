import asyncio
import json
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table

console = Console()

def async_cmd(f):
    import functools
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

def load_nodes():
    path = Path(__file__).parent.parent / "backend/app/private/nodes.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@click.group(name="host", invoke_without_command=True)
@click.argument("name", required=False, default="localhost")
@click.pass_context
def host(ctx, name):
    """Информация о хостах из nodes.json."""
    if ctx.invoked_subcommand is None:
        # Вызываем показ напрямую
        ctx.invoke(show_host, name=name)

@host.command(name="show")
@click.argument("name", default="localhost")
@async_cmd
async def show_host(name):
    """Показать информацию о хосте. По умолчанию localhost."""
    nodes = load_nodes()
    if name == "localhost":
        node = nodes.get("ulysses", {})
        title = "Ulysses Host (localhost)"
        if not node:
            console.print("[red]В nodes.json нет записи 'ulysses'[/red]")
            return
    else:
        if name not in nodes:
            console.print(f"[red]Хост '{name}' не найден в nodes.json[/red]")
            return
        node = nodes[name]
        title = f"Хост {name}"

    table = Table(title=title)
    table.add_column("Параметр", style="cyan")
    table.add_column("Значение", style="green")
    for key, value in node.items():
        table.add_row(key, str(value))
    console.print(table)

if __name__ == "__main__":
    host()
