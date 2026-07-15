# tests/test_11_security_check.py
#!/usr/bin/env python3
"""
Тест 11: Проверка безопасности - поиск захардкоженных секретов
"""

import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Загружаем переменные из .env
import tests.set_env

import os
import re
from pathlib import Path

# Загружаем секреты из .env для сравнения
def load_secrets_from_env():
    """Загружаем все секретные значения из .env"""
    secrets = set()

    env_path = Path.home() / "Ulysses" / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent.parent / ".env"

    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip().strip('"').strip("'")
                    # Собираем только реальные секреты (пароли, ключи, токены)
                    if any(s in key.upper() for s in ['PASS', 'TOKEN', 'KEY', 'SECRET']):
                        if value and len(value) > 8:  # Игнорируем короткие/пустые
                            secrets.add(value)

    return secrets

def find_hardcoded_secrets(secrets_to_find):
    """Поиск секретов в исходном коде"""

    project_root = Path(__file__).parent.parent
    found_secrets = []

    # Файлы для проверки (исключаем .env, тесты безопасности)
    files_to_check = []
    for pattern in ['app/**/*.py', 'cli/**/*.py', '*.py']:
        files_to_check.extend(project_root.glob(pattern))

    # Добавляем конкретные файлы
    files_to_check.extend([
        project_root / "test_email.py",
    ])

    # Убираем дубликаты и сам тест
    files_to_check = list(set(files_to_check))
    files_to_check = [f for f in files_to_check if 'test_11' not in str(f)]

    for file_path in files_to_check:
        if not file_path.exists() or file_path.suffix != '.py':
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')

            for line_num, line in enumerate(lines, 1):
                # Пропускаем комментарии и импорты
                if line.strip().startswith('#') or line.strip().startswith('import'):
                    continue

                # Ищем секреты
                for secret in secrets_to_find:
                    if secret in line:
                        # Проверяем, не является ли это чтением из env
                        if 'os.getenv' in line or 'settings.' in line or 'os.environ' in line:
                            continue  # Это нормально - чтение из конфига

                        # Проверяем, не тестовые ли это данные
                        if 'test_' in line or 'TEST_' in line or 'example.com' in line:
                            continue

                        found_secrets.append({
                            'file': str(file_path.relative_to(project_root)),
                            'line': line_num,
                            'secret_type': 'PASSWORD' if 'pass' in secret.lower() else 'API_KEY/TOKEN',
                            'line_content': line.strip()[:100]
                        })
        except Exception as e:
            print(f"   ⚠️ Не удалось проверить {file_path.name}: {e}")

    return found_secrets

def check_ssl_verify_false():
    """Проверка отключенной SSL проверки"""
    project_root = Path(__file__).parent.parent
    issues = []

    for py_file in project_root.glob('app/**/*.py'):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()

            if 'verify=False' in content:
                issues.append(str(py_file.relative_to(project_root)))
            if 'check_hostname = False' in content:
                issues.append(f"{py_file.relative_to(project_root)} (check_hostname)")
        except:
            pass

    return issues

def main():
    print("=" * 60)
    print("🔒 ТЕСТ 11: Проверка безопасности")
    print("=" * 60)

    all_ok = True

    # 1. Проверка захардкоженных секретов
    print("\n📋 Шаг 1: Поиск захардкоженных секретов...")

    secrets = load_secrets_from_env()
    print(f"   🔑 Загружено секретов из .env: {len(secrets)}")

    if not secrets:
        print("   ⚠️ Не удалось загрузить секреты из .env")
        all_ok = False
    else:
        found = find_hardcoded_secrets(secrets)

        if found:
            print(f"   🚨 НАЙДЕНО ЗАХАРДКОЖЕННЫХ СЕКРЕТОВ: {len(found)}")
            for item in found:
                print(f"   ❌ {item['file']}:{item['line']}")
                print(f"      Тип: {item['secret_type']}")
                print(f"      Код: {item['line_content']}")
            all_ok = False
        else:
            print("   ✅ Захардкоженных секретов не найдено!")

    # 2. Проверка SSL
    print("\n🔐 Шаг 2: Проверка SSL настроек...")

    ssl_issues = check_ssl_verify_false()

    if ssl_issues:
        print(f"   ⚠️ Найдена отключенная проверка SSL:")
        for issue in ssl_issues:
            print(f"   ⚠️ {issue}")
        print("   ℹ️ Это допустимо для development окружения")
        # Не считаем это ошибкой для dev
    else:
        print("   ✅ SSL проверки настроены правильно")

    # 3. Проверка .gitignore
    # 3. Проверка .gitignore
    print("\n📄 Шаг 3: Проверка .gitignore...")

    gitignore_paths = [
        Path(__file__).parent.parent / ".gitignore",
        Path(__file__).parent.parent.parent / ".gitignore",
    ]

    gitignore_found = False
    for gitignore_path in gitignore_paths:
        if gitignore_path.exists():
            gitignore_found = True
            with open(gitignore_path, 'r') as f:
                gitignore_content = f.read()

            required_entries = ['.env', '*.pyc', '__pycache__']
            missing = [e for e in required_entries if e not in gitignore_content]

            if missing:
                print(f"   ⚠️ В {gitignore_path.relative_to(Path.home())} отсутствуют:")
                for m in missing:
                    print(f"   ⚠️ - {m}")
            else:
                print(f"   ✅ {gitignore_path.relative_to(Path.home())} содержит необходимые правила")
            break

    if not gitignore_found:
        print("   ⚠️ .gitignore не найден ни в одной из ожидаемых локаций")

    # Итоги
    print("\n" + "=" * 60)
    if all_ok:
        print("✅ ТЕСТ 11 ПРОЙДЕН! Критических проблем безопасности не найдено.")
    else:
        print("❌ ТЕСТ 11 НЕ ПРОЙДЕН! Обнаружены проблемы безопасности.")
        print("\n📝 Рекомендации по исправлению:")
        print("   1. Замените хардкод на os.getenv() или settings.")
        print("   2. Переместите все секреты в .env файл")
        print("   3. Добавьте .env в .gitignore")
    print("=" * 60)

    return all_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
