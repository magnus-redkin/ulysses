# ulysses-backend/tests/integration/bot_tg_lifecycle.py

# ИНТЕГРАЦИОННЫЙ ТЕСТ: Полный сквозной цикл взаимодействия пользователя с Telegram-ботом.
# Имитирует действия реального клиента: первый запуск (/start), последовательный прогон
# по всем информационным кнопкам меню (О сервисе, Правила, Поддержка), проверку баланса,
# активацию бесплатного тестового периода и последующий выход из аккаунта (/logout).

import asyncio
import sys
from pathlib import Path

# Добавляем путь к папке тестов в системные пути для подключения хелперов
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.test_helpers import create_user_tg, get_user_balance, get_bot_state, cleanup_user

BASE_URL = "http://127.0.0.1:8000"
TEST_TG_ID = 777111222
TEST_TG_USERNAME = "ulysses_lifecycle_user"

async def run_bot_lifecycle_test():
    print("=" * 60)
    print("🧪 ЭМУЛЯЦИЯ СКВОЗНОГО ЖИЗНЕННОГО ЦИКЛА ПОЛЬЗОВАТЕЛЯ В ТГ")
    print("=" * 60)

    # ------------------------------------------------------------
    # ШАГ 0: Полная очистка перед стартом
    # ------------------------------------------------------------
    print("\n🧹 Шаг 0: Очистка окружения базы данных...")
    await cleanup_user(tg_id=TEST_TG_ID)
    await asyncio.sleep(0.3)
    print("   ✅ База готова к чистому тесту")

    # ------------------------------------------------------------
    # ШАГ 1: Имитация команды /start (Новый пользователь)
    # ------------------------------------------------------------
    print("\n📝 Шаг 1: Имитация отправки команды /start нового клиента...")
    state = await get_bot_state(TEST_TG_ID)
    assert state and state.get("state") == "new", "❌ Ошибка: Ожидался начальный статус 'new'"
    print(f"   ✅ Получен статус: {state.get('state')}")

    # ------------------------------------------------------------
    # ШАГ 2: Прогон по информационным кнопкам меню
    # ------------------------------------------------------------
    print("\n📝 Шаг 2: Прогон кликов по информационным экранам меню...")
    async with __import__("httpx").AsyncClient(timeout=10.0) as client:
        # Проверяем кнопку "О сервисе" (экшен show_about)
        res_about = await client.post(f"{BASE_URL}/api/bot/action", json={
            "tg_user_id": TEST_TG_ID, "action": "show_about", "payload": {}
        })
        assert res_about.status_code == 200 and res_about.json().get("state") == "info"
        print("   ✅ Экран 'О сервисе' успешно отрендерен")

        # Проверяем кнопку "Правила" (экшен show_rules)
        res_rules = await client.post(f"{BASE_URL}/api/bot/action", json={
            "tg_user_id": TEST_TG_ID, "action": "show_rules", "payload": {}
        })
        assert res_rules.status_code == 200 and res_rules.json().get("state") == "info"
        print("   ✅ Экран 'Правила использования' успешно отрендерен")

        # Проверяем кнопку "Поддержка" (экшен show_support)
        res_support = await client.post(f"{BASE_URL}/api/bot/action", json={
            "tg_user_id": TEST_TG_ID, "action": "show_support", "payload": {}
        })
        assert res_support.status_code == 200 and res_support.json().get("state") == "info"
        print("   ✅ Экран 'Техническая поддержка' успешно отрендерен")

        # Проверяем кнопку "Документы" (экшен show_rules)
        res_rules = await client.post(f"{BASE_URL}/api/bot/action", json={
            "tg_user_id": TEST_TG_ID, "action": "show_rules", "payload": {}
        })
        assert res_rules.status_code == 200 and res_rules.json().get("state") == "info"
        print("   ✅ Экран 'Документы / Правила' успешно отрендерен бэкендом")


    # ------------------------------------------------------------
    # ШАГ 3: Запрос тарифа и активация бесплатного триала
    # ------------------------------------------------------------
    print("\n📝 Шаг 3: Выбор бесплатного тарифа и запуск активации...")
    result_tariff = await create_user_tg(TEST_TG_ID, TEST_TG_USERNAME, "sub_free")
    assert result_tariff and result_tariff.get("state") == "payment_free", f"❌ Неожиданный ответ тарифа: {result_tariff}"
    print("   ✅ Бэкенд принял бесплатный инвойс и запустил фоновый процесс")

    # Ожидаем завершения асинхронной фоновой задачи воркера в provisioning_manager
    print("   ⏳ Ожидание ответа от VPN-ноды и фонового воркера (3 сек)...")
    await asyncio.sleep(3.0)

    # ------------------------------------------------------------
    # ШАГ 4: Проверка баланса и параметров подписки после активации
    # ------------------------------------------------------------
    print("\n📝 Шаг 4: Запрос баланса и проверка валидности туннеля...")
    balance = await get_user_balance(TEST_TG_ID)
    assert balance and balance.get("is_active"), "❌ Ошибка: Подписка должна быть активна"
    print(f"   ✅ Статус туннеля: Активен")
    print(f"   ✅ Срок действия: Осталось {balance.get('days_left')} дн.")
    print(f"   ✅ Постоянный UUID ключа: {balance.get('uuid')}")

    # ------------------------------------------------------------
    # ШАГ 5: Имитация команды /logout (Отвязка Telegram от профиля)
    # ------------------------------------------------------------
    print("\n📝 Шаг 5: Имитация отвязки аккаунта (команда /logout)...")
    async with __import__("httpx").AsyncClient(timeout=10.0) as client:
        res_logout = await client.post(f"{BASE_URL}/api/user/unlink-telegram", json={
            "tg_user_id": TEST_TG_ID,
            "tg_username": TEST_TG_USERNAME
        })

        assert res_logout.status_code == 200, f"❌ Ошибка отвязки: {res_logout.status_code}"
        print("   ✅ Сигнал на отвязку Telegram обработан успешно")

    # Проверяем, что по ТГ-идентификатору баланс больше недоступен
    balance_after_logout = await get_user_balance(TEST_TG_ID)
    assert balance_after_logout is None, "❌ Ошибка: Пользователь не должен находиться в ТГ-меню после отвязки"
    print("   ✅ Проверка подтверждена: аккаунт успешно отвязан от мессенджера")

    # ------------------------------------------------------------
    # ШАГ 6: Финальная каскадная очистка хвостов в БД
    # ------------------------------------------------------------
    print("\n🧹 Шаг 6: Финальная очистка тестовых записей...")
    await cleanup_user(tg_id=TEST_TG_ID)
    print("   ✅ База данных приведена в исходное состояние")
    return True

# В самом конце файла ulysses-backend/tests/integration/bot_tg_lifecycle.py

if __name__ == "__main__":
    success = False
    try:
        # Запускаем сквозную эмуляцию
        success = asyncio.run(run_bot_lifecycle_test())
    except AssertionError as e:
        print(f"\n❌ Критическая ошибка валидации логики: {e}")
    except Exception as e:
        print(f"\n❌ Непредвиденный сбой скрипта: {e}")
    finally:
        # 🌟 ГАРАНТИРОВАННЫЙ РУБЕЖ ЧИСТОТЫ: Выполнится даже при падении ассертов!
        print(f"\n🧹 [ФИНАЛИЗАТОР ТЕСТА] Очистка операционной среды...")
        try:
            from lib.test_helpers import cleanup_user
            # Вычищаем нашего жестко прописанного тест-юзера из базы
            asyncio.run(cleanup_user(tg_id=777111222))
            print("   ✅ Все интеграционные хвосты успешно удалены из PostgreSQL.")
        except Exception as err:
            print(f"   ❌ Не удалось запустить авто-клининг: {err}")

    print("\n" + "=" * 60)
    print("✅ ИНТЕГРАЦИОННЫЙ ТЕСТ УСПЕШНО ВЫПОЛНЕН!" if success else "❌ ТЕСТ ПРОВАЛЕН!")
    print("=" * 60)
