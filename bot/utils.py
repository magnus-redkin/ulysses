import httpx
from bot.config import logger

async def api_call(method: str, url: str, api_key: str = None, **kwargs) -> dict | None:
    """Centralized, resilient wrapper for backend API communication."""
    try:
        headers = kwargs.pop("headers", {})
        if api_key:
            headers["X-API-Key"] = api_key

        async with httpx.AsyncClient(timeout=15.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers, **kwargs)
            else:
                resp = await client.post(url, json=kwargs.get("json"), headers=headers)

            if resp.status_code == 200:
                logger.info(f"📡 [API RAW RESPONSE] from {url} ➔ {resp.text[:200]}")
                try:
                    return resp.json()
                except Exception as parse_err:
                    logger.error(f"💥 Backend returned invalid JSON string: {parse_err}")
                    return {"state": "error", "message": resp.text, "keyboard": "back"}

            logger.error(f"API {method} {url} → HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Network transport fault during API call: {e}")
    return None
