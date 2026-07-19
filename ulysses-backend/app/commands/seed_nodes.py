# ulysses-backend/app/commands/seed_nodes.py

import os
import sys

# ============================================================
# ⚙️ АВТОНОМНЫЙ ДИНАМИЧЕСКИЙ PYTHON PATH (УБИРАЕМ ПРЕФИКСЫ)
# ============================================================
# Вычисляем абсолютные пути относительно расположения этого файла
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))  # app/commands/
APP_DIR = os.path.dirname(CURRENT_FILE_DIR)                   # app/
BACKEND_DIR = os.path.dirname(APP_DIR)                       # ulysses-backend/
ROOT_DIR = os.path.dirname(BACKEND_DIR)                       # Ulysses/

# Принудительно зашиваем путь поиска модулей прямо в ядро интерпретатора
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Теперь импорты из app.* гарантированно сработают без внешних переменных окружения!
import json
import logging
import asyncio
from sqlalchemy import text
from app.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_nodes")

TOPOLOGY_PATH = os.path.join(ROOT_DIR, "topology.json")

async def seed_infrastructure():
    """
    Парсит topology.json и каскадно импортирует структуру нод и гейтов в PostgreSQL.
    """
    logger.info(f"📂 Чтение файла топологии из: {TOPOLOGY_PATH}")
    if not os.path.exists(TOPOLOGY_PATH):
        logger.error(f"❌ Файл topology.json не найден по пути: {TOPOLOGY_PATH}")
        return

    with open(TOPOLOGY_PATH, "r", encoding="utf-8") as f:
        topology = json.load(f)

    async with AsyncSessionLocal() as session:
        try:
            for node_name, meta in topology.items():
                logger.info(f"🔄 Обработка сервера: {node_name} ({meta['aeza']})")

                # 1. Проверяем, существует ли уже такая нода в базе данных
                check_node_sql = text("SELECT id FROM nodes WHERE name = :name")
                res = await session.execute(check_node_sql, {"name": node_name})
                node_row = res.fetchone()

                if node_row:
                    node_id = node_row[0]
                    logger.info(f"  ➜ Нода уже существует в БД. ID: {node_id}")
                else:
                    # Вставляем новую запись в таблицу физических серверов nodes
                    insert_node_sql = text("""
                        INSERT INTO nodes (name, aeza_name, country, country_code, node_type)
                        VALUES (:name, :aeza, :country, :code, :type)
                        RETURNING id
                    """)
                    res_insert = await session.execute(insert_node_sql, {
                        "name": node_name,
                        "aeza": meta["aeza"],
                        "country": meta["country"],
                        "code": meta["code"],
                        "type": meta["type"]
                    })
                    node_id = res_insert.scalar_one()
                    logger.info(f"  ✅ Создана новая нода. Присвоен ID: {node_id}")

                # 2. Перебираем список IP-адресов, привязанных к этой ноде
                backup_index = meta.get("backup_ip_index", -1)

                for idx, ip in enumerate(meta.get("ips", [])):
                    # Определяем, является ли данный IP резервным (например, 3-й IP Финляндии)
                    is_backup = (idx == backup_index)

                    # Проверяем дубликаты IP-адресов во избежание нарушения уникального индекса
                    check_gw_sql = text("SELECT id FROM gateways WHERE node_id = :node_id AND ip_address = :ip")
                    gw_res = await session.execute(check_gw_sql, {"node_id": node_id, "ip": ip})

                    if gw_res.fetchone():
                        logger.info(f"    ⚠️ Gateway IP {ip} уже зарегистрирован. Пропускаем.")
                        continue

                    # Вставляем IP-адрес шлюза в таблицу gateways
                    insert_gw_sql = text("""
                        INSERT INTO gateways (node_id, ip_address, is_backup, status)
                        VALUES (:node_id, :ip, :is_backup, 'active')
                    """)
                    await session.execute(insert_gw_sql, {
                        "node_id": node_id,
                        "ip": ip,
                        "is_backup": is_backup
                    })
                    logger.info(f"    ➕ Добавлен шлюз IP: {ip} (Резервный: {is_backup})")

            await session.commit()
            logger.info("🎯 [СИДДЕР] Импорт всей сетевой инфраструктуры успешно завершен!")

        except Exception as e:
            await session.rollback()
            logger.error(f"❌ Критический сбой при выполнении сиддера: {e}")

if __name__ == "__main__":
    asyncio.run(seed_infrastructure())
