"""
نسخ سجل المراجعة القديم لطلبات الدفع إلى سجل التدقيق الجديد. آمن للتكرار (لا ينسخ السطر مرتين).
python manage.py backfill_payment_audit
"""
from django.core.management.base import BaseCommand

from apps.audit.legacy import mirror_legacy_row
from apps.payments.models import AuditLog as LegacyAuditLog


class Command(BaseCommand):
    help = 'نسخ payments.AuditLog القديم إلى سجل التدقيق الجديد'

    def handle(self, *args, **options):
        copied = skipped = 0
        for legacy in LegacyAuditLog.objects.select_related('user').order_by('id').iterator():
            if mirror_legacy_row(legacy):
                copied += 1
            else:
                skipped += 1
        self.stdout.write(self.style.SUCCESS(f'تم نسخ {copied} سجلًا، وتم تجاوز {skipped} (منسوخ مسبقًا)'))
