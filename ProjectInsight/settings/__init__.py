# ProjectInsight/settings.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ==========================================================
# SÉCURITÉ
# ==========================================================

LOCAL_SECRET_KEY = "django-insecure-local-dev-only-change-this"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", LOCAL_SECRET_KEY)

DEBUG = os.environ.get("DEBUG", "True").strip().lower() in (
    "true", "1", "yes"
)

if os.environ.get("RENDER"):
    if not os.environ.get("DJANGO_SECRET_KEY") or SECRET_KEY == LOCAL_SECRET_KEY:
        raise RuntimeError("Configure une vraie DJANGO_SECRET_KEY sur Render.")
    if DEBUG:
        raise RuntimeError("DEBUG doit être False en production sur Render.")

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1,insightboard-fev0.onrender.com"
    ).split(",") if h.strip()
]

RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]
if RENDER_EXTERNAL_HOSTNAME:
    auto_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if auto_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(auto_origin)

# ==========================================================
# MODE DB / CACHE-ONLY
# ==========================================================
# USE_LOCAL_DB=1  → PostgreSQL local (dev)
# USE_LOCAL_DB=0  → aucune DB, tout passe par le cache (prod Render)
# Défaut : True si DEBUG=True, sinon False.
_default_use_db = "1" if DEBUG else "0"
USE_LOCAL_DB = os.environ.get("USE_LOCAL_DB", _default_use_db).strip() == "1"

# ==========================================================
# BASE DE DONNÉES
# ==========================================================
if USE_LOCAL_DB:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "insightdb"),
            "USER": os.environ.get("DB_USER", "guizo"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "1234"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        },
    }
else:
    DATABASES = {}   # ← aucun accès DB

# ==========================================================
# CACHE
# ==========================================================
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "TIMEOUT": 60 * 60 * 24,   # 24h
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "insight-local",
            "TIMEOUT": 60 * 60 * 24,
        }
    }

# ==========================================================
# SESSIONS
# ==========================================================
SESSION_ENGINE = (
    "django.contrib.sessions.backends.db"
    if USE_LOCAL_DB
    else "django.contrib.sessions.backends.signed_cookies"
)

# ==========================================================
# APPLICATIONS
# ==========================================================
_BASE_APPS = [
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.messages",
    "django.contrib.sessions",
    "corsheaders",
    "InsightApp",
]

_DB_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
]

INSTALLED_APPS = (_BASE_APPS + _DB_APPS) if USE_LOCAL_DB else _BASE_APPS

# ==========================================================
# MIDDLEWARE
# ==========================================================
_MW_COMMON = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]
_MW_DB = ["django.contrib.auth.middleware.AuthenticationMiddleware"]
_MW_TAIL = [
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
MIDDLEWARE = _MW_COMMON + (_MW_DB if USE_LOCAL_DB else []) + _MW_TAIL

# ==========================================================
# URLS ET TEMPLATES
# ==========================================================
ROOT_URLCONF = "ProjectInsight.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.messages.context_processors.messages",
                "InsightApp.context_processors.company_processor",
            ] + (
                ["django.contrib.auth.context_processors.auth"]
                if USE_LOCAL_DB else []
            ),
        },
    },
]

WSGI_APPLICATION = "ProjectInsight.wsgi.application"

# ==========================================================
# AUTHENTIFICATION
# ==========================================================
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 6},
    },
]

# ==========================================================
# INTERNATIONALISATION
# ==========================================================
USE_I18N = True
USE_TZ = True

LANGUAGES = [("fr", "Français"), ("en", "English")]
LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Douala"
LOCALE_PATHS = [BASE_DIR.parent / "locale"]

# ==========================================================
# FICHIERS STATIQUES
# ==========================================================
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ==========================================================
# HTTPS EN PRODUCTION
# ==========================================================
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ==========================================================
# DIVERS
# ==========================================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
CORS_ALLOW_ALL_ORIGINS = DEBUG
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ==========================================================
# UPLOAD
# ==========================================================
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "10"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024

# ==========================================================
# ENTREPRISE
# ==========================================================
COMPANY_NAME    = os.environ.get("COMPANY_NAME",    "InsightBoard")
COMPANY_ADDRESS = os.environ.get("COMPANY_ADDRESS", "Paris, France")
COMPANY_PHONE   = os.environ.get("COMPANY_PHONE",   "+237 6 91 72 77 58")
COMPANY_EMAIL   = os.environ.get("COMPANY_EMAIL",   "contact@insightboard.app")
COMPANY_WEBSITE = os.environ.get("COMPANY_WEBSITE", "https://insightboard.app")

# ==========================================================
# MODE D'ANALYSE
# ==========================================================
ANALYSIS_MODE = os.environ.get("ANALYSIS_MODE", "local").strip().lower()

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT") or ""
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "dev-webhook-token")

if ANALYSIS_MODE == "github":
    missing = [
        name for name, value in [
            ("GITHUB_TOKEN", GITHUB_TOKEN),
            ("GITHUB_REPO",  GITHUB_REPO),
            ("WEBHOOK_TOKEN", os.environ.get("WEBHOOK_TOKEN")),
        ] if not value
    ]
    if missing:
        raise RuntimeError(
            f"ANALYSIS_MODE=github requiert : {', '.join(missing)}. "
            f"Configure-les sur Render → Environment."
        )