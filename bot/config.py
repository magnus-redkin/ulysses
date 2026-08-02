import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ulysses_bot")

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")
WEB_API_URL = os.getenv("WEB_API_URL", "http://127.0.0.1:5173").rstrip("/")
HOST_API_KEY = os.getenv("HOST_API_KEY")

# Флаг-переключатель для Экрана 2 (Выбор валюты)
# False — пропускает экран валют (сразу создает инвойс в RUB)
# True — включает экран выбора валюты (RUB/USD/EUR)
USE_CURRENCY_SCREEN = False

if not BOT_TOKEN:
    logger.critical("❌ CRITICAL ERROR: BOT_TOKEN not found in environment!")
    sys.exit(1)

if not HOST_API_KEY:
    logger.warning("⚠️ WARNING: HOST_API_KEY is not defined in your environment variables!")
