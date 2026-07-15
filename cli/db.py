import os
import subprocess
import click
from rich.console import Console

console = Console()

@click.group()
def db():
    """Управление базой данных Ulysses VPN Core"""
    pass

@db.command(name="reset")
@click.confirmation_option(prompt="🚨 Вы уверены, что хотите ПОЛНОСТЬЮ СБРОСИТЬ БАЗУ ДАННЫХ? Все данные пользователей будут удалены!")
def db_reset():
    """Полная очистка и переинициализация структуры БД"""
    console.print("[yellow]⏳ Начинается сброс базы данных...[/yellow]")

    # Ищем ваш bash-скрипт инициализации в корне проекта
    script_name = "init_db.sh"  # Переименуйте, если ваш файл называется иначе (например, setup_db.sh)
    script_path = os.path.expanduser(f"~/Ulysses/{script_name}")

    if not os.path.exists(script_path):
        console.print(f"[red]❌ Скрипт инициализации не найден по пути: {script_path}[/red]")
        return

    try:
        # Выполняем ваш bash-скрипт
        console.print(f"📦 Запуск {script_name}...")
        result = subprocess.run(["bash", script_path], check=True, text=True, capture_output=True)
        console.print(result.stdout)

        # Перезапускаем бэкенд, чтобы сбросить пул соединений SQLAlchemy
        console.print("⚙️ Перезапуск systemd-сервиса бэкенда...")
        subprocess.run(["sudo", "systemctl", "restart", "ulysses-backend.service"], check=True)

        console.print("[green]✅ База данных успешно сброшена и инициализирована заново![/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Ошибка при выполнении сброса БД:[/red]")
        console.print(e.stderr or str(e))


@db.command(name="restore")
@click.argument('file', type=click.Path(exists=True))
@click.confirmation_option(prompt="🚨 Вы уверены, что хотите ВОССТАНОВИТЬ БД из дампа? Текущие данные будут потеряны!")
def db_restore(file):
    """Восстановить базу данных из дампа (pg_restore или psql)"""
    import os

    from dotenv import load_dotenv
    from pathlib import Path

    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)

    db_name = os.getenv("DB_NAME", "ulysses_db")
    db_user = os.getenv("DB_USER", "ulysses_admin")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_pass = os.getenv("DB_PASS", "")

    os.environ["PGPASSWORD"] = db_pass

    console.print(f"[yellow]⏳ Восстановление БД из '{file}'...[/yellow]")

    try:
        # Сначала удаляем существующую БД и создаём чистую
        subprocess.run(
            ["dropdb", "-h", db_host, "-p", db_port, "-U", db_user, db_name],
            check=False,  # БД может не существовать
            capture_output=True
        )
        subprocess.run(
            ["createdb", "-h", db_host, "-p", db_port, "-U", db_user, db_name],
            check=True,
            capture_output=True
        )

        # Восстанавливаем из дампа
        with open(file, 'r') as f:
            result = subprocess.run(
                [
                    "psql",
                    "-h", db_host,
                    "-p", db_port,
                    "-U", db_user,
                    "-d", db_name
                ],
                stdin=f,
                check=True,
                capture_output=True,
                text=True
            )

        console.print(f"[green]✓[/] База данных восстановлена из '{file}'")
        console.print("⚙️ Не забудьте перезапустить бэкенд: sudo systemctl restart ulysses-backend.service")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Ошибка восстановления:[/red]")
        console.print(e.stderr)
    finally:
        del os.environ["PGPASSWORD"]

@db.command(name="dump")
@click.option('--file', default=None, help='Путь к файлу дампа (по умолчанию: ~/Ulysses/dump/backup_latest.sql)')
def db_dump(file):
    """Создать дамп базы данных с ротацией (текущий + предыдущий) и проверкой целостности"""
    from datetime import datetime
    import os
    import shutil

    from dotenv import load_dotenv
    from pathlib import Path

    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)

    db_name = os.getenv("DB_NAME", "ulysses_db")
    db_user = os.getenv("DB_USER", "ulysses_admin")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_pass = os.getenv("DB_PASS", "")

    dump_dir = os.path.expanduser("~/Ulysses/dump")
    os.makedirs(dump_dir, exist_ok=True)

    latest = os.path.join(dump_dir, "backup_latest.sql")
    previous = os.path.join(dump_dir, "backup_previous.sql")
    temp = os.path.join(dump_dir, "backup_temp.sql")

    if file:
        target = file
    else:
        target = temp

    os.environ["PGPASSWORD"] = db_pass

    console.print(f"[yellow]⏳ Создание дампа БД '{db_name}'...[/yellow]")

    try:
        # Создаём дамп
        subprocess.run(
            [
                "pg_dump",
                "-h", db_host,
                "-p", db_port,
                "-U", db_user,
                "-d", db_name,
                "--no-owner",
                "--no-acl",
                "-f", target
            ],
            check=True,
            capture_output=True,
            text=True
        )
        size = os.path.getsize(target)
        console.print(f"  Дамп записан: {size / 1024:.1f} KB")

        # Проверка целостности: последняя строка должна содержать завершающий комментарий pg_dump
        with open(target, 'r') as f:
            # Читаем последние 4 КБ файла (хвост)
            f.seek(0, 2)  # в конец
            fsize = f.tell()
            tail_size = min(4096, fsize)
            f.seek(fsize - tail_size)
            tail = f.read()

            if '-- PostgreSQL database dump complete' not in tail:
                raise ValueError("Дамп не завершён: отсутствует финальный комментарий pg_dump")

        console.print(f"[green]✓[/] Целостность дампа подтверждена")

        # Ротация: только если дамп корректен
        if not file:
            if os.path.exists(latest):
                shutil.move(latest, previous)
                console.print("[dim]  Предыдущий дамп → backup_previous.sql[/dim]")
            shutil.move(temp, latest)
            console.print(f"[green]✓[/] Дамп сохранён: {latest}")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Ошибка pg_dump:[/red]")
        console.print(e.stderr)
        # Удаляем недоделанный файл
        if os.path.exists(target):
            os.remove(target)
    except ValueError as e:
        console.print(f"[red]❌ Дамп повреждён: {e}[/red]")
        if os.path.exists(target):
            os.remove(target)
        console.print("[yellow]⚠[/] Предыдущий дамп НЕ заменён.")
    finally:
        del os.environ["PGPASSWORD"]
        # Подчищаем temp, если что-то пошло не так и он остался
        if os.path.exists(temp):
            os.remove(temp)


@db.command(name="query")
@click.argument('sql', required=True)
def db_query(sql):
    """Выполнить произвольный SQL-запрос и вывести результат"""
    from cli.brain.db import query, close
    rows = query(sql)
    if not rows:
        console.print("[dim](пусто)[/dim]")
        close()
        return
    # Вывод в таблице
    from rich.table import Table
    table = Table()
    for key in rows[0].keys():
        table.add_column(key, style="cyan")
    for row in rows:
        table.add_row(*[str(v) for v in row.values()])
    console.print(table)
    close()

# uadmin db query "SELECT id, email, amount, status, created_at FROM payment_attempts ORDER BY created_at DESC LIMIT 5"
