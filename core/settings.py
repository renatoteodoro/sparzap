"""
Django settings for the Sparzap project.
"""

from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-troque-em-producao')

# Cifra as API keys de IA em repouso (ai.crypto). Em produção, defina de
# verdade em .env — gere com:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Sem a variável (dev/teste), deriva uma chave determinística do SECRET_KEY
# para não exigir configuração extra — nunca use esse fallback em produção.
AI_FIELD_ENCRYPTION_KEY = config('AI_FIELD_ENCRYPTION_KEY', default='')
if not AI_FIELD_ENCRYPTION_KEY:
    import base64
    import hashlib

    AI_FIELD_ENCRYPTION_KEY = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()

DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
if DEBUG and 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')

CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

# Atrás do Nginx (proxy reverso, Sprint 18): confia no header que o Nginx
# define para indicar que a conexão original do cliente era HTTPS.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # HSTS/SSL redirect ficam desligados por padrão até o HTTPS estar
    # configurado de verdade no Nginx (ver docs/DEPLOY.md); ligue via .env
    # (SECURE_SSL_REDIRECT=True) depois de confirmar o certificado.
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'django_celery_beat',
    'core',
    'accounts',
    'instances',
    'webhooks',
    'contacts',
    'library',
    'scripts',
    'campaigns',
    'antiblock',
    'triggers',
    'crm',
    'reports',
    'api',
    'ai',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

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

WSGI_APPLICATION = 'core.wsgi.application'


# Database
# Produção: PostgreSQL 16 (já disponível no host da Evolution API).
# Dev sem Postgres: deixe DB_ENGINE=sqlite3 no .env (padrão).
if config('DB_ENGINE', default='sqlite3') == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='sparzap'),
            'USER': config('DB_USER', default='sparzap'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True


# Static & media files
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
# ManifestStaticFilesStorage exige que `collectstatic` já tenha rodado (gera
# staticfiles.json com os hashes); em dev/test isso nunca acontece, então
# usamos o storage simples do WhiteNoise, que serve os arquivos direto sem
# depender de manifesto. Produção (Sprint 18) roda `collectstatic` no build
# do Docker e usa o storage comprimido/versionado.
STORAGES = {
    'staticfiles': {
        'BACKEND': (
            'whitenoise.storage.CompressedManifestStaticFilesStorage'
            if not DEBUG
            else 'whitenoise.storage.CompressedStaticFilesStorage'
        ),
    },
}

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Auth redirects
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'landing'


# Celery
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/1')
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=False, cast=bool)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'


# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '120/minute',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Sparzap API',
    'DESCRIPTION': 'API REST do Sparzap — automação de vendas e divulgação no WhatsApp.',
    'VERSION': '1.0.0',
}


# Evolution API
EVOLUTION_BASE_URL = config('EVOLUTION_BASE_URL', default='http://localhost:8080')
EVOLUTION_API_KEY = config('EVOLUTION_API_KEY', default='')
EVOLUTION_WEBHOOK_SECRET = config('EVOLUTION_WEBHOOK_SECRET', default='troque-por-um-segredo')
EVOLUTION_WEBHOOK_BASE_URL = config('EVOLUTION_WEBHOOK_BASE_URL', default='http://localhost:8000')

# Alertas operacionais (Sprint 19) — opcional; se vazio, alertas só vão pro log
ALERT_WEBHOOK_URL = config('ALERT_WEBHOOK_URL', default='')


# Logging estruturado (Sprint 19) — texto legível em dev, JSON em produção
# (mais fácil de agregar/filtrar por instance_id/campaign_id num coletor de
# logs externo, ex. `docker compose logs` + grep/jq).
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'structured': {
            'format': '%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s',
        },
        'json': {
            '()': 'core.logging_utils.JsonFormatter',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json' if not DEBUG else 'structured',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'sparzap': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
