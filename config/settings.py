"""
Settings for the parish election check-in system.

Anything secret or different on the live server (secret key, debug,
allowed hosts) is read from environment variables, with safe defaults
for development on your own laptop.

Election details (name, date, age rule, centres, sessions) are NOT here:
they live in the database and are managed in the admin, so the system
can be reused for future elections without code changes.
"""
import os
from pathlib import Path

# Project root folder (the one containing manage.py)
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY: the real key will come from an environment variable on the live server
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")

# DEBUG shows detailed error pages. Must be False on the live server.
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"

# In development, allow any host so you can open the site from your phone
# on the same Wi-Fi. On the live server, list the real domain only.
if DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")


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


# Database: SQLite for development. We switch to PostgreSQL when we deploy.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
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


# Static files (our CSS). STATIC_ROOT is where they get collected on the live server.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Login: where to send people before and after signing in or out
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "voting:checkin"
LOGOUT_REDIRECT_URL = "login"