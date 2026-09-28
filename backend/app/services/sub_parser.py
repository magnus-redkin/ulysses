# backend/app/services/sub_parser.py
"""
Парсер plain-text подписки Hiddify Manager v13 (/sub/).

Принимает строки vless://, trojan://, ... и превращает их
в sing-box outbound'ы. Используется, когда /singbox/ не отдаёт
нужные транспорты (например, xhttp).
"""

import json
import logging
from urllib.parse import urlparse, parse_qs, unquote

logger = logging.getLogger(__name__)

# Транспорты, которые умеет sing-box в клиентском конфиге
SUPPORTED_TRANSPORTS = {"xhttp", "grpc", "ws", "httpupgrade", "quic", "http", "tcp", ""}


def _split_csv(val: str) -> list[str]:
    return [x.strip() for x in unquote(val).split(",") if x.strip()]


def _is_fake_host(host: str) -> bool:
    """HFM подкладывает заглушки типа 08.25--2026.09.27.time в первый конфиг."""
    if not host:
        return True
    if "--" in host or host.endswith(".time"):
        return True
    return False


def _make_tls(params: dict, host: str) -> dict | None:
    security = (params.get("security") or "none").lower()
    if security not in ("tls", "reality", "xtls"):
        return None

    tls: dict = {
        "enabled": True,
        "server_name": params.get("sni") or host,
        "utls": {
            "enabled": True,
            "fingerprint": params.get("fp", "chrome"),
        },
    }

    alpn = params.get("alpn")
    if alpn:
        tls["alpn"] = _split_csv(alpn)

    if security == "reality":
        pbk = params.get("pbk")
        sid = params.get("sid")
        if not pbk or not sid:
            logger.warning("Reality без pbk/sid, пропускаю tls")
            return None
        tls["reality"] = {
            "enabled": True,
            "public_key": pbk,
            "short_id": sid,
        }

    if security == "xtls":
        tls["reality"] = None  # xtls не поддерживаем — просто отбросим

    return tls


def _make_transport(params: dict) -> dict | None:
    ttype = (params.get("type") or "tcp").lower()
    if ttype not in SUPPORTED_TRANSPORTS:
        logger.warning(f"Транспорт '{ttype}' не поддержан, пропускаю")
        return None

    if ttype in ("", "tcp"):
        header = (params.get("headerType") or "").lower()
        if header and header != "none":
            return {
                "type": "http",
                "host": params.get("host", ""),
                "path": unquote(params.get("path", "/")),
            }
        return None

    if ttype == "xhttp":
        return {
            "type": "xhttp",
            "host": params.get("host", ""),
            "path": unquote(params.get("path", "/")),
            "mode": params.get("mode", "auto"),
        }

    if ttype == "grpc":
        return {
            "type": "grpc",
            "service_name": params.get("serviceName") or params.get("path", ""),
        }

    if ttype == "ws":
        return {
            "type": "ws",
            "path": unquote(params.get("path", "/")),
            "headers": {"Host": params.get("host", "")},
        }

    if ttype == "httpupgrade":
        return {
            "type": "httpupgrade",
            "host": params.get("host", ""),
            "path": unquote(params.get("path", "/")),
        }

    return {"type": ttype}


def _parse_vless(uri: str) -> dict | None:
    try:
        parsed = urlparse(uri)
        uuid = parsed.username
        host = parsed.hostname
        port = parsed.port
    except Exception as e:
        logger.warning(f"Не разобран vless: {e}")
        return None

    if not uuid or not host or not port:
        return None
    if _is_fake_host(host):
        return None

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    tag = unquote(parsed.fragment).strip() if parsed.fragment else f"VLESS {host}"

    ob: dict = {
        "type": "vless",
        "tag": tag,
        "server": host,
        "server_port": int(port),
        "uuid": uuid,
    }

    transport = _make_transport(params)
    if transport:
        ob["transport"] = transport

    tls = _make_tls(params, host)
    if tls:
        ob["tls"] = tls

    # flow только для tcp — для xhttp/grpc он ломает конфиг
    flow = params.get("flow")
    ttype = (params.get("type") or "tcp").lower()
    if flow and ttype in ("", "tcp"):
        ob["flow"] = flow

    # packet_encoding
    if (params.get("packetEncoding") or "").lower() == "xudp":
        ob["packet_encoding"] = "xudp"

    return ob


def _parse_trojan(uri: str) -> dict | None:
    try:
        parsed = urlparse(uri)
        password = unquote(parsed.username or "")
        host = parsed.hostname
        port = parsed.port
    except Exception:
        return None

    if not host or not port or _is_fake_host(host):
        return None

    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    tag = unquote(parsed.fragment).strip() if parsed.fragment else f"Trojan {host}"

    ob: dict = {
        "type": "trojan",
        "tag": tag,
        "server": host,
        "server_port": int(port),
        "password": password,
    }

    tls = _make_tls(params, host)
    if tls:
        ob["tls"] = tls

    transport = _make_transport(params)
    if transport:
        ob["transport"] = transport

    return ob


def parse_sub_line(line: str) -> dict | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("vless://"):
        return _parse_vless(line)
    if line.startswith("trojan://"):
        return _parse_trojan(line)
    # TODO: hysteria2, ss, tuic — добавить при необходимости
    return None


def parse_sub_text(text: str) -> list[dict]:
    result = []
    for line in text.splitlines():
        ob = parse_sub_line(line)
        if ob:
            result.append(ob)
    logger.info(f"📦 Распарсено {len(result)} outbound'ов из подписки")
    return result
