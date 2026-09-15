# cli/help.py

"""
Сводная справка по всем командам Ulysses CLI.

Собирается автоматически из дерева click-команд — не надо вручную
поддерживать список в актуальном состоянии. Достаточно объявить
команду через @cli.command / @group.command, и она появится здесь.
"""

import click
from rich.console import Console
from rich.table import Table

console = Console()


def _short_description(cmd: click.Command) -> str:
    """Краткое описание команды: первая строка short_help/help/docstring."""
    text = (
        cmd.short_help
        or cmd.help
        or (cmd.callback.__doc__ if cmd.callback else "")
        or ""
    ).strip()

    if not text:
        return "—"

    first_line = text.split("\n", 1)[0].strip()
    if first_line.endswith("."):
        first_line = first_line[:-1]
    return first_line


def _iter_commands(group: click.Group, prefix: str = ""):
    """Генератор (full_name, description, depth) для группы и всех подкоманд."""
    for name, cmd in group.commands.items():
        if getattr(cmd, "hidden", False):
            continue
        full = f"{prefix} {name}".strip()
        depth = full.count(" ")
        yield full, _short_description(cmd), depth
        if isinstance(cmd, click.Group):
            yield from _iter_commands(cmd, full)


def _resolve_command(root: click.Group, path: str) -> click.Command | None:
    """По строке 'user sub' находит соответствующий Command в дереве."""
    parts = path.strip().split()
    cmd: click.Command = root
    for part in parts:
        if not isinstance(cmd, click.Group):
            return None
        nxt = cmd.commands.get(part)
        if nxt is None:
            return None
        cmd = nxt
    return cmd


@click.command(name="help")
@click.argument("command_path", required=False)
@click.pass_context
def help_cmd(ctx: click.Context, command_path: str | None):
    """Сводка всех команд CLI либо детальная справка по конкретной команде.

    Примеры:

        uadmin help                — таблица всех команд

        uadmin help user           — справка по группе 'user'

        uadmin help user sub       — справка по 'user sub' с ключами
    """
    root: click.Group = ctx.find_root().command

    # --- Детальная справка по конкретной команде ---
    if command_path:
        target = _resolve_command(root, command_path)
        if target is None:
            console.print(f"[red]❌ Команда '{command_path}' не найдена[/red]")
            console.print("[dim]Подсказка: uadmin help[/dim]")
            return

        with click.Context(target, info_name=command_path) as sub_ctx:
            click.echo(target.get_help(sub_ctx))
        return

    # --- Сводная таблица всех команд ---
    table = Table(
        title="🛠  Ulysses CLI — команды",
        show_header=True,
        header_style="bold magenta",
        padding=(0, 1),
    )
    table.add_column("Команда", style="cyan", no_wrap=True)
    table.add_column("Описание")

    for full_name, description, depth in _iter_commands(root):
        # отступ для вложенных подкоманд
        indent = "  " * depth
        table.add_row(f"uadmin {full_name}" if depth == 0 else f"{indent}└─ {full_name}",
                      description)

    console.print(table)
    console.print(
        "[dim]ℹ️ Детали:  [cyan]uadmin help <команда>[/cyan]  "
        "(например, [cyan]uadmin help user sub[/cyan])[/dim]"
    )
