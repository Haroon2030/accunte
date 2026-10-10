"""
أنواع الخدمات الستة الافتراضية من المواصفات. يمكن للمدير تعديلها أو إضافة غيرها من شاشة «أنواع الخدمات».
"""
from django.db import migrations

TYPES = [
    dict(code='account-reconciliation', name='مطابقة حساب', destination_role='accountant', sla_hours=72,
         escalation_role='cs_supervisor', spawns_reconciliation=True, sort_order=10,
         description='طلب مطابقة كشف حساب المورد عن فترة مالية.',
         field_schema=[
             {'key': 'period_start', 'label': 'بداية الفترة', 'type': 'date', 'required': True, 'options': []},
             {'key': 'period_end', 'label': 'نهاية الفترة', 'type': 'date', 'required': True, 'options': []},
         ],
         required_documents=['كشف حساب المورد']),
    dict(code='payment-status', name='استفسار عن حالة دفعة', destination_role='accountant', sla_hours=24,
         escalation_role='cs_supervisor', sort_order=20,
         description='استفسار المورد عن موعد أو حالة سداد دفعة.',
         field_schema=[
             {'key': 'invoice_number', 'label': 'رقم الفاتورة', 'type': 'text', 'required': True, 'options': []},
             {'key': 'amount', 'label': 'المبلغ (ر.س)', 'type': 'number', 'required': False, 'options': []},
         ], required_documents=[]),
    dict(code='dues-followup', name='متابعة مستحقات', destination_role='accountant', sla_hours=48,
         escalation_role='cs_supervisor', sort_order=30,
         description='مطالبة المورد بمستحقات متأخرة ومتابعتها.',
         field_schema=[
             {'key': 'invoice_number', 'label': 'رقم الفاتورة', 'type': 'text', 'required': False, 'options': []},
             {'key': 'due_amount', 'label': 'المبلغ المستحق (ر.س)', 'type': 'number', 'required': False, 'options': []},
         ], required_documents=[]),
    dict(code='general-support', name='دعم عام', destination_role='cs_agent', sla_hours=24,
         escalation_role='cs_supervisor', sort_order=40, description='أي استفسار أو طلب لا يندرج تحت نوع آخر.',
         field_schema=[], required_documents=[]),
    dict(code='meeting', name='جدولة اجتماع', destination_role='cs_supervisor', sla_hours=48,
         escalation_role='manager', sort_order=50, description='طلب لقاء مع المورد أو مع قسم المحاسبة.',
         field_schema=[
             {'key': 'preferred_date', 'label': 'التاريخ المفضل', 'type': 'date', 'required': True, 'options': []},
             {'key': 'topic', 'label': 'موضوع الاجتماع', 'type': 'textarea', 'required': True, 'options': []},
         ], required_documents=[]),
    dict(code='document-request', name='طلب مستندات', destination_role='accountant', sla_hours=24,
         escalation_role='cs_supervisor', sort_order=60, description='طلب مستند من المورد أو للمورد (إشعار دفع، شهادة...).',
         field_schema=[
             {'key': 'document_name', 'label': 'المستند المطلوب', 'type': 'text', 'required': True, 'options': []},
         ], required_documents=[]),
]


def seed(apps, schema_editor):
    ServiceType = apps.get_model('servicedesk', 'ServiceType')
    for t in TYPES:
        ServiceType.objects.get_or_create(code=t['code'], defaults=t)


class Migration(migrations.Migration):
    dependencies = [('servicedesk', '0001_initial')]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
