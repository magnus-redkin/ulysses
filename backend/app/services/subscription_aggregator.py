import base64
import logging
from typing import List
import httpx

from app.services.node_manager import node_manager

logger = logging.getLogger(__name__)

async def fetch_subscription_from_node(node: dict, hiddify_uuid: str) -> str:
    """
    Получает подписку пользователя с конкретной ноды.
    Возвращает декодированную строку с URI протоколов.
    """
    node_id = node.get("id", "unknown")
    domain = node.get("domain") or node.get("ip")
    admin_path = node.get("admin_path")

    logger.info(f"🔍 Начинаем получение подписки с ноды {node_id} (domain={domain}, admin_path={admin_path})")

    if not domain or not admin_path:
        logger.error(f"❌ Нода {node_id}: не хватает domain или admin_path")
        return ""

    sub_path = node.get("sub_path") # or node.get("admin_path")
    url = f"https://{domain}/{sub_path}/{hiddify_uuid}/"
    logger.info(f"📡 URL для запроса подписки: {url}")

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
            response = await client.get(url)
            logger.info(f"📥 Ответ от ноды {node_id}: HTTP {response.status_code}")
            if response.status_code == 200:
                raw = response.text.strip()
                logger.info(f"📦 Длина сырого ответа: {len(raw)} символов")
                try:
                    decoded = base64.b64decode(raw).decode("utf-8")
                    logger.info(f"✅ Успешно декодировано {len(decoded)} символов с ноды {node_id}")
                    return decoded
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось декодировать base64 с ноды {node_id}: {e}")
                    return raw
            else:
                logger.error(f"❌ Нода {node_id} вернула HTTP {response.status_code}")
                logger.error(f"Тело ответа: {response.text[:200]}")
                return ""
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к ноде {node_id}: {e}")
        return ""

async def aggregate_subscriptions(hiddify_uuid: str) -> str:
    """
    Собирает подписки со всех HFM нод и возвращает объединённую строку.
    """
    logger.info(f"🚀 Запуск агрегации для UUID {hiddify_uuid}")
    nodes = node_manager.get_hfm_nodes()
    logger.info(f"📋 Найдено HFM нод: {len(nodes)}")
    if not nodes:
        logger.error("❌ Нет доступных HFM нод для агрегации")
        return ""

    all_links = []
    for node in nodes:
        logger.info(f"🔄 Обрабатываем ноду {node.get('id')}")
        links_str = await fetch_subscription_from_node(node, hiddify_uuid)
        if links_str:
            lines = [line.strip() for line in links_str.splitlines() if line.strip()]
            logger.info(f"✅ С ноды {node.get('id')} получено {len(lines)} ссылок")
            all_links.extend(lines)
        else:
            logger.warning(f"⚠️ С ноды {node.get('id')} ничего не получено")

    if not all_links:
        logger.error(f"❌ Не удалось получить ни одной подписки для UUID {hiddify_uuid}")
        return ""

    combined = "\n".join(all_links)
    logger.info(f"🎉 Итого агрегировано {len(all_links)} ссылок с {len(nodes)} нод")
    return combined

def encode_subscription(links_str: str) -> str:
    if not links_str:
        return ""
    encoded = base64.b64encode(links_str.encode("utf-8")).decode("utf-8")
    logger.info(f"🔐 Закодировано в base64, длина {len(encoded)}")
    return encoded
