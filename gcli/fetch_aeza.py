# gcli/fetch_aeza.py

"""
Скрипт опроса Aeza API и синхронизации с gryphons.vps.
Запуск: uv run gcli/fetch_aeza.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import httpx
from app.config import settings
from app.database import AsyncSessionLocal
from sqlalchemy import text

AEZA_API_URL = "https://my.aeza.net/api/v2/services"


async def fetch_services() -> list[dict]:
    """Получить список всех VPS."""
    headers = {
        "X-API-Key": settings.AEZA_API_KEY,
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(AEZA_API_URL, headers=headers)
        if resp.status_code != 200:
            print(f"❌ Aeza API error: {resp.status_code}")
            return []
        data = resp.json()
        return data.get("data", data)  # некоторые API оборачивают в {"data": [...]}


async def fetch_service_detail(service_id: str) -> dict:
    """Получить детали одного VPS (включая IP)."""
    headers = {
        "X-API-Key": settings.AEZA_API_KEY,
        "Accept": "application/json"
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{AEZA_API_URL}/{service_id}", headers=headers)
        if resp.status_code != 200:
            print(f"  ⚠️ Не удалось получить детали {service_id}: {resp.status_code}")
            return {}
        return resp.json()


async def sync_to_db(services: list[dict]):
    """Записать/обновить данные VPS в gryphons.vps."""
    async with AsyncSessionLocal() as session:
        for svc in services:
            # Базовые поля из списка
            provider_id = str(svc.get("id", ""))
            name = svc.get("name", "")
            status = svc.get("status", "unknown")
            country = svc.get("location", {}).get("country", "??")

            # Детали получаем отдельным запросом
            detail = await fetch_service_detail(provider_id)

            internal_ip = ""
            active_ip = ""
            reserve_ip = None
            ip_addresses = []

            # IP могут быть в разных полях — смотрим detail
            if detail:
                # Возможные варианты: ip_addresses, ips, network.interfaces
                params = detail.get("computedParameters", detail.get("parameters", {}))
                ip_addresses = params.get("ip_addresses", params.get("ips", []))

                if not ip_addresses:
                    # Пробуем найти IP в других местах
                    network = detail.get("network", {})
                    interfaces = network.get("interfaces", [])
                    for iface in interfaces:
                        ip_addresses.append(iface.get("ip", iface.get("address", "")))

            if ip_addresses:
                active_ip = ip_addresses[0]
                if len(ip_addresses) > 1:
                    reserve_ip = ip_addresses[1]

            await session.execute(
                text("""
                    INSERT INTO gryphons.vps
                        (host, provider, provider_id, country, internal_ip, active_ip, reserve_ip, is_gate, role, status)
                    VALUES
                        (:host, 'aeza', :pid, :country, :int_ip, :active_ip, :reserve_ip, TRUE, 'gate', :status)
                    ON CONFLICT (provider_id) DO UPDATE SET
                        host = EXCLUDED.host,
                        country = EXCLUDED.country,
                        internal_ip = EXCLUDED.internal_ip,
                        active_ip = EXCLUDED.active_ip,
                        reserve_ip = EXCLUDED.reserve_ip,
                        status = EXCLUDED.status,
                        updated_at = NOW()
                """),
                {
                    "host": name,
                    "pid": provider_id,
                    "country": country,
                    "int_ip": internal_ip,
                    "active_ip": active_ip,
                    "reserve_ip": reserve_ip,
                    "status": status,
                }
            )
            print(f"  ✅ {name} ({country}): {active_ip}" + (f" | reserve: {reserve_ip}" if reserve_ip else ""))

        await session.commit()
    print(f"📊 Синхронизировано VPS: {len(services)}")


async def main():
    print("🔄 Запрос к Aeza API...")
    services = await fetch_services()
    if not services:
        print("⚠️ Нет данных от Aeza")
        return

    print(f"📡 Получено серверов: {len(services)}")
    await sync_to_db(services)


if __name__ == "__main__":
    asyncio.run(main())
