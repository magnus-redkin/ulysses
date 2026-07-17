# cli/db.py

# УПРАВЛЕНИЕ СТРУКТУРОЙ И РЕЗЕРВНЫМ КОПИРОВАНИЕМ СУБД CLI DB
# Модуль предоставляет инструменты обслуживания СУБД PostgreSQL.
# Обеспечивает аварийный сброс таблиц, создание дампов с ротацией и валидацией,
# а также безопасное восстановление контура без необходимости обладать правами суперпользователя.

import os
import shutil
import subprocess
import click
from rich.console import Console
from rich.table import Table

console = Console()

# Переопределяем имя исполняемого файла и ключи вызова в хелпе Click на uadmin
CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help'],
    max_content_width=120
)

@click.group(context_settings=CONTEXT_SETTINGS)
def db():
    """Управление базой данных Ulysses VPN Core.

    Использование: uadmin db КОМАНДА [АРГУМЕНТЫ]...
    """
    pass

# Переопределяем отображение имени группы в подсказках хелпа нижнего уровня
db.get_usage = lambda ctx: "uadmin db [ОПЦИИ] КОМАНДА [ARGS]..."


@db.command(name="reset")
@click.confirmation_option(prompt="🚨 Вы уверены, что хотите ПОЛНОСТЬЮ СБРОСИТЬ БАЗУ ДАННЫХ? Все данные пользователей будут удалены!")
def db_reset():
    """Полная очистка и переинициализация структуры БД.

    Пример: uadmin db reset
    """
    console.print("[yellow]⏳ Начинается сброс базы данных...[/yellow]")

    script_name = "init_db.sh"
    script_path = os.path.expanduser(f"~/Ulysses/{script_name}")

    if not os.path.exists(script_path):
        console.print(f"[red]❌ Скрипт инициализации не найден по пути: {script_path}[/red]")
        return

    try:
        console.print(f"📦 Запуск {script_name}...")
        result = subprocess.run(["bash", script_path], check=True, text=True, capture_output=True)
        console.print(result.stdout)

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
    """Восстановить базу данных из файла дампа (psql) без прав суперпользователя.

    Пример: uadmin db restore backup.sql
    """
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

    console.print(f"[yellow]⏳ Очистка текущих таблиц и схем в базе '{db_name}'...[/yellow]")

    try:
        # Решение проблемы прав: Вместо dropdb/createdb мы принудительно очищаем таблицы внутри текущей сессии
        cleanup_sql = """
        DROP SCHEMA IF EXISTS brain CASCADE;
        DROP TABLE IF EXISTS payment_attempts CASCADE;
        DROP TABLE IF EXISTS subscriptions CASCADE;
        DROP TABLE IF EXISTS users CASCADE;
        DROP EXTENSION IF EXISTS "uuid-ossp" CASCADE;
        """
        subprocess.run(
            ["psql", "-h", db_host, "-p", db_port, "-U", db_user, "-d", db_name, "-c", cleanup_sql],
            check=True,
            capture_output=True
        )

        console.print(f"[yellow]⏳ Накатывание дампа из '{file}'...[/yellow]")
        with open(file, 'r', encoding='utf-8', errors='ignore') as f:
            subprocess.run(
                ["psql", "-h", db_host, "-p", db_port, "-U", db_user, "-d", db_name],
                stdin=f,
                check=True,
                capture_output=True,
                text=True
            )

        console.print(f"[green]✓[/] База данных успешно восстановлена из '{file}'")
        console.print("⚙️ Перезапуск бэкенда для очистки пула соединений...")
        subprocess.run(["sudo", "systemctl", "restart", "ulysses-backend.service"], check=False)

    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Ошибка восстановления контура СУБД:[/red]")
        console.print(e.stderr or str(e))
    finally:
        if "PGPASSWORD" in os.environ:
            del os.environ["PGPASSWORD"]


@db.command(name="dump")
@click.option('--file', default=None, help='Путь к файлу дампа (по умолчанию: ~/Ulysses/dump/backup_latest.sql)')
def db_dump(file):
    """Создать дамп базы данных с ротацией (текущий + предыдущий) и проверкой целостности.

    Пример: uadmin db dump
    """
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

        with open(target, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(0, 2)
            fsize = f.tell()
            tail_size = min(4096, fsize)
            f.seek(fsize - tail_size)
            tail = f.read()

            if '-- PostgreSQL database dump complete' not in tail:
                raise ValueError("Дамп не завершён: отсутствует финальный комментарий pg_dump")

        console.print(f"[green]✓[/] Целостность дампа подтверждена")

        if not file:
            if os.path.exists(latest):
                shutil.move(latest, previous)
                console.print("[dim]  Предыдущий дамп → backup_previous.sql[/dim]")
            shutil.move(temp, latest)
            console.print(f"[green]✓[/] Дамп сохранён: {latest}")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Ошибка pg_dump:[/red]")
        console.print(e.stderr)
        if os.path.exists(target):
            os.remove(target)
    except ValueError as e:
        console.print(f"[red]❌ Дамп повреждён: {e}[/red]")
        if os.path.exists(target):
            os.remove(target)
        console.print("[yellow]⚠[/] Предыдущий дамп НЕ заменён.")
    finally:
        if "PGPASSWORD" in os.environ:
            del os.environ["PGPASSWORD"]
        if os.path.exists(temp):
            os.remove(temp)

@db.command(name="query")
@click.argument('sql', required=True)
def db_query(sql):
    """Выполнить произвольный SQL-запрос к БД и вывести результат в виде таблицы.

    Поддерживает SELECT, а также INSERT/UPDATE/DELETE с фиксацией (COMMIT).
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor
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

    # Определяем тип операции
    is_mutation = any(sql.strip().upper().startswith(word) for word in ["DELETE", "UPDATE", "INSERT"])

    try:
        # Открываем чистое соединение
        conn = psycopg2.connect(
            dbname=db_name, user=db_user, password=db_pass, host=db_host, port=db_port
        )
        # Использование RealDictCursor позволяет читать ключи по именам колонок
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(sql)

        if is_mutation:
            conn.commit() # 🌟 НАСТОЯЩИЙ КОММИТ ИЗМЕНЕНИЙ НА ДИСК!
            # Получаем количество измененных строк
            affected = cur.rowcount
            console.print(f"[green]✅ Инструкция успешно применена. Изменения зафиксированы (COMMIT).[/green]")
            console.print(f"   [dim]Затронуто строк в базе: {affected}[/dim]")
        else:
            # Если это SELECT — читаем строки и строим таблицу
            rows = cur.fetchall()
            if not rows:
                console.print("[dim](пусто)[/dim]")
            else:
                table = Table()
                # Берем ключи из первой строки в качестве колонок
                for key in rows[0].keys():
                    table.add_column(key, style="cyan")
                for row in rows:
                    table.add_row(*[str(v) if v is not None else "—" for v in row.values()])
                console.print(table)

        cur.close()
        conn.close()

    except Exception as e:
        console.print(f"[red]❌ Ошибка выполнения SQL-команды: {e}[/red]")


if __name__ == "__main__":
    db(prog_name="uadmin db")
