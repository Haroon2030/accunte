"""
تصعيد طلبات الخدمة المتأخرة عن مهلتها. جدوِله كل 5-10 دقائق (Cron أو Task Scheduler):
    python manage.py escalate_overdue_requests
"""
from django.core.management.base import BaseCommand

from apps.servicedesk.services import escalate_overdue


class Command(BaseCommand):
    help = 'تصعيد طلبات الخدمة المتأخرة'

    def handle(self, *args, **options):
        n = escalate_overdue()
        self.stdout.write(self.style.SUCCESS(f'تم تصعيد {n} طلب'))
