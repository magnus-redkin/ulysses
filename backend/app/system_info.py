import os
import shutil
import subprocess
import socket
import logging

logger = logging.getLogger(__name__)

async def collect_system_metrics() -> dict:
    """
    Утилитарная функция сбора реальных метрик сервера.
    Возвращает структурированный словарь, готовый для API и CLI.
    """
    # 1. Проверка диска
    disk_free_pct = 0.0
    try:
        total, used, free = shutil.disk_usage("/")
        disk_free_pct = round((free / total) * 100, 1)
    except Exception as e:
        logger.error(f"Ошибка проверки диска: {e}")

    # 2. Проверка оперативной памяти (RAM)
    free_ram_pct = 0.0
    if os.path.exists("/proc/meminfo"):
        try:
            meminfo = {}
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = parts[1].split()
            total_mem = float(meminfo.get('MemTotal', [1])[0])
            avail_mem = float(meminfo.get('MemAvailable', [0])[0])
            free_ram_pct = round((avail_mem / total_mem) * 100, 1)
        except Exception as e:
            logger.error(f"Ошибка проверки RAM: {e}")
    else:
        free_ram_pct = 15.0  # Заглушка для локальной разработки (mac/win)

    # 3. Проверка PostgreSQL
    pg_running = subprocess.run(["pg_isready", "-q"]).returncode == 0
    postgres_status = "RUNNING" if pg_running else "OFFLINE"

    # 4. Проверка Telegram-бота через systemctl
    bot_running = subprocess.run(["systemctl", "is-active", "--quiet", "ulysses-bot.service"]).returncode == 0
    bot_status = "RUNNING" if bot_running else "DOWN"

    # 5. Проверка доступности порта бэкенда FastAPI
    backend_online = False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", 8000))
        backend_online = True
    except Exception:
        backend_online = False
    finally:
        s.close()

    # Считаем систему здоровой, если критические компоненты запущены
    is_healthy = pg_running and bot_running and backend_online

    return {
        "status": "ok" if is_healthy else "error",
        "disk_free_percent": disk_free_pct,
        "ram_available_percent": free_ram_pct,
        "postgres_status": postgres_status,
        "telegram_bot_status": bot_status,
        "backend_status": "ONLINE" if backend_online else "OFFLINE"
    }
