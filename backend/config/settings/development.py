"""إعدادات التطوير."""
from .base import *  # noqa: F401,F403

SECRET_KEY = 'django-insecure-dev-key-change-in-production'
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', 'testserver']
