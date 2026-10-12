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

# En production sur Render, une vraie clé secrète est obligatoire.
if os.environ.get("RENDER"):
    if (
        not os.environ.get("DJANGO_SECRET_KEY")
        or SECRET_KEY == LOCAL_SECRET_KEY
    ):
        raise RuntimeError(
            "Configure une vraie DJANGO_SECRET_KEY dans les variables "
            "d'environnement de Render."
        )

    if DEBUG:
        raise RuntimeError(
            "DEBUG doit être False en production sur Render."
        )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1,insightboard-fev0.onrender.com"
    ).split(",")
    if host.strip()
]

# Ajoute automatiquement le domaine attribué par Render.
RENDER_EXTERNAL_HOSTNAME = os.environ.get(
    "RENDER_EXTERNAL_HOSTNAME"
)

if RENDER_EXTERNAL_HOSTNAME:
    if RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Origines de confiance CSRF (nécessaire dès que le site est en HTTPS).
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CSRF_TRUSTED_ORIGINS", ""
    ).split(",")
    if origin.strip()
]

if RENDER_EXTERNAL_HOSTNAME:
    auto_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if auto_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(auto_origin)


# ==========================================================
# APPLICATIONS
# ==========================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    "corsheaders",
    "rosetta",
    "InsightApp",
]


# ==========================================================
# MIDDLEWARE
# ==========================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


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
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "InsightApp.context_processors.company_processor",
            ],
        },
    },
]

WSGI_APPLICATION = "ProjectInsight.wsgi.application"

# ==========================================================
# BASE DE DONNÉES
# ==========================================================

import dj_database_url

DATABASE_URL = os.environ.get("PRISMA_DATABASE_URL")
# Initialisation du dictionnaire des bases
DATABASES = {}

# ----------------------------------------------------------
# Connexion principale
# ----------------------------------------------------------

if DATABASE_URL:
    DATABASES["default"] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=0,
        conn_health_checks=True,
        ssl_require=True,
    )
    DATABASES["default"]["OPTIONS"] = {
    "connect_timeout": 30,
     }
else:
    # PostgreSQL local
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "insightdb",
        "USER": "guizo",
        "PASSWORD": os.environ.get("DB_PASSWORD", "1234"),
        "HOST": "localhost",
        "PORT": "5432",
    }



# ==========================================================
# AUTHENTIFICATION
# ==========================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {
            "min_length": 6,
        },
    },
]


# ==========================================================
# INTERNATIONALISATION
# ==========================================================

USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("fr", "Français"),
    ("en", "English"),
]

LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Douala"

LOCALE_PATHS = [
    BASE_DIR.parent / "locale",
]


# ==========================================================
# FICHIERS STATIQUES ET MÉDIAS
# ==========================================================

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}


# ==========================================================
# SÉCURITÉ HTTPS EN PRODUCTION
# ==========================================================

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Render termine le HTTPS au niveau de son proxy.
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO", "https",
)


# ==========================================================
# CONFIGURATION DJANGO
# ==========================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==========================================================
# CORS
# ==========================================================

CORS_ALLOW_ALL_ORIGINS = DEBUG


# ==========================================================
# EMAIL
# ==========================================================

# En développement, les e-mails sont affichés dans la console.
EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
)


# ==========================================================
# UPLOAD (spécifique InsightBoard)
# ==========================================================

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "10"))

DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024


# ==========================================================
# INFORMATIONS DE L'ENTREPRISE
# ==========================================================

COMPANY_NAME = os.environ.get(
    "COMPANY_NAME",
    "InsightBoard",
)

COMPANY_ADDRESS = os.environ.get(
    "COMPANY_ADDRESS",
    "Paris, France",
)

COMPANY_PHONE = os.environ.get(
    "COMPANY_PHONE",
    "+237 6 91 72 77 58",
)

COMPANY_EMAIL = os.environ.get(
    "COMPANY_EMAIL",
    "contact@insightboard.app",
)

COMPANY_WEBSITE = os.environ.get(
    "COMPANY_WEBSITE",
    "https://insightboard.app",
)

# ==========================================================
# MODE D'ANALYSE
# ==========================================================
# "local"  → analyse synchrone dans la vue (développement)
# "github" → analyse déléguée à GitHub Actions (production)
ANALYSIS_MODE = os.environ.get("ANALYSIS_MODE", "local").strip().lower()

# Requis uniquement si ANALYSIS_MODE == "github"
# Accepte les deux noms pour éviter les confusions :
#   - GITHUB_TOKEN : nom standard utilisé dans le code et le workflow
#   - GH_PAT       : nom que l'on retrouve parfois dans les secrets GitHub
GITHUB_TOKEN = (
    os.environ.get("GITHUB_TOKEN")
    or os.environ.get("GH_PAT")
    or ""
)
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")     # "user/insightboard"
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

# Sécurité : empêcher le mode github sans token
if ANALYSIS_MODE == "github" and not GITHUB_TOKEN:
    raise RuntimeError(
        "ANALYSIS_MODE=github requiert la variable GITHUB_TOKEN."
    )

WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "dev-webhook-token")

if ANALYSIS_MODE == "github":
    missing = []
    for name, value in [
        ("GITHUB_TOKEN", GITHUB_TOKEN),
        ("GITHUB_REPO",  GITHUB_REPO),
        ("WEBHOOK_TOKEN", os.environ.get("WEBHOOK_TOKEN")),
    ]:
        if not value:
            missing.append(name)

    if missing:
        raise RuntimeError(
            f"ANALYSIS_MODE=github requiert ces variables "
            f"d'environnement : {', '.join(missing)}. "
            f"Configure-les sur Render → Environment."
        )