#!/usr/bin/env python3
"""
Запуск всех тестов Ulysses Lab.
Использование: utest backend/tests/run_all.py
"""
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# Новые тесты (безопасность, SSL, upsert, транзакции)
NEW_TESTS = [
    "test_billing_auth.py",
    "test_user_upsert.py",
    "test_free_subscription.py",
    "test_hiddify_ssl.py",
    "test_bot_token_config.py",
    "test_logging_middleware.py",
    "test_transaction_rollback.py",
    "test_invoice_thresholds.py",
    "test_platega_webhook.py",
]

# Восстановленные старые тесты
OLD_TESTS = [
    "test_01_create_user_email.py",
    "test_02_create_user_telegram.py",
    "test_03_subscription_renewal.py",
    "test_04_user_info.py",
    "test_05_free_tariff.py",
    "test_07_admin_stats.py",
    "test_08_idempotency_webhooks.py",
]

ALL_TESTS = NEW_TESTS + OLD_TESTS


def run_test(test_file: str) -> tuple[str, bool, str]:
    """Запускает один тест. Возвращает (имя, успех, вывод)."""
    test_path = TESTS_DIR / test_file
    if not test_path.exists():
        return test_file, False, f"Файл не найден: {test_path}"

    try:
        result = subprocess.run(
            [sys.executable, str(test_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(TESTS_DIR.parent.parent)  # Ulysses/
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        return test_file, success, output
    except subprocess.TimeoutExpired:
        return test_file, False, "Тест превысил лимит времени (120с)"
    except Exception as e:
        return test_file, False, str(e)


def main():
    print("=" * 60)
    print("🧪 ULYSSES LAB — ЗАПУСК ВСЕХ ТЕСТОВ")
    print("=" * 60)
    print(f"Всего тестов: {len(ALL_TESTS)}")
    print(f"  Новых: {len(NEW_TESTS)}")
    print(f"  Восстановленных: {len(OLD_TESTS)}")
    print()

    passed = 0
    failed = 0
    results = []

    for i, test_file in enumerate(ALL_TESTS, 1):
        print(f"[{i}/{len(ALL_TESTS)}] {test_file}...", end=" ", flush=True)
        name, success, output = run_test(test_file)

        if success:
            print("✅")
            passed += 1
        else:
            print("❌")
            failed += 1
            results.append((name, output))

    print("\n" + "=" * 60)
    print(f"📊 ИТОГО: {passed} пройдено, {failed} провалено из {len(ALL_TESTS)}")
    print("=" * 60)

    if failed > 0:
        print("\n❌ ПРОВАЛЕННЫЕ ТЕСТЫ:")
        for name, output in results:
            print(f"\n--- {name} ---")
            # Показываем последние 20 строк вывода
            lines = output.strip().split("\n")
            for line in lines[-20:]:
                print(f"  {line}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
