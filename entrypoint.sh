#!/bin/sh
set -e

# Garante log
touch /var/log/cron.log
chmod 666 /var/log/cron.log

# Mostra contexto útil no startup
echo "[entrypoint] Timezone: $TZ"
echo "[entrypoint] PATH: $PATH"
which postman || true
postman -v || true
python --version || true

# Sobe o cron em foreground (mantém container vivo)
cron -f
