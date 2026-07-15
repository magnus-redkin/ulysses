# app/monitoring.py
"""
Простой мониторинг для Ulysses.
Healthcheck + метрики в JSON без Prometheus.
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import psutil
import os

class UlyssesMetrics:
    """Простые метрики приложения"""

    def __init__(self):
        self.start_time = time.time()
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "webhooks_processed": 0,
            "emails_sent": 0,
            "provisioning_success": 0,
            "provisioning_failed": 0,
        }

    def increment(self, metric: str):
        """Увеличить счетчик метрики"""
        if metric in self.metrics:
            self.metrics[metric] += 1

    def get_uptime(self) -> str:
        """Время работы сервиса"""
        uptime_seconds = int(time.time() - self.start_time)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60
        return f"{hours}h {minutes}m {seconds}s"

    def get_system_stats(self) -> Dict[str, Any]:
        """Системные метрики"""
        process = psutil.Process(os.getpid())
        mem = process.memory_info()

        return {
            "cpu_percent": process.cpu_percent(interval=0.1),
            "memory_mb": round(mem.rss / 1024 / 1024, 2),
            "open_files": len(process.open_files()),
            "threads": process.num_threads(),
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Все метрики в одном словаре"""
        return {
            "service": "Ulysses VPN Billing",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime": self.get_uptime(),
            "system": self.get_system_stats(),
            "application": self.metrics,
            "environment": os.getenv("ENVIRONMENT", "production"),
        }

# Глобальный экземпляр метрик
metrics = UlyssesMetrics()
