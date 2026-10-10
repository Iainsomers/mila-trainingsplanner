from pathlib import Path
import os
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# ========================
# SECURITY
# ========================

_is_production = bool(os.environ.get("RENDER") or os.environ.get("DATABASE_URL"))
DEBUG = os.environ.get("DEBUG", "False").strip().lower() in {"1", "true", "yes", "on"}

_configured_secret = os.environ.get("SECRET_KEY", "").strip()
if _is_production and not _configured_secret:
    raise ImproperlyConfigured("SECRET_KEY must be configured in production.")
SECRET_KEY = _configured_secret or "dev-only-secret-key"

_default_hosts = "mila-trainingsplanner.onrender.com,.onrender.com,localhost,127.0.0.1,testserver"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", _default_hosts).split(",")
    if host.strip()
]

# Render terminates TLS at its proxy.  Trust that forwarded scheme and only
# enforce HTTPS/cookie security in production; local HTTP development remains
# usable without extra certificates.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _is_production
SECURE_HSTS_SECONDS = 86400 if _is_production else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# Keep referrers on the same origin and prevent MIME sniffing. Allowing
# popups keeps OAuth flows (such as Polar login) compatible with the app.
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"
SESSION_COOKIE_SECURE = _is_production
CSRF_COOKIE_SECURE = _is_production
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

_default_csrf_origins = "https://mila-trainingsplanner.onrender.com"
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", _default_csrf_origins).split(",")
    if origin.strip()
]


# ========================
# APPLICATIONS
# ========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "core",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.CoachToolsOnlyMiddleware",
    "core.middleware.CoachViewEditAccessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


ROOT_URLCONF = "mila.urls"


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.team_branding",
            ],
        },
    },
]


WSGI_APPLICATION = "mila.wsgi.application"


# ========================
# DATABASE
# ========================

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}


# ========================
# PASSWORD VALIDATION
# ========================

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ========================
# INTERNATIONALIZATION
# ========================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Europe/Amsterdam"

USE_I18N = True
USE_TZ = True


# ========================
# STATIC FILES
# ========================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ========================
# DEFAULT AUTO FIELD
# ========================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Auth redirects
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

INTERNAL_IPS = [
    "127.0.0.1",
]
