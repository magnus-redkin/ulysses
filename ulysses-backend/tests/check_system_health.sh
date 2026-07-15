#!/usr/bin/env bash
# Ulysses Core - Системный мониторинг здоровья сервера и служб (Исправленная версия)

set -e

DISK_THRESHOLD=10  # Минимальный % свободного места на диске
RAM_THRESHOLD=5     # Минимальный % РЕАЛЬНО доступной оперативной памяти
BACKEND_URL="http://127.0.0.1:8000/api/billing/tariffs"

LOG_FILE="$(dirname "$0")/ulysses_health.log"
exec >> "$LOG_FILE" 2>&1

echo "=================================================="
echo "🕒 [$(date '+%Y-%m-%d %H:%M:%S')] НАЧАЛО ПРОВЕКИ СИСТЕМЫ"
echo "=================================================="

FAILED=0
ALERT_MSG=""

# 1. ПРОВЕРКА МЕСТА НА ДИСКЕ (Без изменений, работала верно)
AVAILABLE_DISK=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
FREE_DISK=$((100 - AVAILABLE_DISK))
if [ "$FREE_DISK" -lt "$DISK_THRESHOLD" ]; then
    ALERT_MSG+="🚨 КРИТИЧЕСКИ МАЛО МЕСТА НА ДИСКЕ! Свободно: ${FREE_DISK}%\n"
    FAILED=1
else
    echo "💾 Диск: ОК (Свободно ${FREE_DISK}%)"
fi

# 2. ПРОВЕРКА ОПЕРАТИВНОЙ ПАМЯТИ (Используем столбец 'available')
# Вытаскиваем значения total и available, считаем чистый процент
TOTAL_RAM=$(free | grep Mem | awk '{print $2}')
AVAIL_RAM=$(free | grep Mem | awk '{print $7}')
FREE_RAM_PCT=$((AVAIL_RAM * 100 / TOTAL_RAM))

if [ "$FREE_RAM_PCT" -lt "$RAM_THRESHOLD" ]; then
    ALERT_MSG+="🚨 КРИТИЧЕСКИ МАЛО ОПЕРАТИВНОЙ ПАМЯТИ! Доступно: ${FREE_RAM_PCT}%\n"
    FAILED=1
else
    echo "🧠 Память: ОК (Реально доступно ${FREE_RAM_PCT}%)"
fi

# 3. ПР ПРОВЕРКА СЛУЖБ ЧЕРЕЗ SYSTEMD И PGREP
if ! pg_isready -q; then
    ALERT_MSG+="🚨 СУБД POSTGRESQL НЕДОСТУПНА ИЛИ УПАЛА!\n"
    FAILED=1
else
    echo "🐘 База данных Postgres: ОК (Работает)"
fi

# Проверка Бэкенда (Ищем процесс ulysses-backend)
if ! pgrep -f "ulysses-backend" > /dev/null; then
    ALERT_MSG+="🚨 ПРОЦЕСС ULYSSES-BACKEND НЕ НАЙДЕН (УПАЛ)!\n"
    FAILED=1
else
    echo "⚙️ Бэкенд процесс: ОК"
fi

# Проверка Бота (Используем нативную проверку статуса systemd службы)
if ! systemctl is-active --quiet ulysses-bot.service; then
    ALERT_MSG+="🚨 СЛУЖБА ULYSSES-BOT.SERVICE НЕАКТИВНА ИЛИ УПАЛА!\n"
    FAILED=1
else
    echo "🤖 Бот служба (systemd): ОК"
fi

# 4. ПРОВЕРКА ЖИВОСТИ API (HTTP-тест эндпоинта тарифов)
# Запрашиваем код ответа, ограничивая тайм-аут в 5 секунд
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$BACKEND_URL" || echo "000")

# Нам подходит код 200 OK
if [ "$HTTP_STATUS" -ne 200 ]; then
    ALERT_MSG+="🚨 API БЭКЕНДА НЕ ОТВЕЧАЕТ ИЛИ ВЫДАЕТ ОШИБКУ! HTTP Код: ${HTTP_STATUS}\n"
    FAILED=1
else
    echo "📡 API Бэкенда: ОК (HTTP Статус 200)"
fi

# ИТОГ ПРОВЕРКИ
if [ "$FAILED" -eq 1 ]; then
    echo -e "\n🔴 ОБНАРУЖЕНЫ КРИТИЧЕСКИЕ ПРОБЛЕМЫ:\n$ALERT_MSG"
else
    echo -e "\n🟢 Все системы работают в штатном режиме."
fi

echo "=================================================="
echo "🕒 [$(date '+%Y-%m-%d %H:%M:%S')] ПРОВЕРКА ЗАВЕРШЕНА"
echo "=================================================="
