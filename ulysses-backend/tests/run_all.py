#!/usr/bin/env python3
"""Запуск всех тестов"""

import subprocess
import sys
from pathlib import Path

def main():
    tests_dir = Path(__file__).parent
    tests = sorted(tests_dir.glob("test_*.py"))

    print("=" * 60)
    print("🚀 ЗАПУСК ВСЕХ ТЕСТОВ")
    print("=" * 60)

    passed = 0
    failed = 0
    results = []

    for test in tests:
        name = test.stem
        print(f"\n📝 {name}...")

        result = subprocess.run(
            [sys.executable, str(test)],
            capture_output=False
        )

        if result.returncode == 0:
            passed += 1
            results.append(f"✅ {name}")
        else:
            failed += 1
            results.append(f"❌ {name}")

    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ:")
    for r in results:
        print(f"   {r}")
    print(f"\n✅ Пройдено: {passed}")
    print(f"❌ Не пройдено: {failed}")
    print("=" * 60)

    return failed == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
