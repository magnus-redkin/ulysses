import json
import logging
from typing import Dict, List, Optional
import httpx

from app.config import settings
from app.services.node_manager import node_manager

logger = logging.getLogger(__name__)

SERVICE_TYPES = {"selector", "urltest", "direct", "block", "dns", "bypass"}
UNSUPPORTED_TYPES = {"dnstt", "socks", "naive", "ssh"}

# Транспорт, который понимает ТОЛЬКО Hiddify (форк sing-box)
HIDDIFY_ONLY_TRANSPORTS = {"xhttp"}


PROTOCOL_NAMES = {
    "vless": "VLESS",
    "vmess": "VMess",
    "trojan": "Trojan",
    "hysteria2": "Hysteria2",
    "hysteria": "Hysteria",
    "tuic": "TUIC",
    "shadowsocks": "Shadowsocks",
    "wireguard": "WireGuard",
}


def _protocol_signature(ob: dict) -> str:
    """Сигнатура для группировки одинаковых протоколов."""
    parts = [str(ob.get("type", "?"))]
    tls = ob.get("tls") or {}
    if (tls.get("reality") or {}).get("enabled"):
        parts.append("reality")
    transport = (ob.get("transport") or {}).get("type")
    if transport:
        parts.append(transport)
    flow = ob.get("flow")
    if flow:
        parts.append(flow)
    return "|".join(parts)


def _protocol_display_name(ob: dict) -> str:
    """Человеческое имя протокола: 'VLESS Reality', 'Hysteria2', 'VLESS xhttp'."""
    t = ob.get("type", "unknown")
    parts = [PROTOCOL_NAMES.get(t, t.upper())]
    tls = ob.get("tls") or {}
    if (tls.get("reality") or {}).get("enabled"):
        parts.append("Reality")
    transport = (ob.get("transport") or {}).get("type")
    if transport:
        parts.append(transport)
    return " ".join(parts)

def _make_leaf_tag(node: dict, ob: dict, index: int = 0) -> str:
    """Тег листа без стран и флагов: 'VLESS Reality 1', 'VLESS Reality 2'."""
    proto = _protocol_display_name(ob)
    return f"{proto} {index}" if index else proto

def _is_proxy_outbound(ob: dict) -> bool:
    ob_type = ob.get("type")
    return ob_type not in SERVICE_TYPES and ob_type not in UNSUPPORTED_TYPES


def _is_supported_in_mode(ob: dict, mode: str) -> bool:
    """Проверяет, допустим ли outbound в данном режиме."""
    if not _is_proxy_outbound(ob):
        return False
    if mode == "compat":
        transport = (ob.get("transport") or {}).get("type")
        if transport in HIDDIFY_ONLY_TRANSPORTS:
            return False
    return True


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
    mode: str = "full",
) -> Dict:
    """
    Плоская структура:
        proxy (selector) → [Auto, <все листья>]
        Auto (urltest)   → [<все листья>]

    Теги листьев: 'VLESS Reality', 'VLESS Reality 2', 'Hysteria2', 'Hysteria2 2' и т.д.
    Уникальность обеспечивается нумерацией внутри группы одного протокола.
    Флаги стран Hiddify рисует сам по GeoIP сервера.
    """
    # 1. Сбор outbound'ов с нод
    combined = []
    for node, config in zip(nodes, configs):
        if not config:
            continue
        for ob in config.get("outbounds", []):
            if _is_supported_in_mode(ob, mode):
                new_ob = ob.copy()
                new_ob.pop("tunnel-per-resolver", None)
                combined.append((node, new_ob))

    # 2. Дедупликация
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

    if not deduped:
        return {}

    # 3. Группируем по сигнатуре протокола, чтобы нумеровать внутри группы
    groups: dict = {}
    for node, ob in deduped:
        sig = _protocol_signature(ob)
        groups.setdefault(sig, []).append((node, ob))

    leaves = []
    leaf_tags = []
    used = set()

    for sig, group in groups.items():
        for i, (node, ob) in enumerate(group):
            # Первый без номера, остальные — 2, 3, ...
            tag = _make_leaf_tag(node, ob, index=i + 1 if i > 0 else 0)
            base = tag
            n = 1
            while tag in used:
                n += 1
                tag = f"{base} ({n})"
            used.add(tag)
            ob["tag"] = tag
            leaves.append(ob)
            leaf_tags.append(tag)

    # 4. Top-level selector + urltest
    selector = {
        "type": "selector",
        "tag": "proxy",
        "outbounds": ["Auto", *leaf_tags],
        "interrupt_exist_connections": True,
    }
    auto_urltest = {
        "type": "urltest",
        "tag": "Auto",
        "outbounds": leaf_tags,
        "url": "https://www.gstatic.com/generate_204",
        "interval": "10m",
        "tolerance": 200,
    }

    outbounds = [
        selector,
        auto_urltest,
        {"type": "direct", "tag": "direct"},
        *leaves,
    ]

    # 5. Route и DNS
    route = {
        "auto_detect_interface": True,
        "final": "proxy",
        "default_domain_resolver": {"server": "google"},
        "rules": [
            {"action": "sniff"},
            {"protocol": "dns", "action": "hijack-dns"},
        ],
    }

    dns = {
        "servers": [
            {"type": "tls", "tag": "cf-tls", "server": "1.1.1.1", "detour": "proxy"},
            {"type": "udp", "tag": "google", "server": "8.8.8.8"},
        ],
        "final": "google",
    }

    return {"outbounds": outbounds, "route": route, "dns": dns}



async def aggregate_subscriptions(hiddify_uuid: str, mode: str = "full") -> Optional[Dict]:
    """
    Возвращает готовый конфиг для подписки.

    mode="full"    — все протоколы, включая xhttp. Hiddify.
    mode="compat"  — без xhttp. Happ, Nekoray, v2rayNG, sing-box CLI.
    """
    logger.info(f"🚀 Агрегация для UUID {hiddify_uuid} (mode={mode})")
    nodes = node_manager.get_active_hfm_nodes()
    if not nodes:
        logger.error("❌ Нет доступных HFM нод")
        return None

    configs = []
    for node in nodes:
        cfg = await fetch_singbox_from_node(node, hiddify_uuid)
        configs.append(cfg)

    cfg = _build_config(configs, nodes, mode=mode)
    if not cfg:
        logger.error("❌ Не удалось собрать конфиг")
        return None

    logger.info(
        f"✅ Готово: mode={mode}, outbounds={len(cfg.get('outbounds', []))}"
    )
    return {"main": cfg}
