from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.models import Role
from apps.suppliers.models import Supplier, SupplierContact

from . import services
from .inbox_views import _agents
from .models import SupplierConversation
from .services import ConversationError
from .tests_inbox import CFG, NUMBER, make_user, upsert

RT = Role.RoleType
User = get_user_model()


@override_settings(**CFG)
class AgentsListTests(TestCase):
    """قائمة «إسناد إلى...» كانت فارغة لأنها تستثني مدير النظام والمدير، بينما services.assign يقبلهما."""

    def test_agents_list_matches_who_assign_accepts(self):
        users = {r: make_user(f'u_{r}', r) for r in (RT.ADMIN, RT.CS_SUPERVISOR, RT.CS_AGENT, RT.MANAGER, RT.ACCOUNTANT,
                                                    RT.CFO, RT.AUDITOR, RT.PAYMENT_OFFICER)}
        root = User.objects.create_superuser('root', password='x-Pass-12345')          # بلا دور (مثل أول مدير في الإنتاج)
        inactive = make_user('gone', RT.CS_AGENT)
        inactive.is_active = False
        inactive.save()
        names = {u.username for u in _agents()}
        self.assertEqual(names, {'u_admin', 'u_cs_supervisor', 'u_cs_agent', 'u_manager', 'root'})
        conv = SupplierConversation.objects.create(contact_number=NUMBER, status='new')
        sup = users[RT.CS_SUPERVISOR]
        for u in _agents():                          # كل من يظهر في القائمة يقبله الإسناد فعلًا
            services.assign(conv.pk, u, sup)
        for r in (RT.ACCOUNTANT, RT.CFO, RT.AUDITOR, RT.PAYMENT_OFFICER):                # ومن لا يظهر يرفضه الإسناد
            with self.assertRaises(ConversationError):
                services.assign(conv.pk, users[r], sup)
        self.assertIsNotNone(root)

    def test_only_admin_in_production_can_be_assigned_and_page_shows_them(self):
        admin = User.objects.create_superuser('1', password='x-Pass-12345')
        conv = SupplierConversation.objects.create(contact_number=NUMBER, status='new')
        self.client.force_login(admin)
        html = self.client.get(reverse('whatsapp_inbox:conversation', args=[conv.pk])).content.decode()
        self.assertIn('>1 (أنا)</option>', html)
        self.client.post(reverse('whatsapp_inbox:assign', args=[conv.pk]), {'agent': admin.pk})
        conv.refresh_from_db()
        self.assertEqual(conv.assigned_agent, admin)


@override_settings(**CFG)
class LinkSupplierTests(TestCase):
    def setUp(self):
        self.agent = make_user('agent', RT.CS_AGENT)
        self.admin = make_user('adm', RT.ADMIN)
        self.cfo = make_user('cfo', RT.CFO)
        self.conv = SupplierConversation.objects.create(contact_number=NUMBER, display_name='شركة الأفق', status='open',
                                                        assigned_agent=self.agent)
        self.supplier = Supplier.objects.create(name='الأفق للتوريدات', code='S-1')

    def link(self, user, **data):
        self.client.force_login(user)
        return self.client.post(reverse('whatsapp_inbox:link_supplier', args=[self.conv.pk]), data, follow=True)

    def test_link_by_id_adds_number_as_approved_primary_contact(self):
        self.link(self.agent, supplier=self.supplier.pk)
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.supplier, self.supplier)
        c = SupplierContact.objects.get(supplier=self.supplier)
        self.assertEqual((c.phone, c.name, c.is_primary, c.is_approved), (NUMBER, 'شركة الأفق', True, True))
        self.assertEqual(self.conv.contact, c)
        self.link(self.agent, supplier=self.supplier.pk)                        # لا تكرار عند إعادة الربط
        self.assertEqual(SupplierContact.objects.filter(supplier=self.supplier).count(), 1)

    def test_existing_primary_is_kept(self):
        SupplierContact.objects.create(supplier=self.supplier, phone='966511111111', is_primary=True)
        self.link(self.agent, supplier=self.supplier.pk)
        self.assertEqual(SupplierContact.objects.filter(supplier=self.supplier, is_primary=True).count(), 1)

    def test_future_messages_from_number_match_supplier_automatically(self):
        self.link(self.agent, supplier=self.supplier.pk)
        self.assertEqual(services.match_supplier(NUMBER)[0], self.supplier)

    def test_link_by_code_still_works_and_unknown_is_rejected(self):
        self.link(self.agent, supplier_code='S-1')
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.supplier, self.supplier)
        r = self.link(self.agent, supplier='99999')
        self.assertIn('لا يوجد مورد مطابق', r.content.decode())
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.supplier, self.supplier)                      # لم يتغير

    def test_unlink(self):
        self.link(self.agent, supplier=self.supplier.pk)
        r = self.link(self.agent)
        self.assertIn('تم فك ربط المورد', r.content.decode())
        self.conv.refresh_from_db()
        self.assertIsNone(self.conv.supplier)

    def test_peer_cannot_link_someone_elses_conversation(self):
        other = make_user('agent2', RT.CS_AGENT)
        self.link(other, supplier=self.supplier.pk)
        self.conv.refresh_from_db()
        self.assertIsNone(self.conv.supplier)

    def test_search_json_finds_supplier_by_name_and_code(self):
        self.client.force_login(self.agent)
        for q in ('الأفق', 'S-1'):
            data = self.client.get(reverse('suppliers:search'), {'q': q}).json()['results']
            self.assertEqual([r['code'] for r in data], ['S-1'], q)


@override_settings(**CFG)
class CreateSupplierFromConversationTests(TestCase):
    def setUp(self):
        self.agent = make_user('agent', RT.CS_AGENT)
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.admin = make_user('adm', RT.ADMIN)
        self.mgr = make_user('mgr', RT.MANAGER)
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
        with self.assertRaises(ConversationError):                    # موظف خدمة العملاء يربط فقط
            self.create(self.agent)
        with self.assertRaises(ConversationError):
            services.create_supplier_from_conversation(self.conv.pk, self.sup, 'x')    # المشرف لا يدير الموردين
        self.assertEqual(Supplier.objects.count(), 0)
        self.create(self.mgr)                                          # المدير يستطيع
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

    def test_http_flow_and_form_visibility(self):
        self.client.force_login(self.admin)
        url = reverse('whatsapp_inbox:conversation', args=[self.conv.pk])
        self.assertIn('إنشاء وربط', self.client.get(url).content.decode())
        r = self.client.post(reverse('whatsapp_inbox:create_supplier', args=[self.conv.pk]),
                             {'name': 'شركة الأفق', 'tax_number': '300000000000003'}, follow=True)
        self.assertIn('تم إنشاء المورد وربطه بالمحادثة', r.content.decode())
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.supplier.tax_number, '300000000000003')
        self.assertNotIn('إنشاء وربط', r.content.decode())    # لا يظهر بعد الربط
        self.client.force_login(self.sup)
        self.assertNotIn('إنشاء وربط',
                         self.client.get(reverse('whatsapp_inbox:conversation', args=[
                             SupplierConversation.objects.create(contact_number='966500000321').pk])).content.decode())

    def test_get_not_allowed(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('whatsapp_inbox:create_supplier', args=[self.conv.pk])).status_code, 405)
