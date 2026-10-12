"""
يحذف جداول المشروع القديم من قاعدة البيانات (بعد إلغائه).

افتراضياً يعرض فقط ما سيُحذف (dry-run). التنفيذ الفعلي يتطلب --yes، وهو لا رجعة فيه: خذ نسخة احتياطية أولاً.
يُبقي جداول Django الأساسية (المستخدمون والجلسات...) وجداول التطبيقات الحالية، ويحذف الباقي،
وينظّف سجلات الترحيل وأنواع المحتوى الخاصة بالتطبيقات المحذوفة.
"""
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'يحذف جداول المشروع القديم (dry-run افتراضياً؛ --yes للتنفيذ)'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='ينفّذ الحذف فعلاً (لا رجعة فيه)')

    def handle(self, *args, **opts):
        keep = {m._meta.db_table for m in apps.get_models()}
        keep |= {m._meta.db_table for m in apps.get_models(include_auto_created=True)}
        keep.add('django_migrations')
        existing = connection.introspection.table_names()
        legacy = sorted(t for t in existing if t not in keep)
        known_apps = {c.label for c in apps.get_app_configs()}
        self.stdout.write(f'جداول قديمة: {len(legacy)}')
        for t in legacy:
            self.stdout.write(f'  - {t}')
        if not opts['yes']:
            self.stdout.write(self.style.WARNING('dry-run: لم يُحذف شيء. أعد التشغيل مع --yes بعد أخذ نسخة احتياطية.'))
            return
        vendor = connection.vendor
        with connection.cursor() as cur:
            if vendor == 'mysql':
                cur.execute('SET FOREIGN_KEY_CHECKS=0')
            elif vendor == 'sqlite':
                cur.execute('PRAGMA foreign_keys=OFF')
            for t in legacy:
                cur.execute(f'DROP TABLE IF EXISTS {connection.ops.quote_name(t)}')
            if vendor == 'mysql':
                cur.execute('SET FOREIGN_KEY_CHECKS=1')
            elif vendor == 'sqlite':
                cur.execute('PRAGMA foreign_keys=ON')
            placeholders = ','.join(['%s'] * len(known_apps))
            cur.execute(f'DELETE FROM django_migrations WHERE app NOT IN ({placeholders})', list(known_apps))
        removed, _ = ContentType.objects.exclude(app_label__in=known_apps).delete()
        self.stdout.write(self.style.SUCCESS(f'حُذفت {len(legacy)} جدولاً، ونُظّف {removed} سجل نوع محتوى وصلاحية.'))
