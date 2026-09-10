import json
import logging
from typing import Dict, List, Optional
import httpx

from app.services.node_manager import node_manager

logger = logging.getLogger(__name__)

SERVICE_TYPES = {"selector", "urltest", "direct", "block", "dns", "bypass"}
UNSUPPORTED_TYPES = {"dnstt", "socks", "naive", "ssh"}

# Транспорты, попадающие в Simple
SIMPLE_TRANSPORTS = {"", "grpc", "http"}


def _flag(code: str) -> str:
    code = (code or "").upper()
    if len(code) != 2 or not code.isalpha():
        return "🏳️"
    return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))


def _is_proxy_outbound(ob: dict) -> bool:
    ob_type = ob.get("type")
    return ob_type not in SERVICE_TYPES and ob_type not in UNSUPPORTED_TYPES


def _is_simple_outbound(ob: dict) -> bool:
    if ob.get("type") != "vless":
        return False
    reality = ob.get("tls", {}).get("reality", {})
    if not reality.get("enabled"):
        return False
    transport_type = ob.get("transport", {}).get("type", "")
    return transport_type in SIMPLE_TRANSPORTS


def _make_human_tag(node: dict, outbound: dict, index: int = 0) -> str:
    country = (node.get("code") or "??").upper()
    flag = _flag(country)

    proto = outbound.get("type", "unknown").upper()
    tls = outbound.get("tls", {})
    if tls.get("reality", {}).get("enabled"):
        transport = "Reality"
        ttype = outbound.get("transport", {}).get("type")
        if ttype:
            transport += f" {ttype}"
    elif outbound.get("transport"):
        transport = outbound["transport"].get("type", "")
    else:
        transport = ""

    base = f"{flag} {country} — {proto}"
    if transport:
        base += f" {transport}"

    if index > 0:
        base += f" ({index + 1})"
    return base

async def fetch_singbox_from_node(node: dict, hiddify_uuid: str) -> Optional[dict]:
    node_id = node.get("id", "unknown")
    domain = node.get("domain")
    client_path = node.get("proxy_path_client")

    if not domain or not client_path:
        logger.error(f"❌ Нода {node_id}: нет domain или proxy_path_client")
        return None

    url = f"https://{domain}/{client_path}/{hiddify_uuid}/singbox/?asn=unknown"
    logger.info(f"📡 URL Sing-box: {url}")

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code == 200:
                try:
                    data = response.json()
                    logger.info(f"✅ Нода {node_id}: получено {len(data.get('outbounds', []))} outbounds")
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"❌ Нода {node_id}: невалидный JSON: {e}. Начало: {response.text[:200]!r}")
                    return None
            logger.error(f"❌ Нода {node_id} вернула HTTP {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"❌ Ошибка соединения с {node_id}: {e}")
        return None


def _build_config(
    configs: List[dict],
    nodes: List[dict],
    mode: str,
) -> Dict:
    """Собирает итоговый sing-box конфиг для режима simple / advanced."""
    is_filter = _is_simple_outbound if mode == "simple" else _is_proxy_outbound

    combined = []
    for node, config in zip(nodes, configs):
        if not config:
            continue
        for ob in config.get("outbounds", []):
            if is_filter(ob):
                new_ob = ob.copy()
                new_ob.pop("tunnel-per-resolver", None)
                combined.append((node, new_ob))

    # Дедупликация
    seen = set()
    deduped = []
    for node, ob in combined:
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

    # Уникальные теги
    tag_counts = {}
    final_outbounds = []
    for node, ob in deduped:
        new_tag = _make_human_tag(node, ob, 0)
        if new_tag in tag_counts:
            tag_counts[new_tag] += 1
            new_tag = f"{new_tag} ({tag_counts[new_tag]})"
        else:
            tag_counts[new_tag] = 0
        ob["tag"] = new_tag
        final_outbounds.append(ob)

    if not final_outbounds:
        return {}

    proxy_tags = [ob["tag"] for ob in final_outbounds]

    selector = {
        "type": "selector",
        "tag": "proxy",
        "outbounds": ["Auto", *proxy_tags],
        "interrupt_exist_connections": True,
    }
    urltest = {
        "type": "urltest",
        "tag": "Auto",
        "outbounds": proxy_tags,
        "url": "https://www.gstatic.com/generate_204",
        "interval": "10m",
        "tolerance": 200,
    }

    outbounds = [
        selector,
        urltest,
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"},
        {"type": "dns", "tag": "dns-out"},
        *final_outbounds,
    ]

    route = {
        "auto_detect_interface": True,
        "override_android_vpn": True,
        "final": "proxy",
        "rule_set": [],
        "rules": [],
    }
    dns = {
        "servers": [
            {"address": "tcp://1.1.1.1", "address_resolver": "dns-local", "strategy": "prefer_ipv4", "tag": "dns-remote", "detour": "proxy"},
            {"address": "8.8.8.8", "detour": "direct", "tag": "dns-local"},
            {"address": "rcode://success", "tag": "dns-block"},
        ],
        "rules": [],
        "final": "dns-local",
        "reverse_mapping": True,
        "strategy": "prefer_ipv4",
        "independent_cache": True,
    }

    return {"outbounds": outbounds, "route": route, "dns": dns}


async def aggregate_subscriptions(hiddify_uuid: str) -> Dict:
    """
    Возвращает оба режима сразу:
        {
            "simple":   {...},
            "advanced": {...}
        }
    """
    logger.info(f"🚀 Агрегация для UUID {hiddify_uuid}")
    nodes = node_manager.get_active_hfm_nodes()
    if not nodes:
        logger.error("❌ Нет доступных HFM нод")
        return {}

    configs = []
    for node in nodes:
        cfg = await fetch_singbox_from_node(node, hiddify_uuid)
        configs.append(cfg)

    simple = _build_config(configs, nodes, "simple")
    advanced = _build_config(configs, nodes, "advanced")

    if not simple and not advanced:
        logger.error("❌ Не удалось собрать ни один конфиг")
        return {}

    logger.info(f"✅ Готово: simple={len(simple.get('outbounds', []))}, advanced={len(advanced.get('outbounds', []))}")
    return {"simple": simple, "advanced": advanced}
