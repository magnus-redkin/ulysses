import click
import logging
from . import stats, notify, check, fix, system_info, db, user, sub, vpn, info
from .brain import brain
from .pay import pay as pay_group

# Подавляем логи
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logging.getLogger('sqlalchemy.orm').setLevel(logging.WARNING)

@click.group(context_settings=dict(help_option_names=['-h', '--help']))
def cli():
    """Ulysses VPN — Инструментарий администратора и оператора системы"""
    pass

# Регистрируем команды
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
    cli()
