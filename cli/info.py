import os
import subprocess
import click

@click.command(name="help")
def show_help():
    """Показать сводную интерактивную таблицу всех команд системы"""
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
