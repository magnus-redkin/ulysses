# app/services/subscription_aggregator.py
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
    """
    Человеческое имя тега: 'Reality', 'Reality xhttp', 'xhttp', 'gRPC'.
    Без названия протокола (VLESS/VMess и т.д.) — клиент покажет его сам
    из поля `type`, поэтому дублирование убрано.
    """
    t = ob.get("type", "unknown")
    parts = []

    # Reality — самый важный маркер
    tls = ob.get("tls") or {}
    if (tls.get("reality") or {}).get("enabled"):
        parts.append("Reality")

    # Транспорт
    transport = (ob.get("transport") or {}).get("type")
    if transport:
        # gRPC пишем заглавными — для читаемости
        if transport.lower() == "grpc":
            parts.append("gRPC")
        elif transport.lower() == "xhttp":
            parts.append("xhttp")
        else:
            parts.append(transport)

    # Если ни Reality, ни транспорта нет (чистый TCP) — используем протокол
    if not parts:
        parts.append(PROTOCOL_NAMES.get(t, t.upper()))

    return " ".join(parts)


def _make_leaf_tag(node: dict, ob: dict, index: int = 0) -> str:
    """Тег листа без стран и флагов: 'VLESS Reality 1', 'VLESS Reality 2'."""
    proto = _protocol_display_name(ob)
    return f"{proto} {index}" if index else proto

def _is_proxy_outbound(ob: dict) -> bool:
    ob_type = ob.get("type")
    return ob_type not in SERVICE_TYPES and ob_type not in UNSUPPORTED_TYPES


def _is_supported_in_mode(ob: dict, mode: str) -> bool:
    if not _is_proxy_outbound(ob):
        return False
    if mode == "compat":
        transport = (ob.get("transport") or {}).get("type")
        if transport in HIDDIFY_ONLY_TRANSPORTS:
            return False
    return True

async def fetch_singbox_from_node(node: dict, hiddify_uuid: str) -> Optional[dict]:
    """
    Забирает plain-text подписку с ноды и парсит её в sing-box outbound'ы.
    Используется /sub/, потому что /singbox/ не отдаёт xhttp-транспорты.
    """
    node_id = node.get("id", "unknown")
    domain = node.get("domain")
    client_path = node.get("proxy_path_client")

    if not domain or not client_path:
        logger.error(f"❌ Нода {node_id}: нет domain или proxy_path_client")
        return None

    url = f"https://{domain}/{client_path}/{hiddify_uuid}/sub/"
    logger.info(f"📡 URL Sub: {url}")

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                logger.error(f"❌ Нода {node_id} вернула HTTP {response.status_code}")
                return None

            from app.services.sub_parser import parse_sub_text
            outbounds = parse_sub_text(response.text)
            if not outbounds:
                logger.error(f"❌ Нода {node_id}: не распарсено ни одного outbound'а")
                return None

            logger.info(f"✅ Нода {node_id}: получено {len(outbounds)} outbounds")
            return {"outbounds": outbounds}

    except Exception as e:
        logger.error(f"❌ Ошибка соединения с {node_id}: {e}")
        return None

def _build_xray_standalone_outbound(node: dict, hiddify_uuid: str) -> Optional[dict]:
    """Строит sing-box outbound для standalone Xray Reality (TCP/gRPC)."""
    ip = node.get("ip")
    port = node.get("port")
    sni = node.get("sni")
    pbk = node.get("public_key")
    sid = node.get("short_id")

    if not all([ip, port, sni, pbk, sid]):
        logger.error(f"❌ Standalone-нода {node.get('id')}: не хватает полей")
        return None

    outbound = {
        "type": "vless",
        "tag": node.get("name", node.get("id", "Xray")),
        "server": ip,
        "server_port": port,
        "uuid": hiddify_uuid,
        "tls": {
            "enabled": True,
            "server_name": sni,
            "utls": {
                "enabled": True,
                "fingerprint": node.get("fingerprint", "firefox"),
            },
            "reality": {
                "enabled": True,
                "public_key": pbk,
                "short_id": sid,
            },
        },
    }

    if node.get("flow"):
        outbound["flow"] = node["flow"]

    if node.get("multiplex"):
        outbound["multiplex"] = node["multiplex"]

    # Транспорт — по умолчанию TCP (без поля transport)
    if node.get("transport") == "grpc":
        outbound["transport"] = {
            "type": "grpc",
            "service_name": node.get("service_name", "grpc"),
        }

    return outbound


def fetch_from_xray_standalone(node: dict, hiddify_uuid: str) -> Optional[dict]:
    """Возвращает config-словарь {outbounds: [...]} для standalone-ноды."""
    ob = _build_xray_standalone_outbound(node, hiddify_uuid)
    if not ob:
        return None
    return {"outbounds": [ob]}


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
            ob.get("transport", {}).get("service_name", ""),   # ← для gRPC
            (ob.get("tls") or {}).get("server_name", ""),      # ← SNI
        )
        if key not in seen:
            seen.add(key)
            deduped.append((node, ob))

    if not deduped:
        return {}

    # 2.5. Ограничение: по одному outbound'у каждого (transport, reality)
    #      на каждую ноду. Сокращает UI Hiddify с ~25 до ~6 профилей.
    #      grpc+TLS без Reality отбрасываем — он есть только для старых клиентов,
    #      а для остальных есть xhttp+TLS.
    limited = []
    seen_keys = set()
    for node, ob in deduped:
        node_id = node.get("id", "?")
        proto = ob.get("type", "?")
        transport_type = (ob.get("transport") or {}).get("type", "tcp")
        reality_enabled = bool((ob.get("tls") or {}).get("reality", {}).get("enabled"))

        # Пропускаем gRPC только для HFM-нод.
        # Standalone Xray использует Reality gRPC — он рабочий, оставляем.
        if node.get("type") != "xray-standalone":
            if proto == "vless" and transport_type == "grpc" and reality_enabled:
                continue
            if proto == "vless" and transport_type == "grpc" and not reality_enabled:
                continue


        key = (node_id, proto, transport_type, reality_enabled)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        limited.append((node, ob))

    deduped = limited


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
    logger.info(f"🚀 Агрегация для UUID {hiddify_uuid} (mode={mode})")
    hfm_nodes = node_manager.get_active_hfm_nodes()
    if not hfm_nodes:
        logger.error("❌ Нет доступных HFM нод")
        return None

    configs = []
    all_nodes = []

    # HFM-ноды
    for node in hfm_nodes:
        cfg = await fetch_singbox_from_node(node, hiddify_uuid)
        configs.append(cfg)
        all_nodes.append(node)

    # Standalone Xray-ноды
    standalone_nodes = node_manager.get_xray_standalone_nodes()
    for node in standalone_nodes:
        cfg = fetch_from_xray_standalone(node, hiddify_uuid)
        configs.append(cfg)
        all_nodes.append(node)
        if cfg:
            logger.info(f"✅ Standalone {node['id']}: добавлено {len(cfg['outbounds'])} outbound'ов")

    cfg = _build_config(configs, all_nodes, mode=mode)
    if not cfg:
        logger.error("❌ Не удалось собрать конфиг")
        return None

    logger.info(
        f"✅ Готово: mode={mode}, outbounds={len(cfg.get('outbounds', []))}"
    )
    return {"main": cfg}
