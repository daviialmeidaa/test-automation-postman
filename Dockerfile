# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo

# Sistema + cron + git (para o git pull) + utilitários
RUN apt-get update && apt-get install -y --no-install-recommends \
      tzdata curl ca-certificates cron bash git \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instala Postman CLI (linux64)
RUN curl -fsSL https://dl-cli.pstmn.io/install/linux64.sh | sh

# Diretório da app
WORKDIR /app

# Dependências Python (build cache-friendly)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Código (será sobrescrito pelo bind mount do compose, mas mantém a imagem funcional)
COPY main.py constants.py /app/

# Entrypoint (cron em foreground) + Crontab
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY crontab /etc/cron.d/automatest

# Normaliza EOL (protege contra CRLF) e registra a crontab
RUN chmod 0644 /etc/cron.d/automatest \
    && sed -i 's/\r$//' /entrypoint.sh \
    && sed -i 's/\r$//' /etc/cron.d/automatest \
    && crontab /etc/cron.d/automatest

# Diretórios úteis
RUN mkdir -p /app/collections /app/logs

ENTRYPOINT ["/entrypoint.sh"]
