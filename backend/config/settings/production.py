"""
إعدادات الإنتاج. لا أسرار هنا: كلها من متغيرات البيئة. الإقلاع يفشل عمداً إن غاب SECRET_KEY أو DB_PASSWORD.
"""
from decouple import config

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, R2_ACCESS_KEY_ID, R2_BUCKET_NAME, R2_ENDPOINT_URL, R2_SECRET_ACCESS_KEY, STORAGES, USE_R2

(BASE_DIR / 'logs').mkdir(exist_ok=True)

SECRET_KEY = config('SECRET_KEY')
DEBUG = False


def _csv(value):
    return [v.strip() for v in value.split(',') if v.strip()]


ALLOWED_HOSTS = _csv(config('ALLOWED_HOSTS', default='localhost,127.0.0.1'))

# ── قاعدة البيانات (MySQL) ──
DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE', default='django.db.backends.mysql'),
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {'charset': 'utf8mb4'},
        # اتصالات دائمة: الصفحة تستعلم دورياً، وبدونها يُفتح اتصال جديد لكل طلب
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=600, cast=int),
        'CONN_HEALTH_CHECKS': True,
    }
}

# ── الأمان خلف وكيل عكسي (Traefik/Nginx) ──
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = config('COOKIES_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_TRUSTED_ORIGINS = _csv(config('CSRF_TRUSTED_ORIGINS', default=''))
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

# ── تخزين R2 ──
if USE_R2:
    from types import SimpleNamespace

    from django.core.exceptions import ImproperlyConfigured

    from config.r2 import missing_settings

    _cfg = SimpleNamespace(R2_ACCESS_KEY_ID=R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY=R2_SECRET_ACCESS_KEY,
                           R2_BUCKET_NAME=R2_BUCKET_NAME, R2_ENDPOINT_URL=R2_ENDPOINT_URL)
    _missing = missing_settings(_cfg)
    if _missing:
        raise ImproperlyConfigured('USE_R2=True لكن هذه المتغيرات ناقصة: ' + ', '.join(_missing))

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'verbose': {'format': '{levelname} {asctime} {module} {message}', 'style': '{'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
