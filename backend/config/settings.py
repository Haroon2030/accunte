"""Settings. Every deployment value comes from the environment (or backend/.env)."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR.parent / 'frontend'

env = environ.Env()
environ.Env.read_env(BASE_DIR / '.env')  # real environment variables win over the file

PRODUCTION = env('DJANGO_ENV', default='development') == 'production'
DEBUG = not PRODUCTION
SECRET_KEY = env('SECRET_KEY', default='' if PRODUCTION else 'dev-only-insecure-key')
if PRODUCTION and not SECRET_KEY:
    raise RuntimeError('SECRET_KEY is required in production')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1', 'testserver'])
for _h in ('127.0.0.1', 'localhost'):  # the container healthcheck calls 127.0.0.1
    if _h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_h)
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
# hostnames that serve the suppliers' entrance only: staff accounts cannot sign in through them
SUPPLIER_HOSTS = [h.lower() for h in env.list('SUPPLIER_HOSTS', default=[])]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'storages',
    'portal',
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

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
AUTH_USER_MODEL = 'portal.User'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

# ---- database: MySQL in production, SQLite when DB_ENGINE is not set ----
DB_ENGINE = env('DB_ENGINE', default='django.db.backends.sqlite3')
if DB_ENGINE.endswith('mysql'):
    import pymysql
    pymysql.version_info = (2, 2, 1, 'final', 0)  # satisfies Django's mysqlclient version check
    pymysql.install_as_MySQLdb()
    DATABASES = {'default': {
        'ENGINE': DB_ENGINE, 'NAME': env('DB_NAME'), 'USER': env('DB_USER'), 'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST'), 'PORT': env('DB_PORT', default='3306'),
        'OPTIONS': {'charset': 'utf8mb4'}, 'CONN_MAX_AGE': 60,
    }}
else:
    DATABASES = {'default': {'ENGINE': DB_ENGINE, 'NAME': env('DB_NAME', default=str(BASE_DIR / 'db.sqlite3'))}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_PASSWORD_VALIDATORS = []  # the password rule lives in portal.validators (same rule as the UI)

LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Asia/Riyadh'
USE_I18N = True
USE_TZ = True

# ---- files: Cloudflare R2 when USE_R2, local disk otherwise ----
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'
if env.bool('USE_R2', default=False):
    default_storage = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'access_key': env('R2_ACCESS_KEY_ID'), 'secret_key': env('R2_SECRET_ACCESS_KEY'),
            'bucket_name': env('R2_BUCKET_NAME'), 'endpoint_url': env('R2_ENDPOINT_URL'),
            'region_name': env('R2_REGION', default='auto'), 'location': env('R2_PREFIX', default=''),
            'signature_version': 's3v4', 'addressing_style': 'path', 'default_acl': None,
            'file_overwrite': False, 'querystring_auth': True,
            'querystring_expire': env.int('R2_SIGNED_URL_EXPIRE', default=3600),
        },
    }
else:
    default_storage = {'BACKEND': 'django.core.files.storage.FileSystemStorage'}
STORAGES = {
    'default': default_storage,
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

# ---- static files + the frontend itself (same origin, so session cookies just work) ----
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE_ROOT = FRONTEND_DIR
WHITENOISE_INDEX_FILE = True
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_USE_FINDERS = DEBUG

# ---- API ----
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['portal.permissions.SettledAccount'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser', 'rest_framework.parsers.MultiPartParser'],
}

# ---- security ----
RATELIMIT_ENABLE = env.bool('RATELIMIT_ENABLE', default=True)   # the login limit; only a local test run switches it off
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = env.bool('COOKIES_SECURE', default=PRODUCTION)
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=0)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
if PRODUCTION:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    USE_X_FORWARDED_HOST = True

# ---- the company printed as the seller on supplier notices ----
COMPANY_PROFILE = {
    'name': env('COMPANY_NAME', default='شركة محمد رشيد الرشيد للتجارة - سكاي مول'),
    'building': env('COMPANY_BUILDING', default='5502'),
    'street': env('COMPANY_STREET', default='الامير سعد بن عبدالرحمن الفرعي'),
    'district': env('COMPANY_DISTRICT', default='حي الروابي'),
    'city': env('COMPANY_CITY', default='الرياض'),
    'country': env('COMPANY_COUNTRY', default='المملكة العربية السعودية'),
    'postal': env('COMPANY_POSTAL', default='14216'),
    'additional': env('COMPANY_ADDITIONAL', default='7535'),
    'vat': env('COMPANY_VAT', default='310792238500003'),
    'crn': env('COMPANY_CRN', default='1010055714'),
}
VAT_RATE = 15
