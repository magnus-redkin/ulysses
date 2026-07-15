# cli/brain/db.py
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

_env_loaded = False
_connection = None

def _load_env():
    global _env_loaded
    if _env_loaded:
        return
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
    _env_loaded = True

def get_connection():
    """Возвращает синхронное psycopg2-соединение к БД."""
    global _connection
    if _connection is not None and not _connection.closed:
        return _connection

    _load_env()
    _connection = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "ulysses_db"),
        user=os.getenv("DB_USER", "ulysses_admin"),
        password=os.getenv("DB_PASS", "")
    )
    _connection.autocommit = False
    return _connection

def query(sql: str, params: dict = None) -> list[dict]:
    """Выполнить SELECT и вернуть список словарей."""
    conn = get_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params or {})
        return cur.fetchall()

def execute(sql: str, params: dict = None) -> int:
    """Выполнить INSERT/UPDATE/DELETE. Вернуть количество затронутых строк."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params or {})
        conn.commit()
        return cur.rowcount

def close():
    global _connection
    if _connection is not None and not _connection.closed:
        _connection.close()
        _connection = None
