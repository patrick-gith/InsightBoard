# syntax=docker/dockerfile:1

# ==========================================================
# ÉTAPE 1 : BUILDER (dépendances et outils de compilation)
# ==========================================================
FROM python:3.12-slim-bookworm AS builder

# Dépendances système pour WeasyPrint, Kaleido (Chromium), Psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
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
     gettext \                 # ← AJOUT
    && rm -rf /var/lib/apt/lists/*

# Empêche Python d'écrire des .pyc et force les logs immédiats
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Installe les dépendances Python dans un virtualenv isolé
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ==========================================================
# ÉTAPE 2 : RUNTIME (image finale légère)
# ==========================================================
FROM python:3.12-slim-bookworm AS runtime

# Dépendances système RUNTIME uniquement (pas de build-essential, gcc...)
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
    gettext \                 # ← AJOUT CRITIQUE
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    BROWSER_PATH=/usr/bin/chromium

WORKDIR /app

# Copie le virtualenv depuis l'étape builder (contient toutes les libs Python)
COPY --from=builder /opt/venv /opt/venv

# Copie le code de l'application
COPY . .

# Compile les fichiers de traduction (.po → .mo)
RUN python manage.py compilemessages

# Collecte les fichiers statiques
RUN python manage.py collectstatic --noinput

# Utilisateur non-root pour la sécurité
RUN adduser --disabled-password --gecos "" django \
    && chown -R django:django /app
USER django

EXPOSE 8000

# Gunicorn comme serveur WSGI en production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "ProjectInsight.wsgi:application"]