import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
if os.getenv("VERCEL"):
    ALLOWED_HOSTS.append(".vercel.app")
    if os.getenv("VERCEL_URL"):
        ALLOWED_HOSTS.append(os.getenv("VERCEL_URL"))

CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
if os.getenv("VERCEL"):
    CSRF_TRUSTED_ORIGINS.append("https://*.vercel.app")
    if os.getenv("VERCEL_URL"):
        CSRF_TRUSTED_ORIGINS.append(f"https://{os.getenv('VERCEL_URL')}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "merchants",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
# CsrfViewMiddleware renders this directly on failure, bypassing handler403/403.html.
CSRF_FAILURE_VIEW = "merchants.views.csrf_failure"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.gaxtron",
            ],
        },
    },
]

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv(
            "DATABASE_URL",
            "postgresql://gaxtron:gaxtron_secret@127.0.0.1:5433/gaxtron_db",
        ),
        conn_max_age=0,
    )
}
# Supabase's pooled connection (port 6543) runs PgBouncer in transaction mode, which doesn't
# support server-side cursors shared across statements in a transaction — Django's own docs
# call out disabling them for exactly this setup.
if str(DATABASES["default"].get("PORT")) == "6543":
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# `manage.py test` needs its own throwaway database — CREATE DATABASE isn't reliable (or fast)
# over a PgBouncer transaction-pooling connection like Supabase's, so tests always run on
# local SQLite regardless of what DATABASE_URL points at.
if "test" in sys.argv:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# WhiteNoise serves directly via Django's staticfiles finders — no `collectstatic` build step
# needed, which matters because Vercel's Python builder has no build-command hook to run one.
WHITENOISE_USE_FINDERS = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://127.0.0.1:8001")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", FASTAPI_URL).rstrip("/")

# --- Gaxtron payment engine (ported from GaX/app/config.py; same env var names) ---
JWT_SECRET_KEY = os.getenv("SECRET_KEY", "change-me-min-32-chars-for-jwt-signing-abc123")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-min-32-chars-for-webhook-hmac-abc")
WALLET_ENCRYPTION_KEY = os.getenv("WALLET_ENCRYPTION_KEY", "change-me-32-byte-encryption-key-here!!")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

BLOCKCHAIN_RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL", "https://rpc.sepolia.org")
BLOCKCHAIN_NETWORK = os.getenv("BLOCKCHAIN_NETWORK", "sepolia")

# Mainnet safeguard: switching off testnet must be a deliberate, explicit act — not a
# typo'd env var on a hosting dashboard. Real ETH/USDT move on mainnet; a silent switch
# has no undo. Setting BLOCKCHAIN_NETWORK to anything other than a known testnet name
# requires ALSO setting CONFIRM_MAINNET_DEPLOY to the exact confirmation string below,
# ideally as a separate deploy step from flipping BLOCKCHAIN_NETWORK itself.
_TESTNET_NETWORKS = {"sepolia", "testnet", "goerli", "holesky"}
_MAINNET_CONFIRM_TOKEN = "yes-switch-to-mainnet"
if BLOCKCHAIN_NETWORK.lower() not in _TESTNET_NETWORKS:
    if os.getenv("CONFIRM_MAINNET_DEPLOY", "").strip() != _MAINNET_CONFIRM_TOKEN:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            f"BLOCKCHAIN_NETWORK={BLOCKCHAIN_NETWORK!r} is not a recognized testnet "
            f"({sorted(_TESTNET_NETWORKS)}) — refusing to start against what looks like "
            f"mainnet. This moves real funds. If that's intentional, also set "
            f"CONFIRM_MAINNET_DEPLOY={_MAINNET_CONFIRM_TOKEN!r} (as its own deliberate "
            f"deploy step, not bundled with the network change)."
        )

ETH_REQUIRED_CONFIRMATIONS = int(os.getenv("ETH_REQUIRED_CONFIRMATIONS", "3"))
USDT_CONTRACT_ADDRESS = os.getenv("USDT_CONTRACT_ADDRESS", "0x94a9D9AC8a22534D3cDfaD9d54e96e22d858e9b")
BLOCKCHAIN_SCAN_BLOCKS = int(os.getenv("BLOCKCHAIN_SCAN_BLOCKS", "500"))
ENABLED_CHAINS = os.getenv("ENABLED_CHAINS", "ETH")

CRON_SECRET = os.getenv("CRON_SECRET", "")
CHECKOUT_RECONCILE_ON_POLL = os.getenv("CHECKOUT_RECONCILE_ON_POLL", "True").lower() == "true"

API_RATE_LIMIT = int(os.getenv("API_RATE_LIMIT", "100"))
API_RATE_LIMIT_WINDOW = int(os.getenv("API_RATE_LIMIT_WINDOW", "60"))
AUTH_RATE_LIMIT = int(os.getenv("AUTH_RATE_LIMIT", "20"))
AUTH_RATE_LIMIT_WINDOW = int(os.getenv("AUTH_RATE_LIMIT_WINDOW", "300"))

PAYMENT_EXPIRY_MINUTES = int(os.getenv("PAYMENT_EXPIRY_MINUTES", "60"))
MAX_API_KEYS_PER_USER = int(os.getenv("MAX_API_KEYS_PER_USER", "10"))
WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", "5"))
WEBHOOK_RETRY_BASE_SECONDS = int(os.getenv("WEBHOOK_RETRY_BASE_SECONDS", "30"))

REQUIRE_HTTPS_CALLBACKS = os.getenv("REQUIRE_HTTPS_CALLBACKS", "False").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

AUTH_USER_MODEL = "merchants.GaxtronUser"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "merchants.api_exceptions.exception_handler",
}

# Production security (when DEBUG=False)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "False").lower() == "true"
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
