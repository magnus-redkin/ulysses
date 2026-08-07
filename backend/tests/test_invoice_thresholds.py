# tests/test_invoice_thresholds.py
"""
Тест: порог INVOICE_DIRTY_HOURS применяется в админ-сервисе.
Запуск: utest backend/tests/test_invoice_thresholds.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_invoice_dirty_hours_in_settings():
    """Параметр INVOICE_DIRTY_HOURS должен быть в settings и иметь разумное значение."""
    from app.config import settings

    hours = settings.INVOICE_DIRTY_HOURS
    assert hours > 0, f"INVOICE_DIRTY_HOURS должен быть > 0, получено {hours}"
    assert hours <= 168, f"Подозрительно большое значение: {hours} часов (неделя+)"
    print(f"  INVOICE_DIRTY_HOURS = {hours}")
    print("✅ test_invoice_dirty_hours_in_settings PASSED")


def test_admin_service_uses_dirty_hours():
    """Код admin_service.py должен использовать settings.INVOICE_DIRTY_HOURS."""
    admin_service_path = Path(__file__).parent.parent / "app" / "services" / "admin_service.py"
    with open(admin_service_path) as f:
        source = f.read()

    assert "INVOICE_DIRTY_HOURS" in source, (
        "❌ admin_service.py не использует INVOICE_DIRTY_HOURS из settings.\n"
        "   Убедись, что в get_diagnostics и cleanup_invoices используется settings.INVOICE_DIRTY_HOURS."
    )
    # Проверяем, что нет хардкода '2 days' или '24 hours'
    assert "'2 days'" not in source, "❌ Всё ещё используется хардкод '2 days'"
    assert "INTERVAL '24 hours'" not in source, "❌ Всё ещё используется хардкод '24 hours'"
    print("  admin_service.py использует INVOICE_DIRTY_HOURS")
    print("✅ test_admin_service_uses_dirty_hours PASSED")


def main():
    test_invoice_dirty_hours_in_settings()
    test_admin_service_uses_dirty_hours()


if __name__ == "__main__":
    main()
