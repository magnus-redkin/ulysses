# cli/__main__.py

# ЦЕНТРАЛЬНЫЙ ДИСПЕТЧЕР И ТОЧКА ВХОДА CLI ИНСТРУМЕНТАРИЯ UADMIN
# Модуль собирает и регистрирует все изолированные пакеты команд (user, db, fix, check, brain).
# Жестко фиксирует глобальный контекст утилиты под нативное системное имя "uadmin",
# автоматически каскадируя правильные строки "Usage:" вниз по всему дереву подкоманд.

import click
import logging
from . import stats, notify, check, fix, system_info, db, user, sub, vpn, info
from .brain import brain
from .pay import pay as pay_group

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
cli.add_command(notify.notify)
cli.add_command(check.check)
cli.add_command(fix.fix)
cli.add_command(system_info.system_info, name="system")
cli.add_command(db.db)
cli.add_command(user.user)
cli.add_command(sub.sub)
cli.add_command(vpn.vpn)
cli.add_command(info.show_help)

cli.add_command(pay_group)
cli.add_command(brain)

if __name__ == "__main__":
    # 🌟 ЕДИНСТВЕННОЕ ПРАВИЛЬНОЕ МЕСТО: передаем имя исполняемой программы в точку запуска.
    # Это намертво перестроит все подсказки "Usage: uadmin fix..." без конфликтов в контексте.
    cli(prog_name="uadmin")
