# ulysses-backend/app/services/aeza_sync.py

import os
import sys

# ============================================================
# ⚙️ АВТОНОМНЫЙ ДИНАМИЧЕСКИЙ PYTHON PATH
# ============================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(CURRENT_DIR)
BACKEND_DIR = os.path.dirname(APP_DIR)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import logging
import asyncio
from sqlalchemy import text
import httpx
from app.database import AsyncSessionLocal
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aeza_sync")


class AezaInfrastructureSync:

    def __init__(self):
        aeza_num = str(getattr(settings, "AEZA_NUMBER", "7515")).strip()
        raw_key = str(getattr(settings, "AEZA_API_KEY", "")).strip()

        if "_" in raw_key:
            self.api_key = raw_key
        else:
            self.api_key = f"{aeza_num}_{raw_key}"

        # Верифицированный базовый эндпоинт услуг v1
        self.target_url = "https: / / my.aeza.net / api / services"

        self.headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "curl/7.81.0"
        }

    async def sync_network_gateways(self):
        """Запрашивает список услуг и доп. IP через API v2, синхронизируя базу PostgreSQL."""
        clean_url = self.target_url.replace(" ", "")
        logger.info("📡 [AEZA SYNC] Запуск глубокой синхронизации сетевой инфраструктуры Ulysses...")

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                params = {"page": 1, "count": 100}
                response = await client.get(clean_url, headers=self.headers, params=params)

                if response.status_code != 200:
                    logger.error(f"❌ API Aéza вернул ошибку: HTTP {response.status_code}")
                    return

                aeza_data = response.json()
                vps_items = aeza_data.get("data", {}).get("items", [])
                logger.info(f"✅ Успешно получено базовых серверов от Aéza: {len(vps_items)}")
        except Exception as e:
            logger.error(f"❌ Сетевой сбой при обращении к хостингу Aéza: {e}")
            return

        async with AsyncSessionLocal() as session:
            try:
                # Загружаем из нашей БД карту известных нод
                nodes_res = await session.execute(text("SELECT id, aeza_name FROM nodes"))
                local_nodes = {row: row for row in nodes_res.fetchall()}

                async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                    for vps in vps_items:
                        aeza_name = vps.get("name")
                        if aeza_name not in local_nodes:
                            continue

                        node_id = local_nodes[aeza_name]
                        vps_internal_id = vps.get("id") # Числовой ID услуги (например, 1889795)
                        aeza_status = vps.get("status", "active").lower()

                        # Собираем массив IP-адресов для этой ноды
                        ips = []
                        main_ip = vps.get("ip")
                        if main_ip:
                            ips.append(main_ip)

                        # 🟢 СВЕРХ-УМНЫЙ ШАГ ПОДДЕРЖКИ: Запрашиваем дополнительные IP через API v2 эндпоинт
                        # https://aeza.net{id}/networks/ipv4
                        v2_network_url = f"https: / / my.aeza.net / api / v2 / services / {vps_internal_id} / networks / ipv4"
                        v2_clean_url = v2_network_url.replace(" ", "")

                        try:
                            v2_res = await client.get(v2_clean_url, headers=self.headers)
                            if v2_res.status_code == 200:
                                v2_data = v2_res.json()
                                # Вытаскиваем массив дополнительных IP-адресов
                                additional_items = v2_data.get("data", {}).get("items", [])
                                for item in additional_items:
                                    add_ip = item.get("address")
                                    if add_ip and add_ip not in ips:
                                        ips.append(add_ip)
                        except Exception as v2_err:
                            logger.warning(f"  ⚠️ Не удалось загрузить доп. IP для {aeza_name} через v2: {v2_err}")

                        logger.info(f"⚙️ Нода '{aeza_name}' (ID: {node_id}). Итоговый пул IP: {ips}")
                        system_status = "active" if aeza_status in ("active", "running") else "offline"

                        for ip in ips:
                            check_sql = text("SELECT id FROM gateways WHERE node_id = :nid AND ip_address = :ip")
                            res = await session.execute(check_sql, {"nid": node_id, "ip": ip})
                            gw_row = res.fetchone()

                            if gw_row:
                                update_sql = text("""
                                    UPDATE gateways
                                    SET status = :status, updated_at = CURRENT_TIMESTAMP
                                    WHERE node_id = :nid AND ip_address = :ip AND status != 'blocked'
                                """)
                                await session.execute(update_sql, {"status": system_status, "nid": node_id, "ip": ip})
                            else:
                                insert_sql = text("""
                                    INSERT INTO gateways (node_id, ip_address, status, is_backup)
                                    VALUES (:nid, :ip, :status, FALSE)
                                """)
                                await session.execute(insert_sql, {"nid": node_id, "ip": ip, "status": system_status})
                                logger.info(f"    ➕ Автоматически обнаружен и добавлен дополнительный IP: {ip}")

                await session.commit()
                logger.info("🎯 [AEZA SYNC v2] База данных гейтов полностью укомплектована всеми доп. IP!")

            except Exception as db_err:
                await session.rollback()
                logger.error(f"❌ Сбой СУБД при выполнении коммита: {db_err}")

if __name__ == "__main__":
    sync = AezaInfrastructureSync()
    asyncio.run(sync.sync_network_gateways())

    # curl -k -A "Hiddify Next" -s "http://127.0.0.1:8000/X6CbExbUw2/sub/d3364106-e743-445c-afbc-9939dfe9eac7"
