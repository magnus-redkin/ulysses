import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class NodeManager:
    def __init__(self, config_path: Optional[str] = None):
        base = Path(__file__).parent.parent / "private"
        self.config_path = Path(config_path) if config_path else base / "nodes.json"
        self.cache_path = base / "nodes_cache.json"
        self.nodes: Dict[str, Dict] = {}
        self._loaded = False
        self._load_cache()

    # ---------- Загрузка конфигурации ----------

    def _load_subdomains(self) -> List[str]:
        if not self.config_path.exists():
            logger.error(f"❌ nodes.json не найден: {self.config_path}")
            return []
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return data.get("subdomains", [])
        except Exception as e:
            logger.error(f"❌ Ошибка чтения nodes.json: {e}")
            return []

    def _load_cache(self):
        """Загружаем последний удачный кэш нод — чтобы Ulysses мог работать до refresh()."""
        if not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            self.nodes = data.get("nodes", {})
            self._loaded = bool(self.nodes)
            if self._loaded:
                logger.info(f"💾 Загружен кэш нод: {list(self.nodes.keys())}")
        except Exception as e:
            logger.error(f"❌ Ошибка чтения nodes_cache.json: {e}")

    def _save_cache(self):
        try:
            self.cache_path.write_text(
                json.dumps({"nodes": self.nodes}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"❌ Ошибка записи nodes_cache.json: {e}")

    # ---------- Обновление через SSH ----------

    async def _fetch_node_info(self, subdomain: str) -> Optional[Dict]:
        """Запускает hfm_info.sh по SSH и парсит JSON."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ssh", subdomain, "bash hfm_info.sh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20.0)
        except asyncio.TimeoutError:
            logger.error(f"❌ SSH timeout для ноды {subdomain}")
            return None
        except Exception as e:
            logger.error(f"❌ SSH ошибка для ноды {subdomain}: {e}")
            return None

        if proc.returncode != 0:
            logger.error(f"❌ hfm_info.sh на {subdomain} вернул код {proc.returncode}: {stderr.decode().strip()}")
            return None

        try:
            info = json.loads(stdout.decode())
        except Exception as e:
            logger.error(f"❌ Невалидный JSON от {subdomain}: {e}. Вывод: {stdout[:200]!r}")
            return None

        if info.get("error"):
            logger.error(f"❌ Нода {subdomain}: {info['error']}")
            return None

        info["id"] = subdomain
        info["active"] = True
        return info

    async def refresh(self):
        """Один раз при старте Ulysses: собирает параметры всех нод по SSH."""
        subdomains = self._load_subdomains()
        if not subdomains:
            logger.error("❌ Список поддоменов пуст — refresh не выполнен")
            return

        logger.info(f"🔄 Обновление параметров нод: {subdomains}")
        results = await asyncio.gather(*(self._fetch_node_info(s) for s in subdomains))

        new_nodes: Dict[str, Dict] = {}
        for sub, info in zip(subdomains, results):
            if info:
                new_nodes[sub] = info
            else:
                logger.warning(f"⚠️ Нода {sub} недоступна — оставляем из кэша, если был")
                if sub in self.nodes:
                    new_nodes[sub] = self.nodes[sub]

        if new_nodes:
            self.nodes = new_nodes
            self._loaded = True
            self._save_cache()
            logger.info(f"✅ Загружено {len(self.nodes)} нод: {list(self.nodes.keys())}")
        else:
            logger.error("❌ Ни одну ноду не удалось загрузить")

    # ---------- Доступ ----------

    def get_hfm_nodes(self) -> List[Dict]:
        return list(self.nodes.values())

    def get_active_hfm_nodes(self) -> List[Dict]:
        return [n for n in self.nodes.values() if n.get("active", True)]

    def get_node(self, node_id: str) -> Dict:
        return self.nodes.get(node_id, {})

    def get_node_by_code(self, code: str) -> Dict:
        code = code.upper()
        for n in self.nodes.values():
            if n.get("code", "").upper() == code:
                return n
        return {}

    def is_loaded(self) -> bool:
        return self._loaded


node_manager = NodeManager()
