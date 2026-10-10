"""
حراسة قابلية النقل بين قواعد البيانات.

MySQL/MariaDB (استضافة هوستنجر) لا تدعم الفهارس المشروطة (partial / UniqueConstraint(condition=...)).
Django يتجاهلها بصمت هناك فتضيع ضمانات التفرّد التي تنجح اختباراتها على SQLite. لذلك نُلزم باستعمال
أعمدة ظل تقبل NULL مع قيد فريد عادي بدل الشرط.
"""
from django.apps import apps
from django.db.models import UniqueConstraint
from django.test import TestCase

from apps.suppliers.models import Supplier
from apps.whatsapp.models import ConversationMessage, SupplierConversation


class NoPartialIndexesTests(TestCase):
    def test_no_conditional_constraints_or_indexes(self):
        offenders = []
        for model in apps.get_models():
            if not model.__module__.startswith('apps.'):
                continue
            for c in model._meta.constraints:
                # CheckConstraint مدعوم (MySQL 8.0.16+ / MariaDB 10.2+). المشكلة في الفرادة المشروطة فقط
                if isinstance(c, UniqueConstraint) and c.condition is not None:
                    offenders.append(f'{model.__name__}.{c.name}')
            for i in model._meta.indexes:
                if getattr(i, 'condition', None) is not None:
                    offenders.append(f'{model.__name__}.{i.name}')
        self.assertEqual(offenders, [], 'قيود مشروطة لا تعمل على MySQL')

    def test_unique_columns_accept_null_for_empty_values(self):
        for model, field in ((Supplier, 'tax_key'), (Supplier, 'financial_system_id'),
                             (ConversationMessage, 'wa_message_id')):
            f = model._meta.get_field(field)
            self.assertTrue(f.unique and f.null, f'{model.__name__}.{field}')

    def test_empty_values_are_stored_as_null_and_do_not_collide(self):
        a = Supplier.objects.create(name='a', code='1', tax_number='', financial_system_id='')
        b = Supplier.objects.create(name='b', code='2', tax_number='  ', financial_system_id=' ')
        for s in (a, b):
            s.refresh_from_db()
            self.assertIsNone(s.tax_key)
            self.assertIsNone(s.financial_system_id)
        c = SupplierConversation.objects.create(contact_number='966500000000')
        ConversationMessage.objects.create(conversation=c, direction='out', body='1')
        ConversationMessage.objects.create(conversation=c, direction='out', body='2')
        self.assertEqual(ConversationMessage.objects.filter(wa_message_id__isnull=True).count(), 2)
