# cli/monitor.py
"""
Демон мониторинга Ulysses Shield.
Команды:
    uadmin monitor run    - запустить демон (бесконечный цикл проверок)
    uadmin monitor check  - однократный прогон всех проверок
    uadmin monitor status - показать последние результаты из памяти демона
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone

import click
from aiohttp import web

from cli.notify import send_admin_alert

console = ...  # если нужно, импортируем Console из rich
# Но для демона можно обойтись print или logging

# Настройки
HFM_HOST = os.getenv("HFM_HOST", "45.131.215.185")
HFM_SCRIPT = "~/monitor.sh"
GATE_IPS_FILE = os.getenv("GATE_IPS_FILE", "config/gate_ips.json")  # список ожидаемых IP гейтов
LOCAL_PORTS = {
    "backend": 8000,
    "postgresql": 5432,
    "web_frontend": 5173,
    "telegram_bot": None,  # проверим позже через процесс
}
CHECK_INTERVAL = 60  # секунд между полными циклами
ALERT_COOLDOWN = 900  # 15 минут между повторными алертами одной проблемы

# Хранилище результатов (обновляется демоном)
latest_results = {
    "timestamp": None,
    "local": {},
    "hfm": "",
    "alerts": [],
}

# Для дедупликации алертов: { проблема: время последнего алерта }
last_alert_time = {}

async def check_port(host, port, timeout=2):
    """Проверка TCP порта"""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

async def check_local_services():
    """Проверяет локальные сервисы Улисса"""
    results = {}
    # Бэкенд API
    results["backend_api"] = await check_port("127.0.0.1", 8000)
    # PostgreSQL
    results["postgresql"] = await check_port("127.0.0.1", 5432)
    # Web frontend (Vite)
    results["web_frontend"] = await check_port("127.0.0.1", 5173)
    # Telegram Bot – проверяем через наличие процесса
    try:
        # Пытаемся найти процесс бота
        proc = await asyncio.create_subprocess_exec(
            "pgrep", "-f", "bot/main.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        results["telegram_bot"] = proc.returncode == 0 and bool(stdout.strip())
    except Exception:
        results["telegram_bot"] = False

    # Системные метрики (диск, RAM)
    disk_usage = shutil.disk_usage("/")
    results["disk_free_percent"] = round(disk_usage.free / disk_usage.total * 100, 1)
    # RAM из /proc/meminfo
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        # Простой парсинг
        mem_total = int([l for l in meminfo.splitlines() if "MemTotal" in l][0].split()[1])
        mem_available = int([l for l in meminfo.splitlines() if "MemAvailable" in l][0].split()[1])
        results["ram_available_percent"] = round(mem_available / mem_total * 100, 1)
    except Exception:
        results["ram_available_percent"] = None

    return results

async def run_hfm_check(expected_ips):
    """Запускает monitor.sh на HFM через SSH и возвращает (success, output)"""
    cmd = ["ssh", HFM_HOST, f"{HFM_SCRIPT}"] + expected_ips
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode()
        success = "ALERT:" not in output
        return success, output
    except asyncio.TimeoutError:
        return False, "SSH timeout"
    except Exception as e:
        return False, str(e)

def load_gate_ips():
    """Загружает список ожидаемых IP гейтов из файла"""
    try:
        with open(GATE_IPS_FILE, "r") as f:
            data = json.load(f)
        # Ожидаем, что в файле массив из трёх IP
        return data[:3]  # g1, g2, g3
    except Exception:
        # Если файла нет, вернём пустые строки – проверки SOCKS5 пропустятся
        return ["", "", ""]

async def send_alert(message):
    """Отправляет алерт админу через send_admin_alert"""
    await send_admin_alert(message)

async def process_check_results(local, hfm_ok, hfm_output):
    """Анализирует результаты и отправляет алерты при необходимости"""
    now = time.time()
    alerts = []

    # Локальные сервисы
    for service, status in local.items():
        if isinstance(status, bool) and not status:
            problem = f"local_{service}_down"
            if now - last_alert_time.get(problem, 0) > ALERT_COOLDOWN:
                alerts.append(f"❌ {service} недоступен")
                last_alert_time[problem] = now

    # Системные ресурсы
    disk = local.get("disk_free_percent")
    if disk is not None and disk < 10:
        problem = "disk_low"
        if now - last_alert_time.get(problem, 0) > ALERT_COOLDOWN:
            alerts.append(f"⚠️ Свободное место на диске: {disk}%")
            last_alert_time[problem] = now

    ram = local.get("ram_available_percent")
    if ram is not None and ram < 10:
        problem = "ram_low"
        if now - last_alert_time.get(problem, 0) > ALERT_COOLDOWN:
            alerts.append(f"⚠️ Доступно RAM: {ram}%")
            last_alert_time[problem] = now

    # HFM
    if not hfm_ok:
        # Парсим ALERT строку
        alert_line = ""
        for line in hfm_output.splitlines():
            if line.startswith("ALERT:"):
                alert_line = line.replace("ALERT:", "").strip()
                break
        problem = f"hfm_{alert_line}" if alert_line else "hfm_fail"
        if now - last_alert_time.get(problem, 0) > ALERT_COOLDOWN:
            alerts.append(f"🔴 HFM Alert: {alert_line}")
            last_alert_time[problem] = now

    for msg in alerts:
        await send_alert(msg)

    return alerts

async def run_checks():
    """Один цикл проверок, возвращает словарь результатов"""
    # Локальные проверки
    local = await check_local_services()

    # HFM
    expected_ips = load_gate_ips()
    hfm_ok, hfm_output = await run_hfm_check(expected_ips)

    # Алертинг
    alerts = await process_check_results(local, hfm_ok, hfm_output)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "local": local,
        "hfm_output": hfm_output,
        "alerts": alerts,
    }

async def monitor_daemon():
    """Бесконечный цикл мониторинга"""
    click.echo("🛡️ Демон мониторинга запущен.")
    # Запускаем HTTP-сервер для status
    app = web.Application()
    app.router.add_get("/status", lambda request: web.json_response(latest_results))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 9898)
    await site.start()
    click.echo("HTTP статус-сервер на http://localhost:9898/status")

    try:
        while True:
            results = await run_checks()
            latest_results.update(results)
            await asyncio.sleep(CHECK_INTERVAL)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()

# ---------- CLI команды ----------
@click.group()
def monitor():
    """Мониторинг инфраструктуры Ulysses Shield"""

@monitor.command()
@click.pass_context
def check(ctx):
    """Однократная проверка всех систем"""
    async def _run():
        results = await run_checks()
        # Извлекаем hfm_output, чтобы напечатать отдельно
        hfm = results.pop("hfm_output", "")
        # Печатаем чистый JSON оставшихся данных
        print(json.dumps(results, indent=2, ensure_ascii=False))
        if hfm:
            print("\n📡 HFM Health Check:")
            print(hfm)
    asyncio.run(_run())

@monitor.command()
def run():
    """Запустить демон мониторинга"""
    asyncio.run(monitor_daemon())

@monitor.command()
def status():
    """Показать последние результаты мониторинга"""
    import urllib.request, json
    try:
        with urllib.request.urlopen("http://localhost:9898/status") as resp:
            data = json.loads(resp.read())
        # Извлекаем и красиво печатаем HFM-отчёт отдельно
        hfm = data.pop("hfm_output", "")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        if hfm:
            print("\n📡 HFM Health Check:")
            print(hfm)
    except Exception as e:
        print(f"Не удалось получить статус: {e}")
