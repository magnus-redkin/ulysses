# cli/info.py

# ИНТЕРАКТИВНАЯ СПРАВОЧНАЯ СИСТЕМА И ИНСТРУКЦИИ ОПЕРАТОРА CLI INFO
# Модуль отвечает за вывод расширенной документации по командам Ulysses VPN.
# Считывает файл help.md и рендерит его через системный пейджер less для удобного
# постраничного скроллинга, предоставляя оператору детальные примеры использования утилиты.

import os
import subprocess
import click

# Настройки контекста для жесткого переопределения ключей хелпа Click на uadmin
CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help']
)

@click.command(name="help", context_settings=CONTEXT_SETTINGS)
def show_help():
    """Показать сводную интерактивную таблицу всех команд системы.

    Пример: uadmin help
    """
    # Вычисляем абсолютный путь к help.md относительно корня проекта
    help_path = os.path.expanduser("~/Ulysses/cli/help.md")

    if not os.path.exists(help_path):
        click.secho(f"❌ Файл справки не найден по пути: {help_path}", fg="red")
        return

    try:
        # Запускаем через less, чтобы оператор мог удобно скроллить и выйти на 'q'
        # Флаг -R позволяет корректно отображать цвета/форматирование, -S отключает автоперенос строк
        subprocess.run(["less", "-RS", help_path])
    except Exception:
        # Если less недоступен (например, в урезанном контейнере), просто выводим через cat
        subprocess.run(["cat", help_path])


if __name__ == "__main__":
    # Обеспечиваем нативное отображение синтаксиса uadmin при автономном запуске
    show_help(prog_name="uadmin help")
