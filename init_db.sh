#!/usr/bin/env bash
# Ulysses Lab VPN - Инициализация чистой БД (Только Ядро VPN и Биллинг)

set -e

ENV_PATH="./.env"
if [ ! -f "$ENV_PATH" ]; then ENV_PATH="../.env"; fi

if [ -f "$ENV_PATH" ]; then
    echo "⚙️ Загрузка конфигурации из $ENV_PATH..."
    DB_NAME=$(grep -E "^DB_NAME=" "$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'")
    DB_USER=$(grep -E "^DB_USER=" "$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'")
    DB_PASS=$(grep -E "^DB_PASS=" "$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'")
    DB_HOST=$(grep -E "^DB_HOST=" "$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'")
    DB_PORT=$(grep -E "^DB_PORT=" "$ENV_PATH" | cut -d= -f2- | tr -d '"' | tr -d "'")
fi

DB_NAME=${DB_NAME:-"ulysses_db"}
DB_USER=${DB_USER:-"ulysses_admin"}
DB_PASS=${DB_PASS:-"fdre4332"}
DB_HOST=${DB_HOST:-"localhost"}
DB_PORT=${DB_PORT:-"5432"}

echo "=== Инициализация Ulysses VPN Core DB ==="

export PGPASSWORD="$DB_PASS"

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Полная очистка структуры
DROP TABLE IF EXISTS payment_attempts CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- 1. ПОЛЬЗОВАТЕЛИ (Паспорт + КЛЮЧ VPN)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    tg_user_id BIGINT,                        -- Наш главный источник истины
    tg_username VARCHAR(100),
    email VARCHAR(255) UNIQUE,                -- NULL разрешен для покупок из бота
    hiddify_uuid UUID UNIQUE,                 -- Один ключ на всю жизнь
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. СРОКИ ПОДПИСОК (Только даты и тарифы)
CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tariff_slug VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'provisioning', -- provisioning, active, expired, cancelled
    node_id VARCHAR(50) DEFAULT 'main',
    starts_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    provisioning_attempts INTEGER DEFAULT 0,
    last_provisioning_at TIMESTAMP WITH TIME ZONE,
    provisioning_error TEXT,
    activated_at TIMESTAMP WITH TIME ZONE
);

-- 3. ПЛАТЕЖНЫЕ ИНВОЙСЫ
CREATE TABLE payment_attempts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    tariff_slug VARCHAR(50) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'RUB',
    status VARCHAR(20) DEFAULT 'pending', -- pending, success, failed
    provider_tx_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ТРИГГЕРЫ ОБНОВЛЕНИЯ ВРЕМЕНИ
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS \$\$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
\$\$ LANGUAGE plpgsql;

CREATE TRIGGER tg_user_upd BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER tg_sub_upd BEFORE UPDATE ON subscriptions FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ИНДЕКСЫ ДЛЯ ТАКУЩИХ СВЯЗЕЙ
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tg_user_id ON users(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_users_uuid ON users(hiddify_uuid);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payment_attempts(status);

-- ТЕСТОВЫЙ ЮЗЕР
INSERT INTO users (email, created_at)
VALUES ('test@ulysses.best', CURRENT_TIMESTAMP)
ON CONFLICT (email) DO NOTHING;

-- ТЕСТОВЫЙ ЮЗЕР
INSERT INTO users (email, created_at)
VALUES ('test@ulysses.best', CURRENT_TIMESTAMP)
ON CONFLICT (email) DO NOTHING;

-- BRAIN: Мозг VPN (щиты, телеметрия, инциденты, DNS)
CREATE SCHEMA IF NOT EXISTS brain;

CREATE TABLE IF NOT EXISTS brain.shields (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(45) NOT NULL,
    country VARCHAR(10) NOT NULL,
    datacenter VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    last_health_check TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS brain.telemetry (
    id SERIAL PRIMARY KEY,
    shield_id INTEGER NOT NULL REFERENCES brain.shields(id) ON DELETE CASCADE,
    active_clients INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    avg_latency_ms NUMERIC(10, 2),
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS brain.incidents (
    id SERIAL PRIMARY KEY,
    shield_id INTEGER NOT NULL REFERENCES brain.shields(id) ON DELETE CASCADE,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    action_taken VARCHAR(50),
    notification_sent BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS brain.dns_state (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    ip VARCHAR(45) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_shields_status ON brain.shields(status);
CREATE INDEX IF NOT EXISTS idx_telemetry_shield_time ON brain.telemetry(shield_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_incidents_shield ON brain.incidents(shield_id);

DO \$\$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'tg_shield_upd'
    ) THEN
        CREATE TRIGGER tg_shield_upd
            BEFORE UPDATE ON brain.shields
            FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END \$\$;

EOF

echo "=== Инициализация успешно завершена!  ==="
