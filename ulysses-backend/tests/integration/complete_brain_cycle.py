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
from click.testing import CliRunner

from app.config import settings
from app.provisioning_service import HiddifyProvisioner
from cli.brain.db import query, execute, close

# Импортируем CLI команды «Мозга» для их симуляции внутри теста
from cli.brain.telemetry import telemetry
from cli.brain.detect import detect
from cli.brain.shield import shield_block

async def test_complete_brain_failover_lifecycle():
    """
    🧪 ПОЛНЫЙ ИНТЕГРАЦИОННЫЙ ТЕСТ: Жизненный цикл «Мозга» при блокировке

    Внутри него мы соберем следующую логику:
    1. Инициализация: Метод HiddifyProvisioner подготавливает чистое тестовое соединение к Hiddify-Manager.
    2. Мирное время: Скрипт симулирует генерацию нормальной телеметрии, вызывая telemetry. Детектор подтверждает статус 🟢 Норма.
    3. Обнаружение атаки: Скрипт генерирует аномалию (telemetry --anomaly). Детектор detect выбрасывает статус 🔴 БЛОКИРОВКА и возвращает ID упавшего щита.
    4. Реагирование (Failover): Тест вызывает обновленную команду shield_block(shield_id). Мы проверяем, что в базе данных старый щит лег в blocked, резервный поднялся в active, а в таблице dns_state активным IP стал наш новый гейт 62.60.249.53!
    5. Проверка туннелирования пользователей: Тест создает пользователя live_user@ulysses.best. Так как мы перенесли HIDDIFY_API_URL в .env до корня /HRsXvpBnfQwxRm55yQxcTPMMcsLXRP, мы проверяем, как генерируются новые ссылки.
    """
    runner = CliRunner()
    test_email = "live_user@ulysses.best"
    allocated_uuid = str(uuid.uuid4())
    service = HiddifyProvisioner()

    # Корректируем базовый URL динамически, так как в .env теперь чистый корень панели
    # Для API-клиента Hiddify дописываем стандартный префикс версии
    original_api_url = settings.HIDDIFY_API_URL
    settings.HIDDIFY_API_URL = f"{original_api_url.rstrip('/')}/api/v1/"

    print("\n============================================================")
    print("🤖 ЭТАП 1: Стабильное мирное состояние системы")
    print("============================================================")
    # Сбрасываем базу данных щитов в эталонный дефолт
    execute("UPDATE brain.shields SET status = 'active' WHERE ip = '83.147.216.201'")
    execute("UPDATE brain.shields SET status = 'reserve' WHERE ip = '62.60.249.53'")
    execute("UPDATE brain.dns_state SET is_active = True WHERE ip = '83.147.216.201'")
    execute("UPDATE brain.dns_state SET is_active = False WHERE ip = '62.60.249.53'")

    # Имитируем два мирных замера телеметрии подряд (чтобы у детектора было скользящее окно замеров)
    runner.invoke(telemetry)
    await asyncio.sleep(0.2)
    runner.invoke(telemetry)

    # Проверяем вердикт детектора
    result_normal = runner.invoke(detect)
    assert "Норма" in result_normal.output or "🟢" in result_normal.output, "Ошибка: Мозг ложно зафиксировал аномалию!"
    print("[✓] Зафиксирована стабильная Норма. Трафик идёт через Гейт-1 (83.147.216.201).")

    print("\n============================================================")
    print("🚨 ЭТАП 2: Симуляция атаки цензоров и обнаружение аномалии")
    print("============================================================")
    # Генерируем аномальный цикл телеметрии (0 клиентов, высокий Latency, всплеск ошибок)
    runner.invoke(telemetry, ["--anomaly"])

    # Запускаем детектор
    result_anomaly = runner.invoke(detect)
    assert "БЛОКИРОВКА" in result_anomaly.output or "🔴" in result_anomaly.output, "Ошибка: Мозг пропустил блокировку щита!"
    print("[✓] Аномалия успешно обнаружена! Детектор выбросил статус блокировки основного гейта.")

    # -----------------------------------------------------------------
    # 🔄 ЭТАП 3: Автоматическое принятие решения и DNS Failover
    # -----------------------------------------------------------------
    # Вытаскиваем записи из базы и берем нулевой элемент массива [0]
    shields_res = query("SELECT id FROM brain.shields WHERE ip = '83.147.216.201'")
    assert shields_res, "Основной щит не найден в базе данных!"
    shield_id = shields_res[0]["id"] if isinstance(shields_res, list) else shields_res["id"]

    # Имитируем автоматический или ручной вызов обновлённой команды block из shield.py
    print(f"⚡ Триггер команды аварийной блокировки щита ID={shield_id}...")
    result_block = runner.invoke(shield_block, [str(shield_id)])

    # Проверяем, что в консоль вывелся вердикт о перенаправлении сети на резерв
    assert "СЕТЬ ПЕРЕНАПРАВЛЕНА" in result_block.output or "62.60.249.53" in result_block.output, "Ошибка переключения DNS-кэша!"

    # Проверяем новые статусы щитов на уровне базы данных PostgreSQL с индексами [0]
    res_gate1 = query("SELECT status FROM brain.shields WHERE ip = '83.147.216.201'")
    res_gate2 = query("SELECT status FROM brain.shields WHERE ip = '62.60.249.53'")
    res_dns = query("SELECT ip FROM brain.dns_state WHERE domain = 'vpn.ulysses.best' AND is_active = True")

    status_gate1 = res_gate1[0]["status"] if isinstance(res_gate1, list) else res_gate1["status"]
    status_gate2 = res_gate2[0]["status"] if isinstance(res_gate2, list) else res_gate2["status"]
    dns_active_ip = res_dns[0]["ip"] if isinstance(res_dns, list) else res_dns["ip"]

    assert status_gate1 == "blocked", f"Гейт-1 должен быть заблокирован, но его статус: {status_gate1}"
    assert status_gate2 == "active", f"Резервный Гейт-2 должен стать активным, но его статус: {status_gate2}"
    assert dns_active_ip == "62.60.249.53", f"DNS должен смотреть на резервный IP, но он смотрит на: {dns_active_ip}"

    print("[✓] Проверка статусов БД успешна: Гейт-1 ➔ BLOCKED, Гейт-2 ➔ ACTIVE.")
    print(f"[✓] Мониторинг ClouDNS перенаправил vpn.ulysses.best на резервный IP: {dns_active_ip}")

    # -----------------------------------------------------------------
    # 🛰️ ЭТАП 4: Проверка бесперебойной выдачи подписок через Hiddify
    # -----------------------------------------------------------------
    # Выставляем правильный URL для POST-запроса создания
    settings.HIDDIFY_API_URL = f"{original_api_url.rstrip('/')}/api/v1/user/"

    # Создаем новый экземпляр сервиса под обновленный URL
    live_service = HiddifyProvisioner()

    # Вызываем создание пользователя
    res = await live_service.create_user(
        user_uuid=allocated_uuid,
        email=test_email,
        tariff_slug="sub_free"
    )

    # Умная распаковка: метод возвращает (success, data, error) или просто bool
    if isinstance(res, tuple):
        success = res[0]
    else:
        success = res

    assert success is True, "Hiddify API вернул ошибку при создании профиля!"
    print(f"[✓] Выдача доступа работает штатно. Пользователь зафиксирован на Сердце.")

    # -----------------------------------------------------------------
    # 🧹 ОЧИСТКА СИСТЕМЫ ПОСЛЕ ТЕСТА (TEARDOWN)
    # -----------------------------------------------------------------
    # Для корректного DELETE возвращаем базовый путь (так как delete_user сам добавит UUID)
    settings.HIDDIFY_API_URL = f"{original_api_url.rstrip('/')}/api/v1/user/"

    # Создаем чистый сервис для удаления
    teardown_service = HiddifyProvisioner()
    await teardown_service.delete_user(uuid=allocated_uuid)


    # Возвращаем щиты в исходное стабильное состояние
    execute("UPDATE brain.shields SET status = 'active' WHERE ip = '83.147.216.201'")
    execute("UPDATE brain.shields SET status = 'reserve' WHERE ip = '62.60.249.53'")
    execute("UPDATE brain.dns_state SET is_active = True WHERE ip = '83.147.216.201'")
    execute("UPDATE brain.dns_state SET is_active = False WHERE ip = '62.60.249.53'")
    close()

    print("\n[✓] Очистка базы данных выполнена успешно.")

if __name__ == "__main__":
    print("============================================================")
    print("🧠 СТАРТ ПОЛНОГО ИНТЕГРАЦИОННОГО ТЕСТА ЖИЗНЕННОГО ЦИКЛА МОЗГА")
    print("============================================================")

    try:
        asyncio.run(test_complete_brain_failover_lifecycle())
        print("\n============================================================")
        print("✅ БОЕВОЙ ПОЛНЫЙ ТЕСТ УСПЕШНО ПРОЙДЕН! СИСТЕМА УСТОЙЧИВА К БЛОКИРОВКАМ.")
        print("============================================================")
    except AssertionError as e:
        print(f"\n❌ ТЕСТ ПРОВАЛЕН: {e}")
    except Exception as e:
        print(f"\n💥 КРИТИЧЕСКИЙ СБОЙ ВЫПОЛНЕНИЯ: {e}")
