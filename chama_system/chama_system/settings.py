from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = config('DEBUG', default=False, cast=bool)
APP_VERSION = '1.1.0'

# Require explicit secret key in production; keep a dev-only fallback for local setup.
if DEBUG:
    SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-only-change-me')
else:
    SECRET_KEY = config('SECRET_KEY')

ALLOWED_HOSTS = [
    h.strip()
    for h in config('ALLOWED_HOSTS', default='127.0.0.1,localhost').split(',')
    if h.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # local apps
    'accounts',
    'members',
    'contributions',
    'loans',
    'payments',
    'reports',
    'dashboard',
    'penalties',
    'meetings',
    'welfare',
    'yearend',
    'recycle_bin',
    'audit',
    'backup',
    'other_income',
    'bank_accounts',
    'investments',
    'utils',
    'expenses',
    'money_movement',
    'updater',
]

MIDDLEWARE = [
    'audit.db_reconnect.DbReconnectMiddleware',  # must be first — retries on stale DB after restore
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'chama_system.csrf_middleware.DesktopCsrfMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'audit.middleware.AuditMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'chama_system.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'utils.context_processors.group_settings',
                'utils.context_processors.pending_loan_applications',
                'utils.context_processors.notification_count',
                'utils.context_processors.pending_transfers',
                'utils.context_processors.app_version',
            ],
        },
    },
]

WSGI_APPLICATION = 'chama_system.wsgi.application'

# Database — SQLite for local dev, PostgreSQL in production
if config('DATABASE_URL', default=''):
    import dj_database_url
    DATABASES = {'default': dj_database_url.config(conn_max_age=600)}
elif not DEBUG and config('DB_HOST', default=''):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='chama_db'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }
else:
    import os as _os
    _desktop_db = _os.environ.get('DESKTOP_DB_PATH', '')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _desktop_db if _desktop_db else BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
_desktop_media = _os.environ.get('DESKTOP_MEDIA_ROOT', '')
if _desktop_media:
    MEDIA_ROOT = Path(_desktop_media)
elif _desktop_db:
    MEDIA_ROOT = Path(_desktop_db).parent / 'media'
else:
    MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Bulk contribution/welfare form sends ~7 fields per member row.
# With 1000 members that's 7000 fields — raise the limit well above that.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# ── Chama business rules ──────────────────────────────────────────
# Flat interest rate applied to every new loan (e.g. 0.10 = 10%).
# Also used as the monthly late-penalty rate.
LOAN_INTEREST_RATE = config('LOAN_INTEREST_RATE', default=0.10, cast=float)

# Email
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default="Finance Wise TBM <noreply@financewise.local>")

# Security (enable SSL in production only when explicitly requested)
_trusted = config('CSRF_TRUSTED_ORIGINS', default='')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _trusted.split(',') if o.strip()]
for _local_origin in ['http://127.0.0.1', 'http://localhost']:
    if _local_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_local_origin)

import os as _os
_desktop_db = _os.environ.get('DESKTOP_DB_PATH', '')
_is_desktop = _desktop_db != ''

USE_HTTPS = config('USE_HTTPS', default=False, cast=bool) or config('SECURE_SSL_REDIRECT', default=False, cast=bool)

if USE_HTTPS:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

# On the desktop app, use file-based sessions so they survive a database restore
# and don't conflict with database table rewrites.
if _is_desktop:
    SESSION_ENGINE = 'django.contrib.sessions.backends.file'
    _session_dir = Path(_desktop_db).parent / 'sessions'
    _session_dir.mkdir(parents=True, exist_ok=True)
    SESSION_FILE_PATH = str(_session_dir)

CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SAMESITE = 'Lax'

# Security headers — applied in all environments
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# ── Auto-Update System Configuration ──────────────────────────────
GITHUB_REPO_OWNER = config('GITHUB_REPO_OWNER', default='codewitheddy')
GITHUB_REPO_NAME = config('GITHUB_REPO_NAME', default='chama')
UPDATE_CHANNEL = config('UPDATE_CHANNEL', default='stable')  # 'stable' or 'beta'
UPDATER_PUBLIC_KEY = config('UPDATER_PUBLIC_KEY', default='6443eae2622048fc21d49c81c5661b1e1a841295bf1295f6dcdaffadc1387827')
