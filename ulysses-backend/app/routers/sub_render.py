# ulysses-backend/app/routers/sub_render.py

import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from datetime import datetime, timezone
from app.database import AsyncSessionLocal

logger = logging.getLogger("ulysses.sub_render")
router = APIRouter(prefix="/subscription", tags=["subscription"])

def generate_singbox_json(hiddify_uuid: str) -> dict:
    """Генерация эталонного JSON-конфига Sing-box для Reality + xHTTP (3 гейта)."""

    # Имена нод, которые будут отображаться в селекторе Hiddify
    node_1_tag = "🚀 Ulysses Premium #1 [Round-Robin]"
    node_2_tag = "🚀 Ulysses Premium #2 [Round-Robin]"
    node_3_tag = "🛡️ Ulysses Backup [Резерв]"

    all_proxies = [node_1_tag, node_2_tag, node_3_tag]

    config = {
        "outbounds": [
            # 1. Основной селектор выбора прокси в интерфейсе
            {
                "type": "selector",
                "tag": "proxy",
                "outbounds": ["Best Latency"] + all_proxies,
                "interrupt_exist_connections": True
            },
            # 2. Авто-выбор ноды с наименьшей задержкой (Пинг-тест)
            {
                "type": "urltest",
                "tag": "Best Latency",
                "outbounds": all_proxies,
                "interval": "3m",
                "tolerance": 50
            },
            # Служебные системные аутбаунды ядра
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
            {"type": "dns", "tag": "dns-out"},

            # 3. ГЕЙТ №1 (Round-Robin)
            {
                "type": "vless",
                "tag": node_1_tag,
                "server": "62.60.249.53",
                "server_port": 443,
                "uuid": hiddify_uuid,
                "tls": {
                    "enabled": True,
                    "server_name": "dl.google.com",
                    "utls": {"enabled": True, "fingerprint": "chrome"},
                    "reality": {
                        "enabled": True,
                        "public_key": "HoNJg3CMNQy2oWUTk7gOIOjwiFDc9VkvsenMdFrweTE",
                        "short_id": "0a3f9c1d7b2e4a0f"
                    }
                },
                # 🌟 СПЕЦИФИКАЦИЯ xHTTP ТРАНСПОРТА:
                "transport": {
                    "type": "xhttp",
                    "path": "/TZe1DA5Xmdguu8htyuGgnt",
                    "host": "dl.google.com"
                }
            },
            # 4. ГЕЙТ №2 (Round-Robin)
            {
                "type": "vless",
                "tag": node_2_tag,
                "server": "138.124.25.80",
                "server_port": 443,
                "uuid": hiddify_uuid,
                "tls": {
                    "enabled": True,
                    "server_name": "dl.google.com",
                    "utls": {"enabled": True, "fingerprint": "chrome"},
                    "reality": {
                        "enabled": True,
                        "public_key": "HoNJg3CMNQy2oWUTk7gOIOjwiFDc9VkvsenMdFrweTE",
                        "short_id": "0a3f9c1d7b2e4a0f"
                    }
                },
                "transport": {
                    "type": "xhttp",
                    "path": "/TZe1DA5Xmdguu8htyuGgnt",
                    "host": "dl.google.com"
                }
            },
            # 5. ГЕЙТ №3 (Резервный шлюз)
            {
                "type": "vless",
                "tag": node_3_tag,
                "server": "45.151.102.125",
                "server_port": 443,
                "uuid": hiddify_uuid,
                "tls": {
                    "enabled": True,
                    "server_name": "dl.google.com",
                    "utls": {"enabled": True, "fingerprint": "chrome"},
                    "reality": {
                        "enabled": True,
                        "public_key": "HoNJg3CMNQy2oWUTk7gOIOjwiFDc9VkvsenMdFrweTE",
                        "short_id": "0a3f9c1d7b2e4a0f"
                    }
                },
                "transport": {
                    "type": "xhttp",
                    "path": "/TZe1DA5Xmdguu8htyuGgnt",
                    "host": "dl.google.com"
                }
            }
        ]
    }
    return config


@router.get("/{hiddify_uuid}/")
async def render_user_subscription(hiddify_uuid: str):
    """Раздача нативного JSON-конфига Sing-box."""
    async with AsyncSessionLocal() as session:
        sql_user = """
            SELECT u.id, s.expires_at
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE u.hiddify_uuid = :uuid AND s.status = 'active'
            LIMIT 1
        """
        res = await session.execute(text(sql_user), {"uuid": hiddify_uuid})
        row = res.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Active subscription not found")

        user_id, db_expires_at = row

        # Генерируем структуру словаря
        json_config = generate_singbox_json(hiddify_uuid)

        # Вычисляем заголовок лимитов для полосы прогресса в Hiddify
        total_bytes = 536870912000
        expire_timestamp = int(db_expires_at.replace(tzinfo=timezone.utc).timestamp()) if db_expires_at else 0
        user_info_header = f"upload=0; download=0; total={total_bytes}; expire={expire_timestamp}"

        # Отдаем чистый форматированный JSON-текст
        return Response(
            content=json.dumps(json_config, indent=2, ensure_ascii=False),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=config_{hiddify_uuid[:8]}.json",
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Subscription-Userinfo": user_info_header,
                "Profile-Title": "Ulysses Premium JSON"
            }
        )
