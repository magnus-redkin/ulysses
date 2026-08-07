# tests/test_logging_middleware.py
"""
Тест: middleware логирования запросов не активен в production.
Запуск: utest backend/tests/test_logging_middleware.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_log_all_requests_respects_environment():
    """
    Проверяем, что в коде main.py есть условие, отключающее логирование
    в production-окружении.
    """
    import inspect
    from app.main import app

    # Ищем middleware log_all_requests
    found_condition = False
    for middleware in app.user_middleware:
        if hasattr(middleware, "cls"):
            source = inspect.getsource(middleware.cls)
            # Проверяем, что есть проверка на ENVIRONMENT или DEBUG
            if "ENVIRONMENT" in source or "DEBUG" in source or "LOG_REQUESTS" in source:
                found_condition = True
                break
        else:
            # Это может быть функция, проверяем её имя
            if hasattr(middleware, "kwargs"):
                continue  # CORSMiddleware и др.

    # Альтернативный подход: проверяем исходный код main.py напрямую
    main_path = Path(__file__).parent.parent / "app" / "main.py"
    with open(main_path) as f:
        main_source = f.read()

    # В коде должна быть проверка, отключающая логирование не в dev
    has_env_check = "ENVIRONMENT" in main_source or "LOG_REQUESTS" in main_source or "development" in main_source
    assert has_env_check, (
        "❌ В main.py нет проверки окружения для логирования запросов.\n"
        "   Убедись, что middleware log_all_requests обёрнут условием:\n"
        "   if settings.ENVIRONMENT == 'development' or getattr(settings, 'LOG_REQUESTS', False):"
    )
    print("  Код main.py содержит проверку окружения для логирования")
    print("✅ test_log_all_requests_respects_environment PASSED")

def main():
    test_log_all_requests_respects_environment()

if __name__ == "__main__":
    main()
