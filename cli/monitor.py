# cli/monitor.py
"""
Демон мониторинга Ulysses Shield.
Команды:
    uadmin monitor run    - запустить демон (бесконечный цикл проверок)
    uadmin monitor check  - однократный прогон всех проверок
    uadmin monitor status - показать последние результаты из памяти демона

Для мониторинга используется ключ ~/.ssh/id_monitor, ограниченный на нодах
через command="~/check_*.sh". Чтобы node_manager и автоматика продолжали
работать со своими ключами, в ~/.ssh/config заведены отдельные алиасы
с суффиксом '-mon' (nl-mon, bg-mon, ru-mon).
"""

import asyncio
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import click
import aiohttp
from aiohttp import web

from cli.notify import send_admin_alert  # noqa: F401  (реэкспорт для совместимости)


# ---------- Настройки ----------
HFM_SCRIPT = os.getenv("HFM_MONITOR_SCRIPT", "~/check_hiddify.sh")
RF_SSH_HOST = os.getenv("RF_MONITOR_HOST", "ru").strip()      # короткое имя из ~/.ssh/config
RF_SCRIPT = os.getenv("RF_MONITOR_SCRIPT", "~/check_rf.sh")
NODES_FILE = Path(__file__).resolve().parent.parent / "backend" / "app" / "private" / "nodes.json"

MON_SUFFIX = "-mon"

LOCAL_SERVICES = {
    "backend": "ulysses-backend",
    "web": "ulysses-web",
    "bot": "ulysses-bot",
    "postgresql": "postgresql",
}

CHECK_INTERVAL = 60          # секунд между полными циклами
ALERT_COOLDOWN = 900         # 15 минут между повторными алертами одной проблемы
HTTP_STATUS_PORT = 9898


# Хранилище последних результатов
latest_results = {
    "timestamp": None,
    "local": {},
    "hfm": {},
    "alerts": [],
}

# { problem_key: unix_time_last_alert }
last_alert_time = {}


# ---------- Утилиты ----------

def _strip_mon(host: str) -> str:
    """Убирает суффикс '-mon' для отображения."""
    return host[:-len(MON_SUFFIX)] if host.endswith(MON_SUFFIX) else host


def load_check_targets() -> dict[str, str]:
    """
    Возвращает {ssh_host: script} для всех узлов, которые надо проверить.
    HFM-ноды — из nodes.json, RF-нода — из env.
    К имени хоста добавляется суффикс '-mon' — он указывает на алиас
    в ~/.ssh/config с ограниченным ключом id_monitor.
    """
    targets: dict[str, str] = {}

    # HFM-ноды (nl, bg, ...)
    try:
        with open(NODES_FILE, "r") as f:
            data = json.load(f)
        for host in (data.get("subdomains") or []):
            host = str(host).strip()
            if host:
                targets[f"{host}{MON_SUFFIX}"] = HFM_SCRIPT
    except Exception as e:
        click.echo(f"⚠️ Не удалось прочитать {NODES_FILE}: {e}")

    # RF-нода
    if RF_SSH_HOST:
        targets[f"{RF_SSH_HOST}{MON_SUFFIX}"] = RF_SCRIPT

    return targets


async def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def systemd_active(unit: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", "--quiet", unit,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await asyncio.wait_for(proc.wait(), timeout=5)
        return rc == 0
    except Exception:
        return False


def _read_meminfo() -> tuple[float | None, float | None]:
    try:
        with open("/proc/meminfo") as f:
            lines = f.read().splitlines()
        mem_total = next(int(l.split()[1]) for l in lines if l.startswith("MemTotal"))
        mem_avail = next(int(l.split()[1]) for l in lines if l.startswith("MemAvailable"))
        return round(mem_avail / mem_total * 100, 1), round((mem_total - mem_avail) / mem_total * 100, 1)
    except Exception:
        return None, None


def _read_loadavg() -> tuple[float, float, float] | None:
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
        return float(parts[0]), float(parts[1]), float(parts[2])
    except Exception:
        return None


def _extract_counters(output: str) -> tuple[int | None, int | None]:
    """Вытаскивает 'Пройдено/Провалено' из вывода check-скрипта."""
    m_pass = re.search(r"Пройдено проверок:\s*(\d+)", output)
    m_fail = re.search(r"Провалено проверок:\s*(\d+)", output)
    passed = int(m_pass.group(1)) if m_pass else None
    failed = int(m_fail.group(1)) if m_fail else None
    return passed, failed


def _extract_summary_block(output: str) -> str | None:
    """
    Возвращает оригинальный блок с 'Пройдено/Провалено' как есть,
    вместе с обрамляющими линиями '===='.
    """
    lines = output.splitlines()
    idx = None
    for i, line in enumerate(lines):
        if "Пройдено проверок:" in line:
            idx = i
            break
    if idx is None:
        return None

    start = max(0, idx - 1)
    end = min(len(lines), idx + 3)  # idx, idx+1, idx+2
    return "\n".join(lines[start:end])


# ---------- Проверки ----------

async def check_local_services() -> dict:
    """Проверяет локальные сервисы Улисса."""
    results: dict = {}

    for key, unit in LOCAL_SERVICES.items():
        results[f"unit_{key}"] = await systemd_active(unit)

    results["port_backend"] = await check_port("127.0.0.1", 8000)
    results["port_postgresql"] = await check_port("127.0.0.1", 5432)
    results["port_web_prod"] = await check_port("127.0.0.1", 3000)

    try:
        du = shutil.disk_usage("/")
        results["disk_free_percent"] = round(du.free / du.total * 100, 1)
        results["disk_free_gb"] = round(du.free / (1024 ** 3), 2)
    except Exception:
        results["disk_free_percent"] = None
        results["disk_free_gb"] = None

    avail_pct, used_pct = _read_meminfo()
    results["ram_available_percent"] = avail_pct
    results["ram_used_percent"] = used_pct

    la = _read_loadavg()
    if la:
        results["load_1m"] = la[0]
        results["load_5m"] = la[1]
        results["load_15m"] = la[2]

    results["rf_node_api"] = await check_rf_node()

    return results


async def check_rf_node() -> bool:
    """Проверка RF-ноды через /health (API на 9000)."""
    try:
        from app.config import settings
    except Exception:
        return True

    url = (getattr(settings, "RF_NODE_API_URL", "") or "").rstrip("/")
    token = getattr(settings, "RF_NODE_API_TOKEN", "") or ""
    enabled = getattr(settings, "RF_NODE_ENABLED", False)

    if not enabled or not url or not token:
        return True

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(
                f"{url}/health",
                headers={"Authorization": f"Bearer {token}"},
            ) as r:
                return r.status == 200
    except Exception:
        return False


async def run_ssh_check(host: str, script: str) -> tuple[bool, str]:
    """Запускает указанный скрипт на удалённом хосте через SSH."""
    cmd = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        host, script,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode(errors="replace")
        if proc.returncode != 0 and not output:
            output = f"(exit code {proc.returncode}) {stderr.decode(errors='replace')[:500]}"
        ok = "ALERT:" not in output and proc.returncode == 0
        return ok, output
    except asyncio.TimeoutError:
        return False, "SSH timeout"
    except Exception as e:
        return False, f"SSH error: {e}"


async def run_all_checks(targets: dict[str, str]) -> dict[str, tuple[bool, str]]:
    """Параллельно проверяет все узлы. Возвращает {host: (ok, output)}."""
    if not targets:
        return {}
    tasks = {
        host: asyncio.create_task(run_ssh_check(host, script))
        for host, script in targets.items()
    }
    out: dict[str, tuple[bool, str]] = {}
    for host, task in tasks.items():
        try:
            out[host] = await task
        except Exception as e:
            out[host] = (False, f"task error: {e}")
    return out


# ---------- Алертинг ----------

async def send_alert(message: str) -> None:
    try:
        ok = await send_admin_alert(message)
        if not ok:
            click.echo(f"⚠️ Alert not sent: {message}")
    except Exception as e:
        click.echo(f"❌ Alert error: {e} — {message}")


def _should_alert(problem: str, now: float) -> bool:
    return now - last_alert_time.get(problem, 0) > ALERT_COOLDOWN


def _clear_alert(problem: str) -> None:
    last_alert_time.pop(problem, None)


async def process_check_results(
    local: dict,
    node_results: dict[str, tuple[bool, str]],
) -> list[str]:
    """Анализ результатов и отправка алертов при необходимости."""
    now = time.time()
    alerts: list[str] = []

    # 1. systemd-сервисы
    for key, value in local.items():
        if key.startswith("unit_") and isinstance(value, bool):
            service = key[5:]
            problem = f"unit_{service}_down"
            if value:
                _clear_alert(problem)
            else:
                if _should_alert(problem, now):
                    alerts.append(f"❌ Сервис <code>{service}</code> не активен")
                    last_alert_time[problem] = now

    # 2. TCP-порты
    for key, value in local.items():
        if key.startswith("port_") and isinstance(value, bool):
            service = key[5:]
            problem = f"port_{service}_down"
            if value:
                _clear_alert(problem)
            else:
                if _should_alert(problem, now):
                    alerts.append(f"❌ Порт <code>{service}</code> не отвечает")
                    last_alert_time[problem] = now

    # 3. Диск
    disk = local.get("disk_free_percent")
    if disk is not None:
        problem = "disk_low"
        if disk < 10:
            if _should_alert(problem, now):
                alerts.append(f"⚠️ Свободное место на диске: {disk}%")
                last_alert_time[problem] = now
        else:
            _clear_alert(problem)

    # 4. RAM
    ram = local.get("ram_available_percent")
    if ram is not None:
        problem = "ram_low"
        if ram < 10:
            if _should_alert(problem, now):
                alerts.append(f"⚠️ Доступно RAM: {ram}%")
                last_alert_time[problem] = now
        else:
            _clear_alert(problem)

    # 5. RF-нода (API)
    rf_ok = local.get("rf_node_api")
    if isinstance(rf_ok, bool):
        problem = "rf_node_api_down"
        if rf_ok:
            _clear_alert(problem)
        else:
            if _should_alert(problem, now):
                alerts.append("❌ RF-нода не отвечает на /health")
                last_alert_time[problem] = now

    # 6. Удалённые узлы (HFM + RF через SSH)
    for host, (ok, output) in node_results.items():
        display_host = _strip_mon(host)
        kind = "RF" if display_host == RF_SSH_HOST else "HFM"
        problem = f"node_{display_host}_fail"
        if ok:
            _clear_alert(problem)
            continue
        if not _should_alert(problem, now):
            continue
        alert_line = ""
        for line in output.splitlines():
            if line.startswith("ALERT:"):
                alert_line = line.replace("ALERT:", "").strip()
                break
        short = alert_line or output[:200].replace("\n", " ").strip()
        alerts.append(f"🔴 {kind} <code>{display_host}</code>: {short}")
        last_alert_time[problem] = now

    for msg in alerts:
        await send_alert(msg)

    return alerts


# ---------- Основной цикл ----------

async def run_checks() -> dict:
    """Один цикл проверок."""
    local = await check_local_services()

    targets = load_check_targets()
    node_results = await run_all_checks(targets)

    alerts = await process_check_results(local, node_results)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "local": local,
        "hfm": {h: {"ok": ok, "output": out} for h, (ok, out) in node_results.items()},
        "alerts": alerts,
    }


async def monitor_daemon() -> None:
    """Бесконечный цикл мониторинга + HTTP /status."""
    click.echo("🛡️ Демон мониторинга запущен.")

    def _status_handler(_request):
        # Не отдаём детальные output — там могут быть секреты
        safe = {
            "timestamp": latest_results.get("timestamp"),
            "local": latest_results.get("local", {}),
            "hfm": {
                _strip_mon(h): {"ok": v.get("ok")}
                for h, v in (latest_results.get("hfm") or {}).items()
            },
            "alerts": latest_results.get("alerts", []),
        }
        return web.json_response(safe)

    app = web.Application()
    app.router.add_get("/status", _status_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", HTTP_STATUS_PORT)
    await site.start()
    click.echo(f"HTTP статус: http://127.0.0.1:{HTTP_STATUS_PORT}/status")

    try:
        while True:
            try:
                results = await run_checks()
                latest_results.update(results)
            except Exception as e:
                click.echo(f"❌ Check loop error: {e}")

            await asyncio.sleep(CHECK_INTERVAL)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


# ---------- CLI ----------

@click.group()
def monitor():
    """Мониторинг инфраструктуры Ulysses Shield."""
    pass


@monitor.command()
def check():
    """Однократная проверка всех систем."""
    async def _run():
        results = await run_checks()
        hfm = results.pop("hfm", {})

        summary: list[tuple[str, str, bool, int | None, int | None, str | None]] = []

        for host, data in hfm.items():
            display_host = _strip_mon(host)
            kind = "RF" if display_host == RF_SSH_HOST else "HFM"
            click.echo(f"\n📡 {kind} Health Check: {display_host} "
                       f"({'✅' if data['ok'] else '❌'})")
            click.echo(data["output"])

            passed, failed = _extract_counters(data["output"])
            block = _extract_summary_block(data["output"])
            summary.append((display_host, kind, data["ok"], passed, failed, block))

        # Сводка в конце
        click.echo("\n")
        click.echo("=" * 60)
        click.echo("  СВОДКА ПО НОДАМ")
        click.echo("=" * 60)
        for host, kind, ok, passed, failed, block in summary:
            status = "✅" if ok else "❌"
            click.echo(f"\n  {status} {kind} — {host}")
            if block:
                click.echo(block)
            elif passed is None or failed is None:
                click.echo("  (не удалось прочитать счётчики)")
            else:
                click.echo("=" * 60)
                click.echo(f"  Пройдено проверок: {passed}")
                click.echo(f"  Провалено проверок: {failed}")
                click.echo("=" * 60)
    asyncio.run(_run())


@monitor.command()
def run():
    """Запустить демон мониторинга."""
    asyncio.run(monitor_daemon())


@monitor.command()
def status():
    """Показать последние результаты мониторинга."""
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{HTTP_STATUS_PORT}/status", timeout=5
        ) as resp:
            data = json.loads(resp.read())
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        click.echo(f"Не удалось получить статус: {e}")
