import datetime
import json
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.models import Notification, Role, UserProfile
from apps.suppliers.models import Supplier
from apps.whatsapp.models import SupplierConversation

from . import services
from .models import Appointment, RequestStatusHistory, ServiceRequest, ServiceRequestDocument, ServiceType
from .services import RequestError

User = get_user_model()
S = ServiceRequest.Status
RT = Role.RoleType


def make_user(username, role_type):
    role, _ = Role.objects.get_or_create(role_type=role_type, defaults={'name': f'r-{role_type}', 'is_system_role': True})
    u = User.objects.create_user(username, password='x-Pass-12345')
    UserProfile.objects.create(user=u, role=role)
    return u


class Base(TestCase):
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
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.agent = make_user('agent', RT.CS_AGENT)
        self.acc1 = make_user('acc1', RT.ACCOUNTANT)
        self.acc2 = make_user('acc2', RT.ACCOUNTANT)
        self.cfo = make_user('cfo', RT.CFO)
        self.aud = make_user('aud', RT.AUDITOR)
        self.po = make_user('po', RT.PAYMENT_OFFICER)
        self.supplier = Supplier.objects.create(name='مورد', code='S1')
        self.t_pay = ServiceType.objects.get(code='payment-status')       # مستلمها المحاسب
        self.t_meet = ServiceType.objects.get(code='meeting')              # مستلمها مشرف خدمة العملاء
        self.t_recon = ServiceType.objects.get(code='account-reconciliation')

    def make(self, stype=None, user=None, **kw):
        stype = stype or self.t_pay
        data = {'f_invoice_number': 'INV-1'}
        data.update(kw.pop('fields', {}))
        return services.create_request(user or self.agent, stype, self.supplier, kw.pop('subject', 'استفسار'),
                                       getter=data.get, **kw)


class SchemaTests(TestCase):
    def test_seeded_types(self):
        self.assertEqual(ServiceType.objects.count(), 6)
        self.assertEqual(ServiceType.objects.get(code='account-reconciliation').required_documents, ['كشف حساب المورد'])

    def test_validate_schema(self):
        ok = services.validate_schema([{'key': 'a_1', 'label': 'أ', 'type': 'select', 'options': ['x', ' y ', ''],
                                        'required': 1}])
        self.assertEqual(ok[0]['options'], ['x', 'y'])
        for bad in ([{'key': 'A', 'label': 'x'}], [{'key': '1a', 'label': 'x'}], [{'key': 'a', 'label': ''}],
                    [{'key': 'a', 'label': 'x', 'type': 'weird'}], [{'key': 'a', 'label': 'x', 'type': 'select'}],
                    [{'key': 'a', 'label': 'x'}, {'key': 'a', 'label': 'y'}], 'x', [1], {'key': 'a'}):
            with self.assertRaises(RequestError):
                services.validate_schema(bad)

    def test_validate_fields(self):
        schema = [{'key': 'n', 'label': 'رقم', 'type': 'number', 'required': True},
                  {'key': 'd', 'label': 'تاريخ', 'type': 'date', 'required': False},
                  {'key': 's', 'label': 'قائمة', 'type': 'select', 'options': ['a', 'b']},
                  {'key': 't', 'label': 'نص', 'type': 'text'}]
        get = lambda d: (lambda k: d.get(k, ''))
        cleaned, errs = services.validate_fields(schema, get({'f_n': '1,250.50', 'f_d': '2026-02-03', 'f_s': 'a', 'f_t': ' x '}))
        self.assertEqual((errs, cleaned), ([], {'n': '1250.50', 'd': '2026-02-03', 's': 'a', 't': 'x'}))
        _, errs = services.validate_fields(schema, get({}))
        self.assertEqual(len(errs), 1)
        for bad in ({'f_n': 'abc'}, {'f_n': 'NaN'}, {'f_n': '1', 'f_d': '2026-13-99'}, {'f_n': '1', 'f_s': 'zzz'}):
            self.assertTrue(services.validate_fields(schema, get(bad))[1], bad)


class CreateTests(Base):
    def test_create_sets_due_history_audit_and_notifies_destination(self):
        r = self.make()
        self.assertRegex(r.reference, r'^SR-\d{4}-\d{5}$')
        self.assertEqual(r.status, S.NEW)
        delta = r.due_at - r.created_at
        self.assertAlmostEqual(delta.total_seconds(), 24 * 3600, delta=5)
        self.assertEqual(r.data, {'invoice_number': 'INV-1'})
        self.assertEqual(r.history.count(), 1)
        self.assertTrue(AuditLog.objects.filter(entity_type='servicedesk.ServiceRequest', action='create', actor=self.agent).exists())
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'acc1', 'acc2'})

    def test_missing_required_field_and_empty_subject(self):
        with self.assertRaises(RequestError):
            services.create_request(self.agent, self.t_pay, self.supplier, 'x', getter=lambda k: '')
        with self.assertRaises(RequestError):
            self.make(subject='   ')
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_permissions_and_inactive_type(self):
        with self.assertRaises(RequestError):
            self.make(user=self.po)                  # مسؤول المدفوعات لا ينشئ
        self.t_pay.is_active = False
        self.t_pay.save()
        with self.assertRaises(RequestError):
            self.make()

    def test_create_roles_are_configurable(self):
        self.t_pay.create_roles = [RT.CS_SUPERVISOR]
        self.t_pay.save()
        with self.assertRaises(RequestError):
            self.make(user=self.agent)
        self.make(user=self.sup)

    def test_http_flow_with_dynamic_fields(self):
        self.client.force_login(self.agent)
        r = self.client.get(reverse('servicedesk:create'), {'type': self.t_pay.pk})
        self.assertIn('f_invoice_number', r.content.decode())
        resp = self.client.post(reverse('servicedesk:create'), {
            'step': 'create', 'type': self.t_pay.pk, 'supplier': self.supplier.pk, 'subject': 'متى السداد؟',
            'priority': 'high', 'f_invoice_number': 'INV-77', 'f_amount': '1500'})
        req = ServiceRequest.objects.get()
        self.assertRedirects(resp, reverse('servicedesk:detail', args=[req.pk]))
        self.assertEqual((req.data['invoice_number'], req.data['amount'], req.priority), ('INV-77', '1500', 'high'))

    def test_prefill_from_conversation(self):
        conv = SupplierConversation.objects.create(contact_number='966500000001', supplier=self.supplier, display_name='أحمد')
        self.client.force_login(self.agent)
        html = self.client.get(reverse('servicedesk:create'), {'type': self.t_pay.pk, 'conversation': conv.pk}).content.decode()
        self.assertIn('من محادثة واتساب', html)
        self.client.post(reverse('servicedesk:create'), {
            'step': 'create', 'type': self.t_pay.pk, 'conversation': conv.pk, 'subject': 'x', 'f_invoice_number': '1'})
        self.assertEqual(ServiceRequest.objects.get().conversation, conv)


class VisibilityTests(Base):
    def test_row_level_visibility(self):
        pay = self.make(self.t_pay)
        meet = self.make(self.t_meet, fields={'f_preferred_date': '2026-03-01', 'f_topic': 'مراجعة'})
        ids = lambda u: set(services.visible_requests(u).values_list('pk', flat=True))
        self.assertEqual(ids(self.acc1), {pay.pk})            # يرى ما يخص دوره فقط
        self.assertEqual(ids(self.agent), {pay.pk, meet.pk})  # منشئهما
        self.assertEqual(ids(self.cfo), {pay.pk, meet.pk})
        self.assertEqual(ids(self.aud), {pay.pk, meet.pk})
        self.assertEqual(ids(self.po), set())
        self.assertEqual(ids(make_user('agent2', RT.CS_AGENT)), {meet.pk} - {meet.pk})

    def test_assigned_request_hidden_from_peer_handler(self):
        r = self.make()
        services.claim(r.pk, self.acc1)
        self.assertEqual(set(services.visible_requests(self.acc2).values_list('pk', flat=True)), set())
        self.client.force_login(self.acc2)
        self.assertEqual(self.client.get(reverse('servicedesk:detail', args=[r.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('servicedesk:transition', args=[r.pk]), {'to': 'in_progress'}).status_code, 404)

    def test_payment_officer_has_no_module_access(self):
        self.client.force_login(self.po)
        self.assertEqual(self.client.get(reverse('servicedesk:list')).status_code, 302)

    def test_list_tabs(self):
        mine = self.make()
        services.claim(mine.pk, self.acc1)
        other = self.make()
        late = self.make()
        ServiceRequest.objects.filter(pk=late.pk).update(due_at=timezone.now() - datetime.timedelta(hours=1))
        self.client.force_login(self.acc1)
        url = reverse('servicedesk:list')
        names = lambda tab: {x.pk for x in self.client.get(url, {'tab': tab}).context['page_obj']}
        self.assertEqual(names('mine'), {mine.pk})
        self.assertEqual(names('unassigned'), {other.pk, late.pk})
        self.assertEqual(names('overdue'), {late.pk})


class ClaimAndWorkflowTests(Base):
    def test_only_one_handler_wins_and_non_handlers_blocked(self):
        r = self.make()
        services.claim(r.pk, self.acc1)
        with self.assertRaises(RequestError) as cm:
            services.claim(r.pk, self.acc2)
        self.assertIn('موظف آخر', str(cm.exception))
        with self.assertRaises(RequestError):
            services.claim(self.make().pk, self.po)

    def test_start_auto_claims(self):
        r = self.make()
        services.transition(r.pk, S.IN_PROGRESS, self.acc1)
        r.refresh_from_db()
        self.assertEqual((r.status, r.assigned_to), (S.IN_PROGRESS, self.acc1))

    def test_resolve_requires_note_and_required_documents(self):
        r = self.make(self.t_recon, fields={'f_period_start': '2026-01-01', 'f_period_end': '2026-03-31'})
        services.transition(r.pk, S.IN_PROGRESS, self.acc1)
        with self.assertRaises(RequestError):
            services.transition(r.pk, S.RESOLVED, self.acc1, resolution_note='')
        with self.assertRaises(RequestError) as cm:
            services.transition(r.pk, S.RESOLVED, self.acc1, resolution_note='تمت')
        self.assertIn('كشف حساب المورد', str(cm.exception))
        ServiceRequestDocument.objects.create(request=r, label='كشف حساب المورد', original_name='s.xlsx',
                                              file=SimpleUploadedFile('s.xlsx', b'x'))
        services.transition(r.pk, S.RESOLVED, self.acc1, resolution_note='تمت المطابقة')
        r.refresh_from_db()
        self.assertEqual((r.status, r.resolution_note), (S.RESOLVED, 'تمت المطابقة'))
        self.assertIsNotNone(r.resolved_at)
        self.assertTrue(Notification.objects.filter(recipient=self.agent, title__contains='تم حل').exists())

    def test_close_reopen_cancel_rules(self):
        r = self.make()
        services.transition(r.pk, S.IN_PROGRESS, self.acc1)
        services.transition(r.pk, S.RESOLVED, self.acc1, resolution_note='تم')
        with self.assertRaises(RequestError):
            services.transition(r.pk, S.CLOSED, self.acc2)          # ليس منشئًا
        with self.assertRaises(RequestError):
            services.transition(r.pk, S.IN_PROGRESS, self.agent, '')  # إعادة الفتح تتطلب سببًا
        services.transition(r.pk, S.IN_PROGRESS, self.agent, 'لم يُحل')
        r.refresh_from_db()
        self.assertIsNone(r.resolved_at)
        services.transition(r.pk, S.RESOLVED, self.acc1, resolution_note='ثانية')
        services.transition(r.pk, S.CLOSED, self.agent)
        with self.assertRaises(RequestError):
            services.transition(r.pk, S.IN_PROGRESS, self.sup)       # نهائي
        c = self.make()
        with self.assertRaises(RequestError):
            services.transition(c.pk, S.CANCELLED, self.agent, '')
        services.transition(c.pk, S.CANCELLED, self.agent, 'مكرر')

    def test_manual_escalation_needs_reason_and_notifies_escalation_role(self):
        r = self.make()
        services.transition(r.pk, S.IN_PROGRESS, self.acc1)
        with self.assertRaises(RequestError):
            services.transition(r.pk, S.ESCALATED, self.acc1, '')
        services.transition(r.pk, S.ESCALATED, self.acc1, 'مبلغ كبير')
        self.assertTrue(Notification.objects.filter(recipient=self.sup, title__contains='مصعَّد').exists())
        r.refresh_from_db()
        self.assertEqual(r.escalation_count, 1)

    def test_status_changes_audited_with_actor(self):
        r = self.make()
        services.transition(r.pk, S.IN_PROGRESS, self.acc1)
        log = AuditLog.objects.get(entity_type='servicedesk.ServiceRequest', action='status_change')
        self.assertEqual((log.actor, log.previous_state['status'], log.new_state['status']), (self.acc1, 'new', 'in_progress'))

    def test_assign_by_supervisor_only_to_handlers(self):
        r = self.make()
        with self.assertRaises(RequestError):
            services.assign(r.pk, self.acc2, self.agent)
        with self.assertRaises(RequestError):
            services.assign(r.pk, self.po, self.sup)
        services.assign(r.pk, self.acc2, self.sup)
        r.refresh_from_db()
        self.assertEqual(r.assigned_to, self.acc2)


class EscalationTests(Base):
    def overdue(self, **kw):
        r = self.make(**kw)
        ServiceRequest.objects.filter(pk=r.pk).update(due_at=timezone.now() - datetime.timedelta(minutes=5))
        return r

    def test_overdue_escalated_once_and_notified(self):
        r = self.overdue()
        self.assertEqual(services.escalate_overdue(), 1)
        self.assertEqual(services.escalate_overdue(), 0)          # لا تصعيد مكرر
        r.refresh_from_db()
        self.assertEqual((r.status, r.escalation_count), (S.ESCALATED, 1))
        self.assertTrue(Notification.objects.filter(recipient=self.sup, title__contains='تصعيد تلقائي').exists())
        h = r.history.last()
        self.assertEqual((h.to_status, h.changed_by), ('escalated', None))
        log = AuditLog.objects.get(entity_type='servicedesk.ServiceRequest', new_state__status='escalated')
        self.assertIsNone(log.actor)

    def test_not_escalated_when_on_time_resolved_or_closed(self):
        self.make()
        done = self.overdue()
        services.transition(done.pk, S.IN_PROGRESS, self.acc1)
        services.transition(done.pk, S.RESOLVED, self.acc1, resolution_note='ok')
        self.assertEqual(services.escalate_overdue(), 0)

    def test_returning_to_progress_resets_clock(self):
        r = self.overdue()
        services.escalate_overdue()
        services.transition(r.pk, S.IN_PROGRESS, self.acc1)
        r.refresh_from_db()
        self.assertGreater(r.due_at, timezone.now())
        self.assertEqual(services.escalate_overdue(), 0)

    def test_management_command(self):
        self.overdue()
        call_command('escalate_overdue_requests', verbosity=0)
        self.assertEqual(ServiceRequest.objects.get().status, S.ESCALATED)

    def test_is_overdue_property(self):
        r = self.overdue()
        r.refresh_from_db()
        self.assertTrue(r.is_overdue)
        r.status = S.RESOLVED
        self.assertFalse(r.is_overdue)


class DocumentsAndAppointmentsTests(Base):
    def test_upload_download_access_control(self):
        r = self.make()
        self.client.force_login(self.agent)
        self.client.post(reverse('servicedesk:document_upload', args=[r.pk]),
                         {'file': SimpleUploadedFile('a.pdf', b'%PDF'), 'label': 'كشف'})
        doc = r.documents.get()
        self.assertEqual(len(doc.sha256), 64)
        self.assertEqual(self.client.get(reverse('servicedesk:document_download', args=[r.pk, doc.pk])).status_code, 200)
        self.client.force_login(self.acc1)       # يستلم بعد الإسناد فقط... وهو مرئي لأنه من اختصاصه
        self.assertEqual(self.client.get(reverse('servicedesk:document_download', args=[r.pk, doc.pk])).status_code, 200)
        self.client.force_login(self.po)
        self.assertEqual(self.client.get(reverse('servicedesk:document_download', args=[r.pk, doc.pk])).status_code, 302)
        other = make_user('agent2', RT.CS_AGENT)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('servicedesk:document_download', args=[r.pk, doc.pk])).status_code, 404)

    def test_bad_extension_rejected_and_closed_request_locked(self):
        r = self.make()
        self.client.force_login(self.agent)
        self.client.post(reverse('servicedesk:document_upload', args=[r.pk]), {'file': SimpleUploadedFile('x.exe', b'MZ')})
        self.assertEqual(r.documents.count(), 0)
        services.transition(r.pk, S.CANCELLED, self.agent, 'x')
        self.client.post(reverse('servicedesk:document_upload', args=[r.pk]), {'file': SimpleUploadedFile('a.pdf', b'x')})
        self.assertEqual(r.documents.count(), 0)

    def test_appointments(self):
        r = self.make(self.t_meet, fields={'f_preferred_date': '2026-03-01', 'f_topic': 'مراجعة'})
        self.client.force_login(self.sup)
        self.client.post(reverse('servicedesk:appointment_add', args=[r.pk]), {
            'title': 'اجتماع مطابقة', 'scheduled_at': '2026-12-01T10:30', 'duration_minutes': '45', 'location': 'الرياض'})
        a = Appointment.objects.get()
        self.assertEqual((a.supplier, a.request, a.duration_minutes, a.created_by), (self.supplier, r, 45, self.sup))
        self.client.post(reverse('servicedesk:appointment_status', args=[r.pk, a.pk]), {'to': 'completed'})
        a.refresh_from_db()
        self.assertEqual(a.status, 'completed')
        bad = self.client.post(reverse('servicedesk:appointment_add', args=[r.pk]), {'scheduled_at': 'غير صالح'}, follow=True)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertIn('موعد غير صالح', bad.content.decode())

    def test_appointment_list_scoped_to_assignee(self):
        r = self.make(self.t_meet, fields={'f_preferred_date': '2026-03-01', 'f_topic': 'x'})
        Appointment.objects.create(supplier=self.supplier, request=r, title='لي', scheduled_at=timezone.now() + datetime.timedelta(days=1),
                                   assigned_to=self.agent, created_by=self.sup)
        Appointment.objects.create(supplier=self.supplier, request=r, title='لغيري', scheduled_at=timezone.now() + datetime.timedelta(days=1),
                                   assigned_to=self.sup, created_by=self.sup)
        self.client.force_login(self.agent)
        titles = {a.title for a in self.client.get(reverse('servicedesk:appointments')).context['appointments']}
        self.assertEqual(titles, {'لي'})
        self.client.force_login(self.cfo)
        titles = {a.title for a in self.client.get(reverse('servicedesk:appointments')).context['appointments']}
        self.assertEqual(titles, {'لي', 'لغيري'})


class TypeAdminTests(Base):
    def test_access(self):
        for user, code in ((self.cfo, 200), (make_user('mgr', RT.MANAGER), 200), (self.sup, 302), (self.acc1, 302)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('servicedesk:types')).status_code, code, user.username)

    def test_create_custom_type_with_dynamic_fields_and_use_it(self):
        self.client.force_login(self.cfo)
        schema = [{'key': 'city', 'label': 'المدينة', 'type': 'select', 'options': ['الرياض', 'جدة'], 'required': True}]
        r = self.client.post(reverse('servicedesk:type_new'), {
            'code': 'site-visit', 'name': 'زيارة موقع', 'destination_role': 'cs_agent', 'escalation_role': 'manager',
            'sla_hours': '12', 'field_schema': json.dumps(schema), 'required_documents': 'صورة الموقع\n\n',
            'create_roles': ['cs_agent'], 'is_active': 'on'})
        self.assertRedirects(r, reverse('servicedesk:types'))
        t = ServiceType.objects.get(code='site-visit')
        self.assertEqual((t.sla_hours, t.required_documents, t.field_schema[0]['options']), (12, ['صورة الموقع'], ['الرياض', 'جدة']))
        req = services.create_request(self.agent, t, self.supplier, 'زيارة', getter={'f_city': 'جدة'}.get)
        self.assertEqual(req.data, {'city': 'جدة'})
        with self.assertRaises(RequestError):
            services.create_request(self.agent, t, self.supplier, 'زيارة', getter={'f_city': 'مكة'}.get)
        self.assertTrue(AuditLog.objects.filter(entity_type='servicedesk.ServiceType', action='create').exists())

    def test_invalid_input_rejected(self):
        self.client.force_login(self.cfo)
        base = {'code': 'x', 'name': 'x', 'destination_role': 'cs_agent', 'escalation_role': 'manager', 'sla_hours': '12',
                'field_schema': '[]'}
        for patch in ({'field_schema': '[{"key": "Bad Key", "label": "x"}]'}, {'field_schema': 'not json'},
                      {'sla_hours': '0'}, {'sla_hours': 'abc'}, {'destination_role': 'hacker'}, {'code': ''},
                      {'code': 'meeting'}):
            r = self.client.post(reverse('servicedesk:type_new'), {**base, **patch})
            self.assertEqual(r.status_code, 200, patch)
        self.assertEqual(ServiceType.objects.filter(code='x').count(), 0)

    def test_script_injection_in_schema_is_escaped_on_edit_page(self):
        self.t_pay.field_schema = [{'key': 'a', 'label': '</script><script>alert(1)</script>', 'type': 'text',
                                    'required': False, 'options': []}]
        self.t_pay.save()
        self.client.force_login(self.cfo)
        html = self.client.get(reverse('servicedesk:type_edit', args=[self.t_pay.pk])).content.decode()
        self.assertNotIn('</script><script>alert(1)', html)


class IntegrationTests(Base):
    def test_whatsapp_conversation_shows_requests_and_create_button(self):
        conv = SupplierConversation.objects.create(contact_number='966500000002', supplier=self.supplier,
                                                   status='open', assigned_agent=self.agent)
        r = self.make(conversation=conv)
        self.client.force_login(self.agent)
        html = self.client.get(reverse('whatsapp_inbox:conversation', args=[conv.pk])).content.decode()
        self.assertIn(r.reference, html)
        self.assertIn('إنشاء طلب خدمة', html)

    def test_spawn_reconciliation_links_back(self):
        r = self.make(self.t_recon, fields={'f_period_start': '2026-01-01', 'f_period_end': '2026-03-31'})
        self.client.force_login(self.sup)
        html = self.client.get(reverse('servicedesk:detail', args=[r.pk])).content.decode()
        self.assertIn('فتح حالة مطابقة', html)
        page = self.client.get(reverse('reconciliation:create'), {'supplier': self.supplier.pk, 'service_request': r.pk})
        self.assertEqual(page.context['pre_supplier'], self.supplier)
        self.client.post(reverse('reconciliation:create'), {
            'supplier': self.supplier.pk, 'service_request': r.pk, 'period_start': '2026-01-01',
            'period_end': '2026-03-31', 'priority': 'normal'})
        r.refresh_from_db()
        self.assertIsNotNone(r.reconciliation_case)
        # لا يُربط طلب بحالة ثانية
        self.client.post(reverse('reconciliation:create'), {
            'supplier': self.supplier.pk, 'service_request': r.pk, 'period_start': '2026-04-01',
            'period_end': '2026-06-30', 'priority': 'normal'})
        first = r.reconciliation_case_id
        r.refresh_from_db()
        self.assertEqual(r.reconciliation_case_id, first)

    def test_dashboard_counts_requests(self):
        from apps.reconciliation import kpis
        a = self.make()
        b = self.make()
        ServiceRequest.objects.filter(pk=b.pk).update(due_at=timezone.now() - datetime.timedelta(hours=1))
        services.transition(a.pk, S.IN_PROGRESS, self.acc1)
        services.transition(a.pk, S.RESOLVED, self.acc1, resolution_note='ok')
        out = kpis.service_request_kpis('all')
        self.assertEqual((out['total'], out['open'], out['overdue'], out['resolved']), (2, 1, 1, 1))
        self.assertIsNotNone(out['avg_resolution'])
        self.client.force_login(self.cfo)
        html = self.client.get(reverse('reconciliation:executive')).content.decode()
        self.assertIn('طلبات الخدمة', html)


class InvalidDateRegressionTests(Base):
    """parse_date يرمي ValueError لتاريخ مثل 2026-13-99 فيتحول المدخل إلى 500. يجب أن يُرفض بأدب."""
    BAD = '2026-13-99'

    def test_dates_helper(self):
        from apps.core.dates import safe_parse_date, safe_parse_datetime
        self.assertIsNone(safe_parse_date(self.BAD))
        self.assertIsNone(safe_parse_date(None))
        self.assertIsNone(safe_parse_datetime(self.BAD + 'T10:00'))
        self.assertEqual(safe_parse_date(' 2026-02-03 ').isoformat(), '2026-02-03')

    def test_reconciliation_filters_and_form(self):
        self.client.force_login(self.cfo)
        r = self.client.get(reverse('reconciliation:list'), {'from': self.BAD, 'to': self.BAD})
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse('reconciliation:export_excel'), {'from': self.BAD})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse('reconciliation:create'), {
            'supplier': self.supplier.pk, 'period_start': self.BAD, 'period_end': self.BAD, 'due_date': self.BAD,
            'priority': 'normal'})
        self.assertEqual(r.status_code, 200)

    def test_service_request_date_field_and_appointment(self):
        with self.assertRaises(RequestError):
            self.make(self.t_meet, fields={'f_preferred_date': self.BAD, 'f_topic': 'x'})
        r = self.make(self.t_meet, fields={'f_preferred_date': '2026-03-01', 'f_topic': 'x'})
        self.client.force_login(self.sup)
        resp = self.client.post(reverse('servicedesk:appointment_add', args=[r.pk]),
                                {'scheduled_at': self.BAD + 'T10:00'}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)

    def test_proposal_dispatch_with_bad_payment_date(self):
        from apps.proposals import workflow as pw
        from apps.proposals.models import PaymentProposal
        from apps.branches.models import Branch
        from apps.reconciliation.models import ReconciliationCase
        case = ReconciliationCase.objects.create(
            supplier=self.supplier, period_start=datetime.date(2026, 1, 1), period_end=datetime.date(2026, 2, 1),
            created_by=self.agent, status='completed')
        p = PaymentProposal.objects.create(
            supplier=self.supplier, branch=Branch.objects.create(name='ب', code='B'), reconciliation_case=case,
            total_dues=100, proposed_amount=50, justification='x', created_by=self.acc1, status='approved')
        self.client.force_login(self.po)
        r = self.client.post(reverse('proposals:transition', args=[p.pk]),
                             {'to': 'dispatched', 'bank_reference': 'T1', 'payment_date': self.BAD}, follow=True)
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, 'approved')
