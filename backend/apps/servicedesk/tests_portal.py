"""
بوابة الموردين: حساب المورد يرى الخدمات ويطلبها ويتابع طلباته فقط، وكل ما عداها مغلق أمامه.
"""
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.core.models import Notification, Role, UserProfile
from apps.suppliers.models import Supplier

from . import services
from .models import ServiceRequest, ServiceRequestDocument, ServiceType
from .services import RequestError

User = get_user_model()
RT = Role.RoleType


def make_user(username, role_type, supplier=None):
    role, _ = Role.objects.get_or_create(role_type=role_type, defaults={'name': f'r-{role_type}', 'is_system_role': True})
    u = User.objects.create_user(username, password='x-Pass-12345')
    UserProfile.objects.create(user=u, role=role, supplier=supplier)
    return u


class PortalBase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp()
        ServiceRequestDocument._meta.get_field('file').storage = FileSystemStorage(location=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.s1 = Supplier.objects.create(name='شركة الأفق', code='P1')
        self.s2 = Supplier.objects.create(name='شركة النور', code='P2')
        self.vendor = make_user('vendor1', RT.SUPPLIER, self.s1)
        self.other = make_user('vendor2', RT.SUPPLIER, self.s2)
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.acc = make_user('acc', RT.ACCOUNTANT)
        self.pay = ServiceType.objects.get(code='payment-status')
        self.client.force_login(self.vendor)

    def order(self, stype=None, **post):
        stype = stype or self.pay
        data = {'subject': 'استفسار', 'details': 'متى الصرف؟', 'f_invoice_number': 'INV-9'}
        data.update(post)
        return self.client.post(reverse('portal:new', args=[stype.code]), data)


class HomeAndServicesTests(PortalBase):
    def test_login_lands_on_portal(self):
        resp = self.client.get('/', follow=True)
        self.assertEqual(resp.redirect_chain[-1][0], '/portal/')
        self.assertContains(resp, 'شركة الأفق')

    def test_home_lists_active_portal_services_only(self):
        ServiceType.objects.filter(code='meeting').update(portal_menu=False)
        ServiceType.objects.filter(code='dues-followup').update(is_active=False)
        html = self.client.get(reverse('portal:home')).content.decode()
        self.assertIn(self.pay.name, html)
        self.assertNotIn(ServiceType.objects.get(code='meeting').name, html)
        self.assertNotIn(ServiceType.objects.get(code='dues-followup').name, html)

    @override_settings(WHATSAPP_SUPPORT_NUMBER='+966 50 123 4567')
    def test_whatsapp_chat_is_one_of_the_services(self):
        html = self.client.get(reverse('portal:home')).content.decode()
        self.assertIn('https://wa.me/966501234567', html)
        self.assertIn('التحدث عبر واتساب', html)

    @override_settings(WHATSAPP_SUPPORT_NUMBER='', WHATSAPP_ENABLED=False)
    def test_live_chat_card_always_listed_whatsapp_card_only_with_number(self):
        html = self.client.get(reverse('portal:home')).content.decode()
        self.assertIn('دردشة مباشرة مع الدعم', html)
        self.assertNotIn('wa.me', html)

    @override_settings(WHATSAPP_SUPPORT_NUMBER='', WHATSAPP_ENABLED=True, EVOLUTION_API_URL='http://evo.test',
                       EVOLUTION_API_KEY='k', EVOLUTION_INSTANCE='hr')
    def test_number_falls_back_to_connected_instance(self):
        from django.core.cache import cache
        cache.delete('wa_support_number')
        with mock.patch('apps.whatsapp.client.instance_info', return_value={'number': '966555000111', 'name': 'x'}) as info:
            html = self.client.get(reverse('portal:home')).content.decode()
            self.client.get(reverse('portal:home'))
        self.assertIn('https://wa.me/966555000111', html)
        info.assert_called_once()                       # الثاني من الذاكرة المؤقتة
        cache.delete('wa_support_number')

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('portal:home')).status_code, 302)

    def test_staff_cannot_use_portal(self):
        self.client.force_login(self.sup)
        self.assertEqual(self.client.get(reverse('portal:home')).status_code, 302)

    def test_unlinked_supplier_account_is_refused(self):
        lone = make_user('lone', RT.SUPPLIER)
        self.client.force_login(lone)
        self.assertEqual(self.client.get(reverse('portal:home')).status_code, 403)


class OrderTests(PortalBase):
    def test_order_creates_request_for_own_supplier_and_notifies_supervisors(self):
        Notification.objects.all().delete()
        resp = self.order()
        req = ServiceRequest.objects.get()
        self.assertRedirects(resp, reverse('portal:detail', args=[req.pk]))
        self.assertEqual((req.supplier, req.source, req.created_by, req.service_type), (self.s1, 'portal', self.vendor, self.pay))
        self.assertEqual(req.data, {'invoice_number': 'INV-9'})
        self.assertEqual(req.history.count(), 1)
        self.assertTrue(AuditLog.objects.filter(entity_type='servicedesk.ServiceRequest', action='create', actor=self.vendor).exists())
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'sup'})

    def test_supplier_cannot_choose_another_supplier(self):
        self.order(supplier=self.s2.pk)
        self.assertEqual(ServiceRequest.objects.get().supplier, self.s1)

    def test_missing_required_field_shows_error_and_creates_nothing(self):
        resp = self.order(f_invoice_number='')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ServiceRequest.objects.count(), 0)
        self.assertTrue(resp.context['errors'])

    def test_blank_subject_defaults_to_type_name(self):
        self.order(subject='')
        self.assertEqual(ServiceRequest.objects.get().subject, self.pay.name)

    def test_hidden_or_inactive_service_cannot_be_ordered(self):
        ServiceType.objects.filter(pk=self.pay.pk).update(portal_menu=False)
        self.assertEqual(self.order().status_code, 404)
        ServiceType.objects.filter(pk=self.pay.pk).update(portal_menu=True, is_active=False)
        self.assertEqual(self.order().status_code, 404)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_service_layer_guards_even_without_the_view(self):
        with self.assertRaises(RequestError):
            services.create_from_portal(make_user('lone', RT.SUPPLIER), self.pay, 'x')
        ServiceType.objects.filter(pk=self.pay.pk).update(portal_menu=False)
        self.pay.refresh_from_db()
        with self.assertRaises(RequestError):
            services.create_from_portal(self.vendor, self.pay, 'x')

    def test_accountant_destination_requests_are_distributed_by_supervisor(self):
        self.order()
        req = ServiceRequest.objects.get()
        self.assertEqual(set(services.visible_requests(self.acc)), set())       # لا يصل المطابق قبل الإسناد
        services.assign(req.pk, self.acc, self.sup)
        self.assertEqual(set(services.visible_requests(self.acc)), {req})


class IsolationTests(PortalBase):
    def test_supplier_sees_only_own_requests(self):
        self.order()
        mine = ServiceRequest.objects.get()
        self.client.force_login(self.other)
        self.order()
        theirs = ServiceRequest.objects.exclude(pk=mine.pk).get()
        self.assertEqual(self.client.get(reverse('portal:detail', args=[mine.pk])).status_code, 404)
        self.assertEqual({r.pk for r in self.client.get(reverse('portal:list')).context['requests']}, {theirs.pk})
        self.client.force_login(self.vendor)
        self.assertEqual(self.client.get(reverse('portal:detail', args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('portal:detail', args=[mine.pk])).status_code, 200)

    def test_detail_hides_internal_reasons(self):
        self.order()
        req = ServiceRequest.objects.get()
        services.assign(req.pk, self.acc, self.sup)
        services.transition(req.pk, 'in_progress', self.acc)
        services.transition(req.pk, 'escalated', self.acc, 'ملاحظة داخلية سرية')
        html = self.client.get(reverse('portal:detail', args=[req.pk])).content.decode()
        self.assertNotIn('ملاحظة داخلية سرية', html)

    def test_guard_blocks_every_staff_area(self):
        for url in ('/service-requests/', '/inbox/', '/suppliers/', '/reconciliation/', '/proposals/', '/users/',
                    '/audit/', '/live/badges/', '/api/', '/admin/', '/branches/', '/payments/'):
            resp = self.client.get(url, HTTP_ACCEPT='text/html')
            self.assertEqual((resp.status_code, resp['Location'] if resp.status_code == 302 else ''),
                             (302, '/portal/'), url)

    def test_guard_forbids_non_page_requests_and_posts(self):
        self.assertEqual(self.client.get('/live/badges/', HTTP_ACCEPT='application/json').status_code, 403)
        self.assertEqual(self.client.post('/service-requests/create/', {}).status_code, 403)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_guard_allows_portal_and_logout(self):
        self.assertEqual(self.client.get('/portal/').status_code, 200)
        self.assertEqual(self.client.get('/auth/logout/').status_code, 302)

    def test_guard_does_not_affect_staff(self):
        self.client.force_login(self.sup)
        self.assertEqual(self.client.get(reverse('servicedesk:list')).status_code, 200)

    def test_supplier_role_is_not_offered_as_handler(self):
        self.client.force_login(make_user('boss', RT.CFO))
        roles = [v for v, _ in self.client.get(reverse('servicedesk:type_new')).context['roles']]
        self.assertNotIn('supplier', roles)


class UserAdminTests(PortalBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('root', password='x-Pass-12345')
        self.client.force_login(self.admin)
        self.role = Role.objects.get(role_type=RT.SUPPLIER)

    def post(self, **kw):
        data = {'username': 'newvendor', 'password': 'x-Pass-12345', 'is_active': 'on', 'role': self.role.pk}
        data.update(kw)
        return self.client.post(reverse('users:create'), data)

    def test_supplier_account_requires_valid_code_and_links(self):
        self.post(supplier_code='NOPE')
        self.assertFalse(User.objects.filter(username='newvendor').exists())
        self.post(supplier_code='P2')
        self.assertEqual(User.objects.get(username='newvendor').profile.supplier, self.s2)

    def test_non_supplier_roles_never_keep_a_supplier(self):
        acc_role = Role.objects.get(role_type=RT.ACCOUNTANT)
        self.post(role=acc_role.pk, supplier_code='P1')
        self.assertIsNone(User.objects.get(username='newvendor').profile.supplier)

    def test_seeded_supplier_role_exists(self):
        self.assertTrue(Role.objects.filter(role_type='supplier').exists())


class NoSupplierUploadTests(PortalBase):
    """المورد لا يرفع ملفات من البوابة؛ يستلم فقط ما يشاركه الموظف معه."""

    def pdf(self, name='kashf.pdf', data=b'%PDF-1.4 test'):
        return SimpleUploadedFile(name, data, content_type='application/pdf')

    def test_no_portal_form_has_a_file_input(self):
        for t in ServiceType.objects.filter(is_active=True, portal_menu=True):
            html = self.client.get(reverse('portal:new', args=[t.code])).content.decode()
            self.assertNotIn('type="file"', html, t.code)
            self.assertNotIn('multipart/form-data', html, t.code)

    def test_files_posted_anyway_are_ignored(self):
        self.order(files=[self.pdf(), self.pdf('b.pdf')])
        req = ServiceRequest.objects.get()
        self.assertEqual(req.documents.count(), 0)
        self.assertEqual(ServiceRequestDocument.objects.count(), 0)

    def test_supplier_downloads_only_files_shared_with_him(self):
        self.order()
        req = ServiceRequest.objects.get()
        services.assign(req.pk, self.acc, self.sup)
        self.client.force_login(self.acc)
        self.client.post(reverse('servicedesk:document_upload', args=[req.pk]), {'file': self.pdf('shared.pdf'), 'share': 'on'})
        self.client.post(reverse('servicedesk:document_upload', args=[req.pk]), {'file': self.pdf('internal.pdf')})
        shared = req.documents.get(original_name='shared.pdf')
        internal = req.documents.get(original_name='internal.pdf')
        self.client.force_login(self.vendor)
        page = self.client.get(reverse('portal:detail', args=[req.pk])).content.decode()
        self.assertIn('shared.pdf', page)
        self.assertNotIn('internal.pdf', page)
        resp = self.client.get(reverse('portal:document', args=[req.pk, shared.pk]))
        self.assertEqual(b''.join(resp.streaming_content), b'%PDF-1.4 test')
        self.assertEqual(self.client.get(reverse('portal:document', args=[req.pk, internal.pk])).status_code, 404)
        self.client.force_login(self.other)                                  # مورد آخر
        self.assertEqual(self.client.get(reverse('portal:document', args=[req.pk, shared.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('portal:document', args=[req.pk, shared.pk])).status_code, 302)

    def test_complaint_files_stay_confidential(self):
        self.order(ServiceType.objects.get(code='complaint'))
        req = ServiceRequest.objects.get()
        cfo = make_user('boss', RT.CFO)
        self.client.force_login(cfo)
        self.client.post(reverse('servicedesk:document_upload', args=[req.pk]), {'file': self.pdf('proof.pdf')})
        doc = req.documents.get()
        self.assertEqual(self.client.get(reverse('servicedesk:document_download', args=[req.pk, doc.pk])).status_code, 200)
        self.client.force_login(self.sup)
        self.assertEqual(self.client.get(reverse('servicedesk:document_download', args=[req.pk, doc.pk])).status_code, 404)


class WhatsAppHeaderIconTests(PortalBase):
    @override_settings(WHATSAPP_SUPPORT_NUMBER='+966 50 123 4567')
    def test_icon_on_every_portal_page_links_to_the_account(self):
        self.order()
        req = ServiceRequest.objects.get()
        for url in (reverse('portal:home'), reverse('portal:list'), reverse('portal:detail', args=[req.pk]),
                    reverse('portal:chat'), reverse('portal:new', args=['payment-status'])):
            html = self.client.get(url).content.decode()
            self.assertIn('class="wa-icon"', html, url)
            self.assertIn('href="https://wa.me/966501234567', html, url)

    @override_settings(WHATSAPP_SUPPORT_NUMBER='', WHATSAPP_ENABLED=False)
    def test_no_icon_without_a_number(self):
        for url in (reverse('portal:home'), reverse('portal:chat')):
            self.assertNotIn('wa-icon" ', self.client.get(url).content.decode().replace('.wa-icon {', ''))

    @override_settings(WHATSAPP_SUPPORT_NUMBER='966501234567')
    def test_staff_pages_never_get_the_portal_context(self):
        from apps.servicedesk.portal import wa_context
        from django.test import RequestFactory
        req = RequestFactory().get('/service-requests/')
        req.user = self.sup
        self.assertEqual(wa_context(req), {})
        req = RequestFactory().get('/portal/')
        req.user = self.sup
        self.assertEqual(wa_context(req), {})                                # موظف على مسار البوابة: لا شيء


class AccountStatementTests(PortalBase):
    """«طلب كشف حساب»: المورد يحدد الفترة، والمطابق يرفع الكشف ويشاركه، والمورد ينزّله من البوابة."""

    def setUp(self):
        super().setUp()
        self.t = ServiceType.objects.get(code='account-statement')

    def order_statement(self, **kw):
        data = {'f_period_start': '2026-01-01', 'f_period_end': '2026-03-31', 'f_format': 'PDF'}
        data.update(kw)
        return self.client.post(reverse('portal:new', args=[self.t.code]), data)

    def pdf(self, name='statement.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.4 statement', content_type='application/pdf')

    def test_type_converted_from_document_request(self):
        self.assertEqual(self.t.name, 'طلب كشف حساب')
        self.assertFalse(ServiceType.objects.filter(code='document-request').exists())
        self.assertEqual([f['key'] for f in self.t.field_schema], ['period_start', 'period_end', 'format'])
        self.assertEqual(self.t.required_documents, ['كشف حساب المورد'])

    def test_period_is_required_and_ordered(self):
        self.order_statement(f_period_start='')
        self.order_statement(f_period_start='2026-05-01', f_period_end='2026-01-01')
        self.assertEqual(ServiceRequest.objects.count(), 0)
        self.order_statement()
        self.assertEqual(ServiceRequest.objects.get().data['period_start'], '2026-01-01')

    def deliver(self, share=True):
        self.order_statement()
        req = ServiceRequest.objects.get()
        services.assign(req.pk, self.acc, self.sup)
        self.client.force_login(self.acc)
        services.transition(req.pk, 'in_progress', self.acc)
        self.client.post(reverse('servicedesk:document_upload', args=[req.pk]),
                         {'file': self.pdf(), 'label': 'كشف حساب المورد', **({'share': 'on'} if share else {})})
        return req

    def test_cannot_resolve_until_statement_is_shared_with_supplier(self):
        req = self.deliver(share=False)
        with self.assertRaises(RequestError) as cm:
            services.transition(req.pk, 'resolved', self.acc, resolution_note='تم')
        self.assertIn('شارك المستند', str(cm.exception))

    def test_full_flow_supplier_downloads_the_statement(self):
        req = self.deliver()
        services.transition(req.pk, 'resolved', self.acc, resolution_note='أُرسل الكشف')
        doc = req.documents.get()
        self.assertTrue(doc.shared_with_supplier)
        self.client.force_login(self.vendor)
        html = self.client.get(reverse('portal:detail', args=[req.pk])).content.decode()
        self.assertIn('statement.pdf', html)
        self.assertIn('أُرسل الكشف', html)
        resp = self.client.get(reverse('portal:document', args=[req.pk, doc.pk]))
        self.assertEqual(b''.join(resp.streaming_content), b'%PDF-1.4 statement')

    def test_internal_documents_are_never_shown_or_downloadable(self):
        req = self.deliver(share=False)
        doc = req.documents.get()
        self.assertFalse(doc.shared_with_supplier)
        self.client.force_login(self.vendor)
        self.assertNotContains(self.client.get(reverse('portal:detail', args=[req.pk])), 'statement.pdf')
        self.assertEqual(self.client.get(reverse('portal:document', args=[req.pk, doc.pk])).status_code, 404)

    def test_staff_form_offers_share_checkbox_only_for_portal_requests(self):
        self.order_statement()
        portal_req = ServiceRequest.objects.get()
        services.assign(portal_req.pk, self.acc, self.sup)
        self.client.force_login(self.acc)
        self.assertContains(self.client.get(reverse('servicedesk:detail', args=[portal_req.pk])), 'name="share"')
        staff_req = services.create_request(self.sup, self.pay, self.supplier_obj(), 'x', getter={'f_invoice_number': '1'}.get)
        services.assign(staff_req.pk, self.acc, self.sup)
        self.assertNotContains(self.client.get(reverse('servicedesk:detail', args=[staff_req.pk])), 'name="share"')

    def supplier_obj(self):
        return self.s1

    def test_share_flag_is_ignored_for_non_portal_requests(self):
        staff_req = services.create_request(self.sup, self.pay, self.s1, 'x', getter={'f_invoice_number': '1'}.get)
        services.assign(staff_req.pk, self.acc, self.sup)
        self.client.force_login(self.acc)
        self.client.post(reverse('servicedesk:document_upload', args=[staff_req.pk]), {'file': self.pdf(), 'share': 'on'})
        self.assertFalse(staff_req.documents.get().shared_with_supplier)

