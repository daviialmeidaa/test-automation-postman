# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo

RUN apt-get update && apt-get install -y --no-install-recommends \
      tzdata curl ca-certificates cron bash \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instala Postman CLI (linux64)
RUN curl -fsSL https://dl-cli.pstmn.io/install/linux64.sh | sh

# Diretório da app
WORKDIR /app

# Requisitos primeiro (cache build)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Código da app (você pode montar via volume também)
COPY main.py constants.py /app/

# Entrypoint que sobe o cron em foreground
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Arquivo de crontab será injetado via build
COPY crontab /etc/cron.d/automatest
RUN chmod 0644 /etc/cron.d/automatest && crontab /etc/cron.d/automatest

# Diretórios que vamos montar
RUN mkdir -p /app/collections /app/logs

ENTRYPOINT ["/entrypoint.sh"]
