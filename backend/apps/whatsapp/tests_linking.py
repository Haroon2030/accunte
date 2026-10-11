from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.models import Role
from apps.suppliers.models import Supplier, SupplierContact

from . import services
from .models import SupplierConversation
from .services import ConversationError
from .tests_inbox import CFG, NUMBER, make_user, upsert

RT = Role.RoleType
User = get_user_model()




@override_settings(**CFG)
class LinkSupplierTests(TestCase):
    def setUp(self):
        self.agent = make_user('agent', RT.CS_SUPERVISOR)
        self.admin = make_user('adm', RT.ADMIN)
        self.cfo = make_user('cfo', RT.CFO)
        self.conv = SupplierConversation.objects.create(contact_number=NUMBER, display_name='شركة الأفق', status='open',
                                                        assigned_agent=self.agent)
        self.supplier = Supplier.objects.create(name='الأفق للتوريدات', code='S-1')

    def link(self, user, **data):
        self.client.force_login(user)
        return self.client.post(reverse('whatsapp_inbox:link_supplier', args=[self.conv.pk]), data, follow=True)







    def test_search_json_finds_supplier_by_name_and_code(self):
        self.client.force_login(self.agent)
        for q in ('الأفق', 'S-1'):
            data = self.client.get(reverse('suppliers:search'), {'q': q}).json()['results']
            self.assertEqual([r['code'] for r in data], ['S-1'], q)


@override_settings(**CFG)
class CreateSupplierFromConversationTests(TestCase):
    def setUp(self):
        self.agent = make_user('agent', RT.CS_SUPERVISOR)
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.admin = make_user('adm', RT.ADMIN)
        self.cfo = make_user('cfo', RT.CFO)
        self.conv = SupplierConversation.objects.create(contact_number=NUMBER, display_name='شركة الأفق', status='new')

    def create(self, user, **data):
        services.claim(self.conv.pk, user) if user in (self.agent,) else None
        return services.create_supplier_from_conversation(self.conv.pk, user, data.get('name', 'شركة الأفق'),
                                                          data.get('code', ''), data.get('tax_number', ''))

    def test_creates_supplier_contact_link_and_audit(self):
        s = self.create(self.admin)
        self.conv.refresh_from_db()
        self.assertEqual((s.name, self.conv.supplier), ('شركة الأفق', s))
        self.assertTrue(s.code.startswith('WA-'))
        self.assertEqual(SupplierContact.objects.get(supplier=s).phone, NUMBER)
        self.assertEqual(services.match_supplier(NUMBER)[0], s)
        self.assertTrue(AuditLog.objects.filter(action='create', entity_type='suppliers.Supplier', actor=self.admin).exists())
        self.assertTrue(AuditLog.objects.filter(entity_type='whatsapp.Conversation', reason='ربط المحادثة بمورد').exists())

    def test_roles(self):
        with self.assertRaises(ConversationError):                    # مشرف الدعم يربط فقط
            self.create(self.agent)
        with self.assertRaises(ConversationError):
            services.create_supplier_from_conversation(self.conv.pk, self.sup, 'x')    # ولا يدير الموردين
        self.assertEqual(Supplier.objects.count(), 0)
        self.create(self.cfo)                                          # المدير المالي سوبر أدمن: يجمع الصلاحيتين مثل مدير النظام
        self.assertEqual(Supplier.objects.count(), 1)

    def test_validation_and_duplicates(self):
        for kw in ({'name': '  '}, {'tax_number': '123'}, {'tax_number': 'abcdefghijklmno'}):
            with self.assertRaises(ConversationError):
                self.create(self.admin, **kw)
        Supplier.objects.create(name='موجود', code='DUP', tax_number='300000000000003')
        with self.assertRaises(ConversationError):
            self.create(self.admin, code='DUP')
        with self.assertRaises(ConversationError):
            self.create(self.admin, tax_number='300000000000003')
        self.assertEqual(Supplier.objects.count(), 1)                  # لا شيء أُنشئ من المحاولات الفاشلة
        self.assertFalse(SupplierContact.objects.exists())

    def test_auto_code_is_unique(self):
        # ثلاثة أرقام تشترك في آخر 6 خانات: الكود التلقائي يعتمد عليها فلا بد من فرادة
        first = self.create(self.admin)
        codes = [first.code]
        for n in ('966521234567', '966531234567'):
            conv = SupplierConversation.objects.create(contact_number=n)
            codes.append(services.create_supplier_from_conversation(conv.pk, self.admin, f'مورد {n}').code)
        self.assertEqual(len(set(codes)), 3, codes)
        self.assertEqual(codes[0], 'WA-234567')
        self.assertEqual(codes[1:], ['WA-234567-2', 'WA-234567-3'])


