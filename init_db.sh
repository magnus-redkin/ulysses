#!/usr/bin/env bash
# Ulysses Lab VPN - Инициализация чистой БД (Ядро VPN, Биллинг, Gryphons)

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
DB_HOST=${DB_HOST:-"localhost"}
DB_PORT=${DB_PORT:-"5432"}

if [ -z "$DB_PASS" ]; then
    echo "❌ DB_PASS не задан в .env файле"
    exit 1
fi

echo "=== Инициализация Ulysses VPN Core DB ==="

export PGPASSWORD="$DB_PASS"

psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" <<EOF

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Полная очистка структуры
DROP TABLE IF EXISTS payment_attempts CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ============================================================
-- ULYSSES: Пользователи, подписки, платежи
-- ============================================================

-- 1. ПОЛЬЗОВАТЕЛИ (Паспорт + КЛЮЧ VPN)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    tg_user_id BIGINT,
    tg_username VARCHAR(100),
    tg_lang VARCHAR(10) DEFAULT 'ru',
    email VARCHAR(255) UNIQUE,
    hiddify_uuid UUID UNIQUE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. ПОДПИСКИ
CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tariff_slug VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'provisioning',
    node_id VARCHAR(50) DEFAULT 'main',
    starts_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    provisioning_attempts INTEGER DEFAULT 0,
    last_provisioning_at TIMESTAMPTZ,
    provisioning_error TEXT,
    notified_3d BOOLEAN DEFAULT FALSE,
    notified_1d BOOLEAN DEFAULT FALSE,
    notified_expired BOOLEAN DEFAULT FALSE,
    activated_at TIMESTAMPTZ
);

-- 3. ПЛАТЕЖНЫЕ ИНВОЙСЫ
CREATE TABLE payment_attempts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    tariff_slug VARCHAR(50) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'RUB',
    status VARCHAR(20) DEFAULT 'pending',
    provider_tx_id VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
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

-- ИНДЕКСЫ ULYSSES
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_tg_user_id ON users(tg_user_id);
CREATE INDEX IF NOT EXISTS idx_users_uuid ON users(hiddify_uuid);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payment_attempts(status);

-- ============================================================
-- GRYPHONS: Все VPS (щиты, Ulysses, HFM)
-- ============================================================

DROP SCHEMA IF EXISTS gryphons CASCADE;
CREATE SCHEMA gryphons;

-- ВСЕ VPS в одной таблице
CREATE TABLE gryphons.vps (
    id SERIAL PRIMARY KEY,
    host TEXT NOT NULL,                    -- имя/адрес VPS
    provider TEXT NOT NULL,                -- 'aeza' | 'manual'
    provider_id TEXT,                      -- ID сервера в API провайдера
    country TEXT NOT NULL,                 -- 'FI' | 'SE' | 'RU'
    internal_ip TEXT NOT NULL,             -- 10.x.x.x
    active_ip TEXT NOT NULL,               -- текущий рабочий внешний IP
    reserve_ip TEXT,                       -- резервный внешний IP (если есть)
    is_gate BOOLEAN DEFAULT FALSE,         -- true = гейт Gryphons, false = Ulysses/HFM/инфра
    role TEXT,                             -- 'gate' | 'ulysses' | 'hfm' | 'monitoring'
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- История переключений IP (только для гейтов, но ссылка на vps.id)
CREATE TABLE gryphons.switches (
    id SERIAL PRIMARY KEY,
    vps_id INT REFERENCES gryphons.vps(id),
    old_ip TEXT NOT NULL,
    new_ip TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER tg_vps_upd
    BEFORE UPDATE ON gryphons.vps
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE INDEX IF NOT EXISTS idx_vps_status ON gryphons.vps(status);
CREATE INDEX IF NOT EXISTS idx_vps_is_gate ON gryphons.vps(is_gate);
CREATE INDEX IF NOT EXISTS idx_vps_country ON gryphons.vps(country);
CREATE INDEX IF NOT EXISTS idx_switches_vps ON gryphons.switches(vps_id);

EOF

echo "=== Инициализация успешно завершена! ==="
