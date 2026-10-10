# syntax=docker/dockerfile:1

# ==========================================================
# ÉTAPE 1 : BUILDER
# ==========================================================
FROM python:3.12-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gettext \
    libpq-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    chromium \
    chromium-driver \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Copie le code pour compiler les .po → .mo DANS le builder
COPY . .
RUN /opt/venv/bin/python manage.py compilemessages

# ==========================================================
# ÉTAPE 2 : RUNTIME
# ==========================================================
FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    BROWSER_PATH=/usr/bin/chromium

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Copie TOUT le code (avec les .mo déjà compilés dans le builder)
COPY --from=builder /app /app

RUN python manage.py collectstatic --noinput

RUN adduser --disabled-password --gecos "" django \
    && chown -R django:django /app
USER django

# ⚠️ NE PAS figer le port : Render fournit $PORT dynamiquement
# ⚠️ --workers 1 pour rester dans les 512 MB du plan gratuit
# ⚠️ --timeout 120 pour laisser le temps au cold start
# ⚠️ sh -c pour interpréter ${PORT:-8000}
CMD ["sh", "-c", "gunicorn ProjectInsight.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile -"]