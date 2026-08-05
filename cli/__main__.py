# cli/__main__.py

# ЦЕНТРАЛЬНЫЙ ДИСПЕТЧЕР И ТОЧКА ВХОДА CLI ИНСТРУМЕНТАРИЯ UADMIN
# Модуль собирает и регистрирует все изолированные пакеты команд (user, db, fix, check).
# Жестко фиксирует глобальный контекст утилиты под нативное системное имя "uadmin",
# автоматически каскадируя правильные строки "Usage:" вниз по всему дереву подкоманд.

import click
import logging
from . import stats, notify, check, system_info, db, user
# from .brain import brain
from .pay import pay as pay_group
from .monitor import monitor as monitor_group
from .fix import fix as fix_group

from cli.notify import notify as notify_cmd

# Подавляем избыточные логи SQLAlchemy, сохраняя чистоту терминала
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.orm').setLevel(logging.WARNING)

# Безопасные настройки контекста (БЕЗ info_name для предотвращения TypeError)
CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """Ulysses VPN Core — Главная утилита управления и обслуживания инфраструктуры.

    Использование: uadmin КОМАНДА [ОПЦИИ]...
    """
    pass


# Регистрируем изолированные модули подкоманд в единое дерево
cli.add_command(stats.stats)
cli.add_command(check.check)

cli.add_command(system_info.system_info, name="system")
cli.add_command(db.db)
cli.add_command(user.user)
# cli.add_command(sub.sub)
# cli.add_command(vpn.vpn)
cli.add_command(monitor_group)
cli.add_command(notify_cmd)
cli.add_command(fix_group)

cli.add_command(pay_group)
# cli.add_command(brain)


@cli.command(name="help")
def help_all():
    """Показать подробную справку по всем командам uadmin."""
    ctx = click.get_current_context()
    root_cmd = ctx.find_root().command

    def _print_help(cmd, prefix=""):
        """Рекурсивно печатает help для команды/группы."""
        full_name = f"{prefix} {cmd.name}".strip()
        if isinstance(cmd, click.Group):
            # Справка самой группы
            click.echo(f"\n{'='*60}")
            click.echo(f"COMMAND: {full_name}")
            click.echo(cmd.get_help(click.Context(cmd, info_name=full_name)))
            # Рекурсивно для всех подкоманд
            for sub_cmd in cmd.commands.values():
                _print_help(sub_cmd, full_name)
        else:
            click.echo(f"\n{'='*60}")
            click.echo(f"COMMAND: {full_name}")
            click.echo(cmd.get_help(click.Context(cmd, info_name=full_name)))

    _print_help(root_cmd)



if __name__ == "__main__":
    # 🌟 ЕДИНСТВЕННОЕ ПРАВИЛЬНОЕ МЕСТО: передаем имя исполняемой программы в точку запуска.
    # Это намертво перестроит все подсказки "Usage: uadmin fix..." без конфликтов в контексте.
    cli(prog_name="uadmin")
