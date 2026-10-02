import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-fallback-key-change-in-production')

def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes')

DEBUG = env_bool('DEBUG', True)
if not DEBUG and (len(SECRET_KEY) < 32 or SECRET_KEY.startswith('django-insecure')):
    raise ValueError('Set a private SECRET_KEY before disabling DEBUG.')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')

# ── LLM preference ─────────────────────────────────────────────────────────
# Set True  → go straight to Ollama (skip Gemini) — use when Gemini quota exhausted
# Set False → try Gemini first, fall back to Ollama
LLM_PREFER_LOCAL = env_bool('LLM_PREFER_LOCAL', True)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'core',
    'vetting',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'core.middleware.ClientContextMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'Ai_telent_match.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'Ai_telent_match.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ── Email Configuration ───────────────────────────────────────────────────────
# Console backend: emails print to terminal (perfect for demo/dev)
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = 'AI Talent Match <noreply@aitalentmatch.com>'
SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000').rstrip('/')   # used in interview email links

# To send real emails (production), replace EMAIL_BACKEND with:
# EMAIL_BACKEND    = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST       = 'smtp.gmail.com'
# EMAIL_PORT       = 587
# EMAIL_USE_TLS    = True
# EMAIL_HOST_USER  = 'your-gmail@gmail.com'
# EMAIL_HOST_PASSWORD = 'your-app-password'   # Gmail App Password (not your login password)

# Session Configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_SECURE = not DEBUG  # Set to True in production with HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static',
                    *([BASE_DIR / 'vetting' / 'static'] if (BASE_DIR / 'vetting' / 'static').exists() else []),
                    ]

# Media files (uploaded resumes, etc.)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Celery Configuration (for daily batch processing)
CELERY_BROKER_URL = 'redis://localhost:6379/0'
CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20
}

# CORS Settings
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# Deployment and external services use private local environment values.
if os.environ.get('DB_ENGINE') == 'postgresql':
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'ai_talent_match'),
        'USER': os.environ.get('DB_USER', ''),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
CORS_ALLOWED_ORIGINS = list(filter(None, os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')))
CSRF_TRUSTED_ORIGINS = list(filter(None, os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')))
CSRF_FAILURE_VIEW = 'core.middleware.csrf_failure'
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
MAX_PROFILE_UPLOAD_BYTES = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT = 10
JUDGE0_URL = os.environ.get('JUDGE0_URL', 'http://127.0.0.1:2358').rstrip('/')
JUDGE0_AUTH_TOKEN = os.environ.get('JUDGE0_AUTH_TOKEN', '')
ENABLE_CHAT = env_bool('ENABLE_CHAT', False)
ASGI_APPLICATION = 'Ai_telent_match.asgi.application'
CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
if os.environ.get('REDIS_URL'):
    CHANNEL_LAYERS = {'default': {'BACKEND': 'channels_redis.core.RedisChannelLayer',
                                 'CONFIG': {'hosts': [os.environ['REDIS_URL']]}}}
