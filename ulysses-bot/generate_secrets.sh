# ulysses-bot/generate_secrets.sh
#!/bin/bash
echo "Генерация секретных ключей для .env:"
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "ENCRYPTION_KEY=$(openssl rand -hex 32)"
