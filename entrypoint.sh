#!/usr/bin/env bash
set -e

# Garante permissões básicas
touch /var/log/cron.log
chmod 666 /var/log/cron.log

echo "[entrypoint] Timezone: $TZ"
echo "[entrypoint] Iniciando cron..."
cron -f
