#!/usr/bin/env python
"""
Ulysses Fingerprint Server — entry point.

Запуск (из ~/Ulysses/backend):
    PYTHONPATH=.. ../.venv/bin/python run_fingerprint.py
"""

import sys
import logging

from app.config import settings
from app.fingerprint.server import FingerprintServer


def main() -> int:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        stream=sys.stdout,
    )
    log = logging.getLogger('fingerprint')
    log.info(f"Starting on {settings.FINGERPRINT_HOST}:{settings.FINGERPRINT_PORT}")
    log.info(f"Cert: {settings.FINGERPRINT_CERT}")

    server = FingerprintServer(
        host=settings.FINGERPRINT_HOST,
        port=settings.FINGERPRINT_PORT,
        certfile=settings.FINGERPRINT_CERT,
        keyfile=settings.FINGERPRINT_KEY,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutdown by SIGINT")
    return 0


if __name__ == '__main__':
    sys.exit(main())
