"""
إعدادات الإنتاج - Production Settings
"""

from .base import *
from decouple import config

# مجلد السجلات يُنشأ هنا كي لا يفشل الإقلاع إن غاب (مثلًا خارج Docker)
(BASE_DIR / 'logs').mkdir(exist_ok=True)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='72.61.107.230,localhost,127.0.0.1', cast=lambda v: [s.strip() for s in v.split(',')])

# ══════════════════════════════════════════════════════════════════════════════
# Database - MySQL/PostgreSQL for Production
# ══════════════════════════════════════════════════════════════════════════════

DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.mysql'),
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

# ══════════════════════════════════════════════════════════════════════════════
# Security Settings
# ══════════════════════════════════════════════════════════════════════════════

def _csv(value):
    return [v.strip() for v in value.split(',') if v.strip()]


SECURE_SSL_REDIRECT = False  # Handled by reverse proxy
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# عدد الوكلاء العكسيين الموثوقين أمام التطبيق (nginx/Traefik). يُستعمل لقراءة IP العميل الحقيقي في سجل التدقيق
# وفي تحديد معدل DRF. 0 = لا نثق بـ X-Forwarded-For. تحقق بعد الضبط أن سجل التدقيق يُظهر IP الحقيقي.
PROXY_HOPS = config('PROXY_HOPS', default=0, cast=int)
# فعّلها (COOKIES_SECURE=true) عند الوصول عبر HTTPS فقط. مع true لن يعمل الدخول عبر http://IP
SESSION_COOKIE_SECURE = config('COOKIES_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
# مطلوب مع HTTPS خلف وكيل عكسي، مثال: https://account.alrsheed.net
CSRF_TRUSTED_ORIGINS = _csv(config('CSRF_TRUSTED_ORIGINS', default=''))
# HSTS: اتركه 0 حتى تتأكد أن HTTPS يعمل دائمًا، ثم ارفعه (مثال 31536000)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

# ══════════════════════════════════════════════════════════════════════════════
# CORS - Restricted origins
# ══════════════════════════════════════════════════════════════════════════════

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'http://72.61.107.230:8096',
    'http://72.61.107.230',
    'http://localhost:5173',
    'http://localhost:8096',
    'http://127.0.0.1:5173',
    'http://127.0.0.1:8096',
] + _csv(config('CORS_ALLOWED_ORIGINS', default=''))
CORS_ALLOW_CREDENTIALS = True

# ══════════════════════════════════════════════════════════════════════════════
# REST Framework - Production Settings
# ══════════════════════════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'config.pagination.CustomPagination',
    'PAGE_SIZE': 8,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
    # بدونه يرى DRF عنوان الوكيل لكل المستخدمين فيتشاركون حصة واحدة
    'NUM_PROXIES': PROXY_HOPS or None,
}

# ══════════════════════════════════════════════════════════════════════════════
# Logging
# ══════════════════════════════════════════════════════════════════════════════

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'ERROR',
    },
}
