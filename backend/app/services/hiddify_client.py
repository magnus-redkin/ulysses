# backend/app/services/hiddify_client.py

import logging
import asyncio
import httpx

from app.services.node_manager import node_manager

logger = logging.getLogger(__name__)


class HiddifyProvisioner:
    """
    Работает со всеми активными HFM-нодами через API v2.
    URL: https://<domain>/<proxy_path_admin>/api/v2/admin/user/...
    Auth: Hiddify-API-Key: <admin_uuid>
    """

    def __init__(self):
        self.headers_base = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ---------- Внутренние утилиты ----------

    def _nodes(self):
        return node_manager.get_active_hfm_nodes()

    def _admin_base(self, node: dict) -> str:
        return f"https://{node['domain']}/{node['proxy_path_admin']}/api/v2/admin"

    def _headers(self, node: dict) -> dict:
        h = dict(self.headers_base)
        h["Hiddify-API-Key"] = node.get("admin_uuid", "")
        return h

    # ---------- create ----------

    async def create_user(
        self,
        uuid: str,
        name: str,
        package_days: int = 3,
        usage_limit_gb: int = 500,
    ) -> bool:
        nodes = self._nodes()
        if not nodes:
            logger.error("❌ Нет HFM нод для create_user")
            return False

        payload = {
            "uuid": str(uuid),
            "name": str(name),
            "usage_limit_GB": usage_limit_gb,
            "package_days": package_days,
            "mode": "no_reset",
            "enable": True,
            "current_usage_GB": 0,
            "comment": "",
            "telegram_id": None,
        }

        async def _one(node):
            url = f"{self._admin_base(node)}/user/"
            try:
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
                    r = await client.post(url, headers=self._headers(node), json=payload)
                    if r.status_code in (200, 201):
                        logger.info(f"✅ [{node['id']}] create_user OK: {name}")
                        return True
                    if r.status_code == 400 and "exists" in r.text.lower():
                        logger.info(f"ℹ️ [{node['id']}] пользователь уже существует: {name}")
                        return True
                    logger.error(f"❌ [{node['id']}] create_user HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                logger.error(f"❌ [{node['id']}] create_user error: {e}")
            return False

        results = await asyncio.gather(*(_one(n) for n in nodes))
        return all(results)

    # ---------- delete ----------

    async def delete_user(self, uuid: str) -> dict:
        nodes = self._nodes()
        if not nodes:
            return {"success": False, "not_found": False}

        clean_uuid = str(uuid).strip().lower()

        async def _one(node):
            url = f"{self._admin_base(node)}/user/{clean_uuid}/"
            try:
                async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
                    r = await client.delete(url, headers=self._headers(node))
                    if r.status_code in (200, 204):
                        logger.info(f"✅ [{node['id']}] удалён {clean_uuid}")
                        return {"success": True, "not_found": False}
                    if r.status_code in (404,) or "not found" in r.text.lower():
                        logger.info(f"ℹ️ [{node['id']}] не найден {clean_uuid}")
                        return {"success": True, "not_found": True}
                    logger.error(f"❌ [{node['id']}] delete_user HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                logger.error(f"❌ [{node['id']}] delete_user error: {e}")
            return {"success": False, "not_found": False}

        results = await asyncio.gather(*(_one(n) for n in nodes))
        success = any(r["success"] for r in results)
        not_found = all(r["not_found"] for r in results)
        return {"success": success, "not_found": not_found}

    # ---------- enable / disable (PATCH) ----------

    async def enable_user(self, uuid_str: str) -> bool:
        return await self._patch_user(uuid_str, {"enable": True})

    async def disable_user(self, uuid_str: str) -> bool:
        return await self._patch_user(uuid_str, {"enable": False})

    async def _patch_user(self, uuid_str: str, payload: dict) -> bool:
        nodes = self._nodes()
        clean_uuid = str(uuid_str).strip().lower()

        async def _one(node):
            url = f"{self._admin_base(node)}/user/{clean_uuid}/"
            try:
                async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
                    r = await client.patch(url, headers=self._headers(node), json=payload)
                    if r.status_code in (200, 204):
                        return True
                    logger.error(f"❌ [{node['id']}] patch_user HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                logger.error(f"❌ [{node['id']}] patch_user error: {e}")
            return False

        results = await asyncio.gather(*(_one(n) for n in nodes))
        return all(results)

    # ---------- exists ----------

    async def check_user_exists(self, uuid_str: str) -> bool:
        nodes = self._nodes()
        clean_uuid = str(uuid_str).strip().lower()

        async def _one(node):
            url = f"{self._admin_base(node)}/user/{clean_uuid}/"
            try:
                async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
                    r = await client.get(url, headers=self._headers(node))
                    if r.status_code == 200:
                        return True
                    if r.status_code in (404, 500):
                        return False
            except Exception as e:
                logger.error(f"❌ [{node['id']}] check_user_exists error: {e}")
            return False

        results = await asyncio.gather(*(_one(n) for n in nodes))
        return any(results)

    # ---------- apply (no-op) ----------

    async def apply_config(self) -> bool:
        return True
