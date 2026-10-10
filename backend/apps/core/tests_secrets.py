"""حراسة: لا أسرار مكتوبة في ملفات النشر. تُتخطى إن لم تكن الملفات متاحة (داخل الحاوية مثلًا)."""
import re
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR).parent
SECRET_ENV = re.compile(r'^\s*(ENV|ARG)\s+\w*(PASSWORD|SECRET|TOKEN|API_?KEY)\w*\s*=\s*\S+', re.I | re.M)
WILDCARD_HOSTS = re.compile(r'ALLOWED_HOSTS\s*=.*\*')


class NoSecretsInDeployFilesTests(SimpleTestCase):
    def files(self):
        return [p for p in (ROOT / 'Dockerfile', ROOT / 'backend' / 'Dockerfile') if p.exists()]

    def test_dockerfiles_have_no_embedded_secrets(self):
        files = self.files()
        if not files:
            raise unittest.SkipTest('ملفات Dockerfile غير متاحة')
        for p in files:
            text = p.read_text(encoding='utf-8')
            self.assertIsNone(SECRET_ENV.search(text), f'سر مكتوب في {p.name}')
            self.assertIsNone(WILDCARD_HOSTS.search(text), f'ALLOWED_HOSTS بنجمة في {p.name}')

    def test_entrypoint_does_not_create_default_password_admin(self):
        p = ROOT / 'backend' / 'entrypoint.sh'
        if not p.exists():
            raise unittest.SkipTest('entrypoint.sh غير متاح')
        text = p.read_text(encoding='utf-8')
        self.assertNotIn('123456', text)
        self.assertIn('ADMIN_PASSWORD', text)

    def test_production_settings_require_secrets(self):
        text = (Path(settings.BASE_DIR) / 'config' / 'settings' / 'production.py').read_text(encoding='utf-8')
        for key in ("config('SECRET_KEY')", "config('DB_PASSWORD')"):
            self.assertIn(key, text)       # بلا قيمة افتراضية: يفشل الإقلاع إن غابت
