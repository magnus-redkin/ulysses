import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

class NodeManager:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "private" / "nodes.json"
        self.config_path = Path(config_path)
        self.nodes = self._load_config()

    def _load_config(self) -> Dict:
        """Загружает конфигурацию из JSON файла."""
        if not self.config_path.exists():
            logger.error(f"❌ Файл конфигурации нод не найден: {self.config_path}")
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"✅ Загружено {len(data)} узлов из {self.config_path}")
            return data
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки nodes.json: {e}")
            return {}

    def get_hfm_nodes(self) -> List[Dict]:
        """Возвращает список всех HFM нод (type == 'hfm' или 'heart')."""
        result = []
        for key, node in self.nodes.items():
            if node.get("type") in ["hfm", "heart"]:
                node_copy = node.copy()
                node_copy["id"] = key
                result.append(node_copy)
        return result

    def get_node(self, node_id: str) -> Dict:
        """Возвращает ноду по её идентификатору."""
        return self.nodes.get(node_id, {})

    def get_node_by_country(self, code: str) -> Dict:
        """Возвращает ноду по ISO-коду страны (AT, FI и т.д.)."""
        for node in self.nodes.values():
            if node.get("code") == code.upper():
                return node
        return {}

# Глобальный экземпляр для использования в других модулях
node_manager = NodeManager()
