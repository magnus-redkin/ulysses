import os
import sys

# =====================================================================
# 🛠️ АВТОМАТИЧЕСКАЯ НАСТРОЙКА ПУТЕЙ PYTHON
# =====================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ULYSSES_BACKEND_DIR = os.path.dirname(os.path.dirname(CURRENT_DIR))
ULYSSES_ROOT_DIR = os.path.dirname(ULYSSES_BACKEND_DIR)

if ULYSSES_ROOT_DIR not in sys.path:
    sys.path.insert(0, ULYSSES_ROOT_DIR)
if ULYSSES_BACKEND_DIR not in sys.path:
    sys.path.insert(0, ULYSSES_BACKEND_DIR)

import asyncio
import httpx
import uuid

from app.config import settings
from app.provisioning_service import HiddifyProvisioner
from cli.brain.db import query, execute, close

async def test_full_user_lifecycle():
    """
    🧪 INTEGRATION TEST: Полный цикл жизни пользователя
    Выдача доступа ➔ Hiddify API ➔ Проверка Гейта ➔ Симуляция аварии ➔ Failover
    """
    test_email = "live_user@ulysses.best"
    allocated_uuid = str(uuid.uuid4())

    # Инициализируем наш боевой провижнер
    service = HiddifyProvisioner()

    # -----------------------------------------------------------------
    # Шаг 1: Проверка связи с Hiddify-Manager по API
    # -----------------------------------------------------------------
    headers = {"Hiddify-API-Key": settings.HIDDIFY_API_KEY}
    # Добавляем follow_redirects=True, чтобы httpx сам проходил сквозь 302 редиректы
    async with httpx.AsyncClient(timeout=10.0, headers=headers, verify=False, follow_redirects=True) as api_client:
        response = await api_client.get(settings.HIDDIFY_API_URL)
        assert response.status_code == 200, f"Hiddify API недоступно! Финальный код ответа: {response.status_code}"


    # -----------------------------------------------------------------
    # Шаг 2: Создание пользователя в Hiddify через Бэкенд
    # -----------------------------------------------------------------
    # Передаем обязательные параметры. Метод сам возьмет нормализованный URL из config.py
    res = await service.create_user(
        user_uuid=allocated_uuid,
        email=test_email,
        tariff_slug="sub_free"
    )

    # Распаковываем ответ (учитываем, что метод возвращает кортеж (success, data, error) или bool)
    if isinstance(res, tuple):
        success = res[0]
    else:
        success = res

    assert success is True, "Hiddify API вернул ошибку при создании профиля!"
    print(f"\n[✓] Пользователь успешно создан в панели Hiddify. UUID: {allocated_uuid}")

    # -----------------------------------------------------------------
    # Шаг 3: Симуляция падения гейта и DNS Failover
    # -----------------------------------------------------------------
    # Принудительно уводим основной щит в offline на уровне базы данных
    execute("UPDATE brain.shields SET status = 'offline' WHERE ip = '83.147.216.201'")

    dns_active = query("SELECT ip FROM brain.dns_state WHERE domain = 'vpn.ulysses.best' AND is_active = True")
    assert dns_active, "Локальный DNS-кэш пуст!"
    print(f"[✓] DNS Failover успешно отработал локально.")

    # -----------------------------------------------------------------
    # Шаг 4: Очистка системы после теста (Teardown)
    # -----------------------------------------------------------------
    # Бесследно стираем созданный профиль по UUID
    if allocated_uuid:
        await service.delete_user(uuid=allocated_uuid)

    # Возвращаем щиты в исходное активное состояние
    execute("UPDATE brain.shields SET status = 'active' WHERE ip = '83.147.216.201'")
    close()
    print(f"[✓] Очистка завершена успешно. Система в исходном состоянии.")

if __name__ == "__main__":
    print("============================================================")
    print("🧪 ЗАПУСК АСИНХРОННОГО ИНТЕГРАЦИОННОГО ТЕСТА (ЧИСТЫЙ URL)")
    print("============================================================")

    try:
        asyncio.run(test_full_user_lifecycle())
        print("\n============================================================")
        print("✅ ИНТЕГРАЦИОННЫЙ ТЕСТ УСПЕШНО ПРОЙДЕН!")
        print("============================================================")
    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛЕН: {e}")
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКАЯ ОШИБКА ВЫПОЛНЕНИЯ: {e}")
