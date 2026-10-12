"""
الإعدادات المشتركة: بوابة مطابقة الموردين (Django API + واجهة ثابتة تُخدَّم من نفس النطاق بجلسات).
القيم الحساسة تأتي من متغيرات البيئة فقط.
"""
from pathlib import Path

from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# الواجهة: داخل الصورة /app/frontend، وعلى جهاز التطوير بجوار مجلد backend
FRONTEND_DIR = next(
    (p for p in (BASE_DIR / 'frontend', BASE_DIR.parent / 'frontend') if (p / 'index.html').exists()),
    BASE_DIR.parent / 'frontend',
)

SECRET_KEY = 'django-insecure-dev-only'
DEBUG = True
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.accounts',
    'apps.matching',
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

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []     # قواعد كلمة المرور تُطبَّق في apps.accounts (8 خانات، حروف وأرقام)

LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Asia/Riyadh'
USE_I18N = True
USE_TZ = True

# ── الملفات الثابتة: الواجهة تُخدَّم من /static/frontend/ ──
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [('frontend', FRONTEND_DIR)]
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── الجلسات ──
SESSION_COOKIE_AGE = 60 * 60 * 12
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False      # الواجهة تقرأ الرمز وترسله في X-CSRFToken

# ── المرفقات (كشوف الحساب والمراسلات): خاصة، التنزيل عبر API بعد فحص الصلاحية ──
PRIVATE_MEDIA_ROOT = BASE_DIR / 'private_media'
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_MESSAGE = 10
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# ── Cloudflare R2 (اختياري): نفس المتغيرات المستعملة سابقاً في الإنتاج ──
USE_R2 = config('USE_R2', default=False, cast=bool)
R2_ACCESS_KEY_ID = config('R2_ACCESS_KEY_ID', default='')
R2_SECRET_ACCESS_KEY = config('R2_SECRET_ACCESS_KEY', default='')
R2_BUCKET_NAME = config('R2_BUCKET_NAME', default='')
R2_ENDPOINT_URL = config('R2_ENDPOINT_URL', default='').rstrip('/')
R2_REGION = config('R2_REGION', default='auto')
R2_PUBLIC_DOMAIN = config('R2_PUBLIC_DOMAIN', default='').strip()
R2_SIGNED_URLS = config('R2_SIGNED_URLS', default=True, cast=bool)
R2_SIGNED_URL_EXPIRE = config('R2_SIGNED_URL_EXPIRE', default=3600, cast=int)
R2_PROXY_MEDIA = config('R2_PROXY_MEDIA', default=True, cast=bool)
R2_PREFIX = config('R2_PREFIX', default='accounting').strip('/')

# ── قفل الدخول بعد محاولات خاطئة ──
LOGIN_MAX_FAILS = 5
LOGIN_LOCK_SECONDS = 30
