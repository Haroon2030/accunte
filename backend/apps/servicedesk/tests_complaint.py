"""
الشكاوى: يرفعها المورد من البوابة وتصل المدير المالي ومدير النظام فقط، ولا يراها غيرهما إطلاقًا.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core import live, sidebar
from apps.core.models import Notification, Role
from apps.suppliers.models import Supplier
from apps.whatsapp import bot

from . import services
from .models import ServiceRequest, ServiceType
from .services import RequestError
from .tests_portal import make_user

User = get_user_model()
RT = Role.RoleType
S = ServiceRequest.Status


class ComplaintBase(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(name='شركة الأفق', code='C1')
        self.vendor = make_user('vendor', RT.SUPPLIER, self.supplier)
        self.cfo = make_user('cfo', RT.CFO)
        self.admin = make_user('adm', RT.ADMIN)
        self.root = User.objects.create_superuser('root', password='x-Pass-12345')
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.acc = make_user('acc', RT.ACCOUNTANT)
        self.complaint = ServiceType.objects.get(code='complaint')

    def file(self, details='تأخر الصرف أكثر من شهر'):
        self.client.force_login(self.vendor)
        self.client.post(reverse('portal:new', args=[self.complaint.code]), {'subject': 'شكوى تأخير', 'details': details})
        return ServiceRequest.objects.get(service_type=self.complaint)


class SeedTests(ComplaintBase):
    def test_type_is_confidential_portal_only_and_cfo_routed(self):
        t = self.complaint
        self.assertEqual((t.confidential, t.portal_menu, t.whatsapp_menu, t.destination_role, t.is_active),
                         (True, True, False, 'cfo', True))
        self.assertNotIn('cs_supervisor', t.effective_handle_roles())

    def test_not_offered_on_whatsapp(self):
        self.assertNotIn('complaint', [x.code for x in bot.menu_types()])

    def test_shown_in_portal_as_sensitive_card(self):
        self.client.force_login(self.vendor)
        html = self.client.get(reverse('portal:home')).content.decode()
        self.assertIn('شكوى', html)
        self.assertIn('svc-card sensitive', html)


class FilingTests(ComplaintBase):
    def test_complaint_reaches_only_cfo_and_admins(self):
        Notification.objects.all().delete()
        req = self.file()
        self.assertEqual((req.supplier, req.source, req.created_by), (self.supplier, 'portal', self.vendor))
        got = set(Notification.objects.values_list('recipient__username', flat=True))
        self.assertEqual(got, {'cfo', 'adm', 'root'})

    def test_regular_requests_still_go_to_supervisors(self):
        Notification.objects.all().delete()
        self.client.force_login(self.vendor)
        self.client.post(reverse('portal:new', args=['payment-status']), {'f_invoice_number': 'I1'})
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'sup'})

    def test_vendor_follows_own_complaint(self):
        req = self.file()
        html = self.client.get(reverse('portal:detail', args=[req.pk])).content.decode()
        self.assertIn('شكوى تأخير', html)


class ConfidentialityTests(ComplaintBase):
    def setUp(self):
        super().setUp()
        self.req = self.file()

    def ids(self, user):
        return set(services.visible_requests(user).values_list('pk', flat=True))

    def test_only_cfo_and_admins_see_it(self):
        for u in (self.cfo, self.admin, self.root):
            self.assertEqual(self.ids(u), {self.req.pk}, u.username)
        for u in (self.sup, self.acc):
            self.assertEqual(self.ids(u), set(), u.username)

    def test_http_hidden_from_supervisor_and_accountant(self):
        for u in (self.sup, self.acc):
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse('servicedesk:detail', args=[self.req.pk])).status_code, 404, u.username)
            self.assertEqual(self.client.post(reverse('servicedesk:claim', args=[self.req.pk])).status_code, 404)
            listed = {r.pk for r in self.client.get(reverse('servicedesk:list'), {'tab': 'all'}).context['page_obj']}
            self.assertNotIn(self.req.pk, listed)

    def test_cfo_sees_it_in_list_and_detail(self):
        self.client.force_login(self.cfo)
        self.assertEqual(self.client.get(reverse('servicedesk:detail', args=[self.req.pk])).status_code, 200)
        listed = {r.pk for r in self.client.get(reverse('servicedesk:list'), {'tab': 'all'}).context['page_obj']}
        self.assertIn(self.req.pk, listed)

    def test_supervisor_cannot_assign_or_transition_it_even_directly(self):
        with self.assertRaises(RequestError):
            services.assign(self.req.pk, self.acc, self.sup)
        with self.assertRaises(RequestError):
            services.transition(self.req.pk, S.IN_PROGRESS, self.sup)
        with self.assertRaises(RequestError):
            services.claim(self.req.pk, self.sup)
        self.req.refresh_from_db()
        self.assertEqual((self.req.status, self.req.assigned_to), (S.NEW, None))

    def test_cfo_handles_it_to_resolution(self):
        services.transition(self.req.pk, S.IN_PROGRESS, self.cfo)
        services.transition(self.req.pk, S.RESOLVED, self.cfo, resolution_note='تواصلنا مع المورد وسُدّدت المستحقات')
        self.req.refresh_from_db()
        self.assertEqual((self.req.status, self.req.assigned_to), (S.RESOLVED, self.cfo))
        self.client.force_login(self.vendor)
        self.assertIn('سُدّدت المستحقات', self.client.get(reverse('portal:detail', args=[self.req.pk])).content.decode())

    def test_not_counted_in_supervisor_badge(self):
        self.assertNotIn('requests', live.badge_counts(self.sup, sidebar.visible_keys(self.sup)))

    def test_overdue_complaint_escalates_to_cfo_only(self):
        ServiceRequest.objects.filter(pk=self.req.pk).update(due_at='2020-01-01T00:00:00Z')
        Notification.objects.all().delete()
        services.escalate_overdue()
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'cfo'})

    def test_type_form_can_flag_other_types_confidential(self):
        self.client.force_login(self.cfo)
        t = ServiceType.objects.get(code='meeting')
        self.client.post(reverse('servicedesk:type_edit', args=[t.pk]), {
            'code': t.code, 'name': t.name, 'destination_role': 'cs_supervisor', 'escalation_role': 'cfo',
            'sla_hours': '24', 'field_schema': '[]', 'confidential': 'on', 'is_active': 'on'})
        t.refresh_from_db()
        self.assertTrue(t.confidential)
