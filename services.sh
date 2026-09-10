#!/bin/bash
# Ulysses Service Manager
# Использование:
#   ./services.sh          - production mode (systemd)
#   ./services.sh --dev    - development mode
#   ./services.sh stop     - полная остановка всех сервисов
#   ./services.sh status   - показать статус systemd-сервисов и портов

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

stop_all() {
    echo -e "${YELLOW}⏹ Остановка всех сервисов...${NC}"
    sudo systemctl stop ulysses-backend ulysses-bot ulysses-web ulysses-monitor 2>/dev/null || true
    sudo fuser -k 8000/tcp 5173/tcp 3000/tcp 2>/dev/null || true
    echo -e "${GREEN}✅ Все сервисы остановлены${NC}"
}

start_prod() {
#     echo -e "${BLUE}📦 Сборка web (pnpm build)...${NC}"
    cd "$PROJECT_ROOT/web"
#     pnpm build

    echo -e "${BLUE}🚀 Запуск production сервисов...${NC}"
    sudo systemctl start postgresql
    sudo systemctl start ulysses-backend
    sudo systemctl start ulysses-web
    sudo systemctl start ulysses-bot
    sudo systemctl start ulysses-monitor
    sudo systemctl start ulysses-maintenance.timer

    echo -e "${GREEN}✅ Production сервисы запущены${NC}"
    sleep 2
    show_status
}

start_dev() {
    cd "$PROJECT_ROOT"

    # Backend
    if sudo lsof -i :8000 >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️ Backend уже запущен${NC}"
    else
        echo -e "${BLUE}🚀 Запуск backend (uvicorn --reload)...${NC}"
        (cd backend && PYTHONPATH=.. ../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > /tmp/ulysses-backend.log 2>&1 &)
        sleep 2
        if sudo lsof -i :8000 >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Backend запущен${NC}"
        else
            echo -e "${RED}❌ Backend не запустился! Лог: /tmp/ulysses-backend.log${NC}"
            tail -n 20 /tmp/ulysses-backend.log
            exit 1
        fi
    fi

    # Web
    if sudo lsof -i :5173 >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️ Web уже запущен${NC}"
    else
        echo -e "${BLUE}🚀 Запуск web (vite dev)...${NC}"
        (cd web && pnpm run dev --host 0.0.0.0 > /tmp/ulysses-web.log 2>&1 &)
        sleep 2
        if sudo lsof -i :5173 >/dev/null 2>&1; then
            echo -e "${GREEN}✅ Web запущен${NC}"
        else
            echo -e "${RED}❌ Web не запустился! Лог: /tmp/ulysses-web.log${NC}"
            tail -n 20 /tmp/ulysses-web.log
            exit 1
        fi
    fi

    # Bot
    if pgrep -f "bot/main.py" >/dev/null; then
        echo -e "${YELLOW}⚠️ Bot уже запущен${NC}"
    else
        echo -e "${BLUE}🚀 Запуск bot...${NC}"
        (PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/bot" "$PROJECT_ROOT/.venv/bin/python" "$PROJECT_ROOT/bot/main.py" > /tmp/ulysses-bot.log 2>&1 &)
        sleep 2
        if pgrep -f "bot/main.py" >/dev/null; then
            echo -e "${GREEN}✅ Bot запущен${NC}"
        else
            echo -e "${RED}❌ Бот не запустился! Лог: /tmp/ulysses-bot.log${NC}"
            tail -n 20 /tmp/ulysses-bot.log
            exit 1
        fi
    fi
}

show_status() {
    SERVICES=("postgresql.service" "ulysses-backend.service" "ulysses-web.service" "ulysses-bot.service" "ulysses-monitor.service")
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║        Ulysses Lab - Статус сервисов                      ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo "📅 $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    for SERVICE in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
            echo -e "${GREEN}●${NC} $SERVICE ${GREEN}✅ Работает${NC}"
        else
            echo -e "${RED}●${NC} $SERVICE ${RED}❌ Остановлен${NC}"
        fi
    done

    echo ""
    check_port 8000 "Backend API"
    check_port 3000 "Web (prod)"
    check_port 5432 "PostgreSQL"
}

check_port() {
    local port=$1
    local name=$2
    if nc -z 127.0.0.1 "$port" 2>/dev/null; then
        echo -e "   ${GREEN}✅${NC} $name (порт $port) - доступен"
    else
        echo -e "   ${RED}❌${NC} $name (порт $port) - недоступен"
    fi
}

# ====================== MAIN ======================
case "${1}" in
    --dev)
        stop_all
        start_dev
        ;;
    stop)
        stop_all
        ;;
    status)
        show_status
        ;;
    "" | prod | --prod)
        stop_all
        start_prod
        ;;
    *)
        echo "Использование: $0 [--prod|--dev|stop|status]"
        exit 1
        ;;
esac
