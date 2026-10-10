"""
فحص اتصال Cloudflare R2: يكتب ملفًا صغيرًا ويقرؤه ويولّد رابطًا موقّعًا ثم يحذفه، لكلا التخزينين
(الافتراضي للوسائط، والخاص لمرفقات المطابقة/المقترحات/الطلبات).

    python manage.py r2_check

لا يطبع أي مفتاح. يكتب فقط داخل <R2_PREFIX>/_healthcheck/ ويحذف ما كتبه.
"""
import uuid
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from apps.reconciliation.storage import get_private_storage


class Command(BaseCommand):
    help = 'فحص الاتصال بـ Cloudflare R2'

    def handle(self, *args, **options):
        if not settings.USE_R2:
            raise CommandError('USE_R2 غير مفعّل. فعّله في البيئة أولًا.')
        host = urlparse(settings.R2_ENDPOINT_URL).hostname or ''
        self.stdout.write(
            f'bucket={settings.R2_BUCKET_NAME}  prefix={settings.R2_PREFIX or "(none)"}  '
            f'endpoint={host[:6]}...{host[-24:]}  signed={settings.R2_SIGNED_URLS}  proxy={settings.R2_PROXY_MEDIA}')
        failures = 0
        for label, storage in (('الوسائط (default)', default_storage), ('المرفقات الخاصة', get_private_storage())):
            failures += not self._check(label, storage)
        if failures:
            raise CommandError('فشل فحص R2')
        self.stdout.write(self.style.SUCCESS('R2 يعمل: كتابة وقراءة وحذف ناجحة'))

    def _check(self, label, storage):
        name = f'_healthcheck/{uuid.uuid4().hex}.txt'
        payload = b'accounting-r2-healthcheck'
        saved = None
        try:
            saved = storage.save(name, ContentFile(payload))
            with storage.open(saved, 'rb') as fh:
                if fh.read() != payload:
                    raise RuntimeError('المحتوى المقروء لا يطابق المكتوب')
            storage.url(saved)                      # يتحقق من توليد الرابط (الموقّع)
            storage.delete(saved)
            if storage.exists(saved):
                raise RuntimeError('لم يُحذف الملف')
            self.stdout.write(self.style.SUCCESS(f'  OK   {label}'))
            return True
        except Exception as exc:                    # noqa: BLE001 - نعرض النوع فقط حتى لا نسرّب تفاصيل الاتصال
            self.stdout.write(self.style.ERROR(f'  FAIL {label}: {type(exc).__name__}: {str(exc)[:160]}'))
            if saved:
                try:
                    storage.delete(saved)
                except Exception:                   # noqa: BLE001
                    pass
            return False
