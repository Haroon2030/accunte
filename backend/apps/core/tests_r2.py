"""
اختبارات تخزين Cloudflare R2 دون اتصال بالشبكة (لا تكتب في أي bucket).
الفحص الحقيقي: python manage.py r2_check
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured  # noqa: F401
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.test import SimpleTestCase, override_settings

from apps.reconciliation.storage import get_private_storage, serve_file
from config.r2 import missing_settings, storage_options

R2 = dict(USE_R2=True, R2_ACCESS_KEY_ID='AK', R2_SECRET_ACCESS_KEY='SK', R2_BUCKET_NAME='bkt',
          R2_ENDPOINT_URL='https://acct.r2.cloudflarestorage.com', R2_REGION='auto', R2_PUBLIC_DOMAIN='',
          R2_SIGNED_URLS=True, R2_SIGNED_URL_EXPIRE=900, R2_PROXY_MEDIA=True, R2_PREFIX='accounting')


class OptionsTests(SimpleTestCase):
    def cfg(self, **kw):
        return SimpleNamespace(**{**R2, **kw})

    def test_signed_private_bucket_defaults(self):
        o = storage_options(self.cfg())
        self.assertEqual((o['bucket_name'], o['endpoint_url'], o['region_name']),
                         ('bkt', 'https://acct.r2.cloudflarestorage.com', 'auto'))
        self.assertEqual((o['signature_version'], o['addressing_style']), ('s3v4', 'path'))
        self.assertTrue(o['querystring_auth'])
        self.assertEqual(o['querystring_expire'], 900)
        self.assertIsNone(o['custom_domain'])
        self.assertEqual(o['location'], 'accounting')
        self.assertFalse(o['file_overwrite'])         # لا يستبدل ملفًا موجودًا بنفس الاسم
        self.assertIsNone(o['default_acl'])

    def test_public_domain_disables_signing(self):
        o = storage_options(self.cfg(R2_PUBLIC_DOMAIN='files.example.com'))
        self.assertEqual(o['custom_domain'], 'files.example.com')
        self.assertFalse(o['querystring_auth'])

    def test_signed_urls_off_and_prefix_trim(self):
        o = storage_options(self.cfg(R2_SIGNED_URLS=False, R2_PREFIX='/accounting/'))
        self.assertFalse(o['querystring_auth'])
        self.assertEqual(o['location'], 'accounting')

    def test_missing_settings(self):
        self.assertEqual(missing_settings(self.cfg()), [])
        self.assertEqual(set(missing_settings(self.cfg(R2_ACCESS_KEY_ID='', R2_BUCKET_NAME=''))),
                         {'R2_ACCESS_KEY_ID', 'R2_BUCKET_NAME'})

    def test_startup_fails_fast_when_enabled_without_keys(self):
        """USE_R2=True بلا مفاتيح يجب أن يوقف الإقلاع بدل الكتابة على القرص بصمت."""
        backend = Path(settings.BASE_DIR)
        env = {k: v for k, v in os.environ.items() if not k.startswith('R2_')}
        # قيم فارغة صراحةً: متغيرات البيئة تتقدم على ملف .env المحلي (الذي قد يحوي مفاتيح حقيقية)
        env.update({k: '' for k in ('R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET_NAME', 'R2_ENDPOINT_URL')})
        env.update(USE_R2='True', DJANGO_SETTINGS_MODULE='config.settings', PYTHONPATH=str(backend))
        proc = subprocess.run([sys.executable, '-c', 'import django; django.setup()'], env=env, cwd=backend,
                              capture_output=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b'R2_ACCESS_KEY_ID', proc.stderr)      # ثنائي: ترميز الطرفية في ويندوز ليس UTF-8


@override_settings(**R2)
class PrivateStorageSelectionTests(SimpleTestCase):
    def test_uses_s3_storage_when_enabled(self):
        st = get_private_storage()
        self.assertEqual(type(st).__name__, 'S3Storage')
        self.assertEqual((st.bucket_name, st.location, st.querystring_auth), ('bkt', 'accounting', True))
        self.assertEqual(st.endpoint_url, 'https://acct.r2.cloudflarestorage.com')

    @override_settings(USE_R2=False)
    def test_uses_local_disk_when_disabled(self):
        st = get_private_storage()
        self.assertIsInstance(st, FileSystemStorage)
        # خارج MEDIA_ROOT فلا يُخدَّم مباشرة من /media/ أبدًا
        self.assertNotEqual(Path(st.location).resolve(), Path(settings.MEDIA_ROOT).resolve())
        self.assertFalse(str(Path(st.location).resolve()).startswith(str(Path(settings.MEDIA_ROOT).resolve())))

    @override_settings(RECONCILIATION_STORAGE='django.core.files.storage.FileSystemStorage')
    def test_explicit_override_wins(self):
        self.assertIsInstance(get_private_storage(), FileSystemStorage)


class ServeFileTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.storage = FileSystemStorage(location=self.tmp)
        self.name = self.storage.save('a/doc.pdf', ContentFile(b'%PDF-bytes'))

    def field(self, name=None):
        return SimpleNamespace(storage=self.storage, name=name or self.name,
                               open=lambda mode: self.storage.open(name or self.name, mode))

    def test_proxy_streams_as_attachment_with_unicode_name(self):
        resp = serve_file(self.field(), 'كشف حساب.pdf')
        self.assertIsInstance(resp, FileResponse)
        self.assertEqual(b''.join(resp.streaming_content), b'%PDF-bytes')
        self.assertIn('attachment', resp['Content-Disposition'])
        self.assertIn("filename*=utf-8''", resp['Content-Disposition'].lower())

    def test_missing_file_is_404(self):
        with self.assertRaises(Http404):
            serve_file(self.field('nope.pdf'), 'x.pdf')

    @override_settings(**{**R2, 'R2_PROXY_MEDIA': False})
    def test_redirect_mode_returns_signed_url_with_attachment_disposition(self):
        seen = {}

        class FakeStorage:
            def url(self, name, parameters=None, expire=None):
                seen.update(name=name, parameters=parameters, expire=expire)
                return 'https://acct.r2.cloudflarestorage.com/bkt/accounting/x?X-Amz-Signature=abc'

        resp = serve_file(SimpleNamespace(storage=FakeStorage(), name='a/doc.pdf'), 'كشف.pdf')
        self.assertIsInstance(resp, HttpResponseRedirect)
        self.assertIn('X-Amz-Signature', resp['Location'])
        self.assertEqual(seen['expire'], 900)
        self.assertIn("attachment; filename*=UTF-8''", seen['parameters']['ResponseContentDisposition'])

    @override_settings(**{**R2, 'R2_PROXY_MEDIA': False})
    def test_redirect_mode_storage_error_is_404(self):
        class Broken:
            def url(self, *a, **k):
                raise RuntimeError('boom')
        with self.assertRaises(Http404):
            serve_file(SimpleNamespace(storage=Broken(), name='x'), 'x.pdf')

    @override_settings(USE_R2=False, R2_PROXY_MEDIA=False)
    def test_local_disk_always_proxies(self):
        self.assertIsInstance(serve_file(self.field(), 'd.pdf'), FileResponse)


class CheckCommandTests(SimpleTestCase):
    @override_settings(USE_R2=False)
    def test_refuses_when_disabled(self):
        with self.assertRaises(CommandError):
            call_command('r2_check')
