import json
import logging
from typing import List, Dict
import httpx

from app.services.node_manager import node_manager

logger = logging.getLogger(__name__)

# Служебные типы outbound, которые не являются прокси
SERVICE_TYPES = {"selector", "urltest", "direct", "block", "dns", "bypass"}

UNSUPPORTED_TYPES = {"dnstt", "socks", "naive", "ssh"} # , "mieru"

def _is_proxy_outbound(outbound: dict) -> bool:
    ob_type = outbound.get("type")
    return ob_type not in SERVICE_TYPES and ob_type not in UNSUPPORTED_TYPES

def _deduplicate_outbounds(outbounds: List[Dict]) -> List[Dict]:
    """Удаляет дубликаты по ключевым полям, оставляя первый вариант."""
    seen = set()
    unique = []
    for ob in outbounds:
        key = (
            ob.get("type"),
            ob.get("server"),
            ob.get("server_port"),
            ob.get("uuid", ob.get("password", "")),
            ob.get("transport", {}).get("type", ""),
            ob.get("transport", {}).get("path", ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(ob)
    return unique

def _make_human_tag(node: dict, outbound: dict, index: int = 0) -> str:
    """
    Генерирует понятное имя тега для outbound-а.
    Пример: 🇫🇮 FI — VLESS Reality
    """
    country_code = node.get("code", "??").upper()
    flag = node.get("flag", "") or {
        "AT": "🇦🇹",
        "FI": "🇫🇮",
        "RU": "🇷🇺"
    }.get(country_code, "🏳️")

    proto = outbound.get("type", "unknown").upper()
    transport = ""
    tls = outbound.get("tls", {})
    if tls.get("reality", {}).get("enabled"):
        transport = "Reality"
    elif outbound.get("transport"):
        transport = outbound["transport"].get("type", "")
    else:
        transport = ""

    base = f"{flag} {country_code} — {proto}"
    if transport:
        base += f" {transport}"

    if index > 0:
        base += f" ({index+1})"
    return base

async def fetch_singbox_from_node(node: dict, hiddify_uuid: str) -> dict | None:
    """
    Получает Sing-box JSON от конкретной ноды.
    """
    node_id = node.get("id", "unknown")
    domain = node.get("domain") or node.get("ip")
    sub_path = node.get("admin_path")

    if not domain or not sub_path:
        logger.error(f"❌ Нода {node_id}: не хватает domain или sub_path")
        return None

    url = f"https://{domain}/{sub_path}/{hiddify_uuid}/singbox/"
    logger.info(f"📡 URL для Sing-box: {url}")

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.info(f"✅ Получен Sing-box JSON с ноды {node_id} ({len(data.get('outbounds', []))} outbounds)")
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Нода {node_id}: невалидный JSON: {e}")
                    return None
            else:
                logger.error(f"❌ Нода {node_id} вернула HTTP {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к ноде {node_id}: {e}")
        return None

def merge_singbox_configs(configs: List[Dict], nodes: List[Dict]) -> Dict:
    """
    Объединяет Sing-box конфиги с разных нод в один.
    """
    combined_outbounds = []

    # Собираем все прокси outbounds
    for node, config in zip(nodes, configs):
        if not config:
            continue
        for ob in config.get("outbounds", []):
            if _is_proxy_outbound(ob):
                new_ob = ob.copy()
                if "tunnel-per-resolver" in new_ob:
                    del new_ob["tunnel-per-resolver"]
                # Временно оставляем оригинальный тег, потом заменим
                combined_outbounds.append((node, new_ob))

    # Дедупликация
    seen = set()
    deduped = []
    for node, ob in combined_outbounds:
        key = (
            ob.get("type"),
            ob.get("server"),
            ob.get("server_port"),
            ob.get("uuid", ob.get("password", "")),
            ob.get("transport", {}).get("type", ""),
            ob.get("transport", {}).get("path", ""),
        )
        if key not in seen:
            seen.add(key)
            deduped.append((node, ob))

    # Переименовываем теги с учётом возможных повторов имён
    tag_counts = {}
    final_outbounds = []
    for node, ob in deduped:
        original_tag = ob.get("tag", "unknown")
        # Сначала создаём базовое имя
        new_tag = _make_human_tag(node, ob, 0)
        if new_tag in tag_counts:
            tag_counts[new_tag] += 1
            new_tag = f"{new_tag} ({tag_counts[new_tag]})"
        else:
            tag_counts[new_tag] = 0

        ob["tag"] = new_tag
        logger.info(f"🔄 Outbound: {original_tag} → {new_tag}")
        final_outbounds.append(ob)

    if not final_outbounds:
        logger.error("❌ Нет прокси outbounds для объединения")
        return {}

    proxy_tags = [ob["tag"] for ob in final_outbounds]

    selector = {
        "type": "selector",
        "tag": "proxy",
        "outbounds": ["Auto", *proxy_tags],
        "interrupt_exist_connections": True
    }
    urltest = {
        "type": "urltest",
        "tag": "Auto",
        "outbounds": proxy_tags,
        "url": "https://www.gstatic.com/generate_204",
        "interval": "10m",
        "tolerance": 200
    }

    final_outbounds_list = [
        selector,
        urltest,
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"},
        {"type": "dns", "tag": "dns-out"},
        *final_outbounds
    ]

    route = {
        "auto_detect_interface": True,
        "override_android_vpn": True,
        "final": "proxy",
        "rule_set": [],
        "rules": []
    }
    dns = {
        "servers": [
            {"address": "tcp://1.1.1.1", "address_resolver": "dns-local", "strategy": "prefer_ipv4", "tag": "dns-remote", "detour": "proxy"},
            {"address": "8.8.8.8", "detour": "direct", "tag": "dns-local"},
            {"address": "rcode://success", "tag": "dns-block"}
        ],
        "rules": [],
        "final": "dns-local",
        "reverse_mapping": True,
        "strategy": "prefer_ipv4",
        "independent_cache": True
    }

    return {
        "outbounds": final_outbounds_list,
        "route": route,
        "dns": dns
    }

async def aggregate_subscriptions(hiddify_uuid: str) -> Dict:
    """
    Главная функция агрегации: собирает Sing-box JSON со всех нод и объединяет.
    """
    logger.info(f"🚀 Запуск агрегации Sing-box для UUID {hiddify_uuid}")
    nodes = node_manager.get_active_hfm_nodes()
    if not nodes:
        logger.error("❌ Нет доступных HFM нод")
        return {}

    configs = []
    for node in nodes:
        logger.info(f"🔄 Обрабатываем ноду {node.get('id')}")
        cfg = await fetch_singbox_from_node(node, hiddify_uuid)
        if cfg:
            configs.append(cfg)
        else:
            configs.append(None)

    merged = merge_singbox_configs(configs, nodes)
    if not merged:
        logger.error("❌ Не удалось объединить Sing-box конфиги")
        return {}

    logger.info(f"✅ Агрегация завершена. Всего outbounds: {len(merged['outbounds'])}")
    return merged
