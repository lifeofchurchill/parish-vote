"""
Settings for the parish election check-in system.

The same file runs on your laptop and on the live server (Render):
- On your laptop: DEBUG on, SQLite database, no HTTPS.
- On Render: DEBUG off, PostgreSQL (from DATABASE_URL), HTTPS-only cookies.
Render sets an environment variable called RENDER on its servers, which is how
this file knows where it's running. Secrets come from environment variables.

Election details (name, date, age rule, centres, sessions) are NOT here:
they live in the database and are managed in the admin, so the system
can be reused for future elections without code changes.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Project root folder (the one containing manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# True on Render's servers (Render sets RENDER=true), False on your laptop
ON_RENDER = "RENDER" in os.environ

# DEBUG shows detailed error pages. Off on Render unless someone deliberately turns it on.
DEBUG = os.environ.get("DJANGO_DEBUG", "False" if ON_RENDER else "True") == "True"

# SECURITY: the real key comes from an environment variable on the live server
DEV_SECRET_KEY = "dev-only-insecure-key-change-me"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", DEV_SECRET_KEY)
if not DEBUG and SECRET_KEY == DEV_SECRET_KEY:
    # Refuse to start a live site with the well-known development key
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY: the live site can't use the development key.")

# Which web addresses this site answers to.
# Development: any (so you can open it from your phone on the same Wi-Fi).
# Live: the Render address (Render tells us it), plus any extra ones listed in DJANGO_ALLOWED_HOSTS.
if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
    RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
    if RENDER_EXTERNAL_HOSTNAME:
        ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Forms (sign-in, ticks) are only accepted from our own HTTPS address
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS if host != "*"]


# Apps: Django's built-ins plus our own "voting" app
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "voting",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves our CSS, JavaScript and images on the live server (right after Security)
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # All our HTML lives in one top-level "templates" folder
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Our own: puts {{ election }} (the active election) in every template
                "voting.context_processors.active_election",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database: whatever DATABASE_URL points to (PostgreSQL on Render), or SQLite on your laptop.
# conn_max_age keeps a connection open for 10 minutes instead of reconnecting on every page;
# conn_health_checks makes sure a kept connection still works before using it.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Language and time: show times in Ghana time
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Accra"
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, images). collectstatic gathers them into STATIC_ROOT.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# On the live server, every file gets a fingerprint in its name (app.3f9a2c1b.css) and is
# compressed. When a file changes its name changes, so phones never keep an old copy:
# no more Ctrl+F5. On your laptop, files are served plainly as before.
# (config/storage.py: WhiteNoise's storage, but a missing image can't crash a page.)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
            else "config.storage.ForgivingStaticFilesStorage"
        ),
    },
}
WHITENOISE_MANIFEST_STRICT = False

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Login: where to send people before and after signing in or out
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "voting:checkin"
LOGOUT_REDIRECT_URL = "login"


# HTTPS on the live server only (your laptop has no HTTPS, so these would lock you out there)
if ON_RENDER:
    # Render handles HTTPS and tells Django about it in this header
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Anyone typing http:// is sent to https://. The health check is left alone.
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
    # Sign-in and form cookies are only ever sent over HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Browsers remember to use HTTPS for this site for 30 days
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30


# Errors are printed to the server log (Render's "Logs" tab), so you can see what went wrong
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}