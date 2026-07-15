# tests/set_env.py
"""
Модуль для загрузки переменных окружения из .env файла.
Импортируется в начале каждого теста через прямой путь.
"""
import os
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path
_current_file = Path(__file__).resolve()
_project_root = _current_file.parent.parent
sys.path.insert(0, str(_project_root))

def load_env():
    """Загрузка .env файла в переменные окружения"""
    env_paths = [
        _project_root.parent / ".env",      # ~/Ulysses/.env
        _project_root / ".env",              # ~/Ulysses/ulysses-backend/.env
    ]

    for env_path in env_paths:
        if env_path.exists():
            print(f"📂 Загружаю .env из: {env_path}")
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Убираем кавычки и пробелы
                        value = value.strip().strip('"').strip("'")
                        os.environ[key.strip()] = value

            print(f"   ✅ Загружено переменных: {len(os.environ)}")
            return True

    print("⚠️ .env файл не найден!")
    return False

# Автоматически загружаем при импорте
load_env()
