# ulysses-backend/tests/run_all.py

import subprocess
import sys
from pathlib import Path

def main():
    tests_dir = Path(__file__).parent

    # 🟢 ИСПРАВЛЕНО: Теперь скрипт ищет тесты и в корне, и рекурсивно в подпапках (включая integration/)
    tests = sorted(list(tests_dir.glob("test_*.py")) + list(tests_dir.glob("integration/test_*.py")))

    print("=" * 60)
    print("🚀 ЗАПУСК ПОЛНОЙ СБОРКИ ВСЕХ ТЕСТОВ ULYSSES VPN")
    print("=" * 60)

    passed = 0
    failed = 0
    results = []

    for test in tests:
        # Получаем относительный путь для красивого отображения в логах
        rel_path = test.relative_to(tests_dir)
        print(f"\n📝 Запуск: {rel_path}...")

        # Выполняем подпроцесс теста
        result = subprocess.run(
            [sys.executable, str(test)],
            capture_output=False
        )

        # 🟢 ИСПРАВЛЕНО: Считываем честные exit-коды (0 = успех, 1 = провал)
        if result.returncode == 0:
            passed += 1
            results.append(f"✅ {rel_path}")
        else:
            failed += 1
            results.append(f"❌ {rel_path}")

    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЕ РЕЗУЛЬТАТЫ СБОРКИ:")
    for r in results:
        print(f"   {r}")
    print(f"\n✅ Успешно пройдено: {passed}")
    print(f"❌ Обнаружено сбоев: {failed}")
    print("=" * 60)

    return failed == 0

if __name__ == "__main__":
    # Выходим со статусом 0, если все тесты зеленые, или 1, если есть хоть один сбой
    sys.exit(0 if main() else 1)
