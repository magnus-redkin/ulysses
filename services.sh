#!/bin/bash

# Проверка наличия .env файла
if [ ! -f .env ]; then
    echo "❌ Ошибка: .env файл не найден!"
    exit 1
fi

# Загрузка переменных из .env
set -a
source .env
set +a

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SERVICES=("postgresql.service" "ulysses-backend.service" "ulysses-web.service" "ulysses-bot.service")

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        Ulysses Lab - Статус сервисов                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo "📅 $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

for SERVICE in "${SERVICES[@]}"; do
    # Получаем статус
    STATUS=$(systemctl is-active "$SERVICE" 2>/dev/null)

    case "$STATUS" in
        active)
            # Проверяем, что это running, а не exited
            if systemctl status "$SERVICE" --no-pager | grep -q "active (running)"; then
                echo -e "${GREEN}●${NC} $SERVICE ${GREEN}✅ Работает${NC}"
            else
                echo -e "${YELLOW}●${NC} $SERVICE ${YELLOW}⚠️ Запущен (но не в foreground)${NC}"
            fi
            ;;
        inactive|dead|failed)
            echo -e "${RED}●${NC} $SERVICE ${RED}❌ Остановлен${NC}"
            echo "   ➜ Попытка запуска..."
            sudo systemctl start "$SERVICE" 2>/dev/null
            sleep 1.5
            if systemctl is-active --quiet "$SERVICE"; then
                echo -e "   ${GREEN}✅ Успешно запущен${NC}"
            else
                echo -e "   ${RED}❌ Не удалось запустить${NC}"
                echo "   ➜ Логи: sudo journalctl -u $SERVICE -n 5 --no-pager"
            fi
            ;;
        *)
            echo -e "${RED}●${NC} $SERVICE ${RED}❌ Статус неизвестен ($STATUS)${NC}"
            ;;
    esac
done

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║        Детальная информация по процессам                  ║"
echo "╚════════════════════════════════════════════════════════════╝"

# Остановка вручную запущенных процессов (чтобы не мешали systemd)
echo "🔍 Проверка процессов, блокирующих порты бэкенда и фронтенда..."
MANUAL_PIDS=""

# Проверяем порты бэкенда (8000) и фронтенда (5173) через lsof
# Проверяем порты бэкенда (8000) и фронтенда (5173) через lsof
for pid in $(sudo lsof -t -i:8000,5173 2>/dev/null); do
    # Проверяем, принадлежит ли процесс к systemd slice
    if ! cat /proc/$pid/cgroup 2>/dev/null | grep -q "system.slice"; then
        if [ -n "$pid" ]; then
            MANUAL_PIDS="$MANUAL_PIDS $pid"
        fi
    fi
done

if [ -n "$MANUAL_PIDS" ]; then
    echo -e "   ${YELLOW}⚠️ Найдены сторонние процессы: $MANUAL_PIDS${NC}"
    echo "   ➜ Жесткая остановка..."
    for pid in $MANUAL_PIDS; do
        sudo kill -9 $pid 2>/dev/null && echo -e "   ${GREEN}✅ PID $pid остановлен${NC}"
    done
    sleep 1
else
    echo -e "   ${GREEN}✅ Конфликтующих ручных процессов нет${NC}"
fi
echo ""

for SERVICE in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$SERVICE"; then
        PID=$(systemctl show -p MainPID "$SERVICE" --value 2>/dev/null)
        if [ "$PID" != "0" ] && [ "$PID" != "" ]; then
            MEM=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{printf "%.1f MB", $1/1024}')
            CPU=$(ps -o %cpu= -p "$PID" 2>/dev/null | awk '{print $1"%"}')
            echo -e "${BLUE}📊${NC} $SERVICE"
            echo "   PID: $PID | Memory: $MEM | CPU: $CPU"
        else
            echo -e "${BLUE}📊${NC} $SERVICE (фоновый сервис)"
        fi
    fi
done

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║        Проверка доступности портов                        ║"
echo "╚════════════════════════════════════════════════════════════╝"

# Проверка портов
check_port() {
    local port=$1
    local name=$2
    if nc -z 127.0.0.1 "$port" 2>/dev/null; then
        echo -e "   ${GREEN}✅${NC} $name (порт $port) - доступен"
    else
        echo -e "   ${RED}❌${NC} $name (порт $port) - недоступен"
    fi
}

check_port 8000 "Backend API"
check_port 5173 "Web Admin"
check_port 5432 "PostgreSQL"

echo ""
echo "═══════════════════════════════════════════════════════════════"
