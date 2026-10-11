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
        self.agent = make_user('agent', RT.ACCOUNTANT)      # موظف عادي: ينشئ طلبات ولا يوزّع
        self.acc1 = make_user('acc1', RT.ACCOUNTANT)
        self.acc2 = make_user('acc2', RT.ACCOUNTANT)
        self.cfo = make_user('cfo', RT.CFO)
        self.po = make_user('po', RT.SUPPLIER)              # حساب بلا أي وصول لوحدة الطلبات
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
        self.assertEqual(ServiceType.objects.count(), 7)
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
        self.assertEqual(set(Notification.objects.values_list('recipient__username', flat=True)), {'sup'})   # المشرف يوزّع

    def test_missing_required_field_and_empty_subject(self):
        with self.assertRaises(RequestError):
            services.create_request(self.agent, self.t_pay, self.supplier, 'x', getter=lambda k: '')
        with self.assertRaises(RequestError):
            self.make(subject='   ')
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_permissions_and_inactive_type(self):
        with self.assertRaises(RequestError):
            self.make(user=self.po)                  # حساب المورد لا ينشئ من لوحة الموظفين
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




class VisibilityTests(Base):
    def test_row_level_visibility(self):
        pay = self.make(self.t_pay)
        meet = self.make(self.t_meet, fields={'f_preferred_date': '2026-03-01', 'f_topic': 'مراجعة'})
        ids = lambda u: set(services.visible_requests(u).values_list('pk', flat=True))
        self.assertEqual(ids(self.acc1), set())               # المطابق لا يرى إلا ما أُسند إليه
        services.assign(pay.pk, self.acc1, self.sup)
        self.assertEqual(ids(self.acc1), {pay.pk})
        self.assertEqual(ids(self.agent), {pay.pk, meet.pk})  # منشئهما
        self.assertEqual(ids(self.cfo), {pay.pk, meet.pk})
        self.assertEqual(ids(self.sup), {pay.pk, meet.pk})
        self.assertEqual(ids(self.po), set())
        self.assertEqual(ids(make_user('other', RT.ACCOUNTANT)), set())





class ClaimAndWorkflowTests(Base):
    def test_only_one_handler_wins_and_non_handlers_blocked(self):
        general = ServiceType.objects.get(code='general-support')           # مستلمها مشرف الدعم
        sup2 = make_user('sup2', RT.CS_SUPERVISOR)
        r = self.make(general)
        services.claim(r.pk, self.sup)
        with self.assertRaises(RequestError) as cm:
            services.claim(r.pk, sup2)
        self.assertIn('موظف آخر', str(cm.exception))
        with self.assertRaises(RequestError):
            services.claim(self.make(general).pk, self.po)

    def test_accountant_cannot_self_claim_or_work_unassigned(self):
        r = self.make()
        with self.assertRaises(RequestError) as cm:
            services.claim(r.pk, self.acc1)
        self.assertIn('من المشرف', str(cm.exception))
        with self.assertRaises(RequestError):
            services.transition(r.pk, S.IN_PROGRESS, self.acc1)
        self.assertEqual(services.allowed_transitions(self.acc1, r), [])
        services.assign(r.pk, self.acc1, self.sup)
        r.refresh_from_db()
        self.assertTrue(services.allowed_transitions(self.acc1, r))

    def test_start_auto_claims(self):
        r = self.make(user=self.sup)
        services.transition(r.pk, S.IN_PROGRESS, self.sup)
        r.refresh_from_db()
        self.assertEqual((r.status, r.assigned_to), (S.IN_PROGRESS, self.sup))

    def test_resolve_requires_note_and_required_documents(self):
        r = self.make(self.t_recon, fields={'f_period_start': '2026-01-01', 'f_period_end': '2026-03-31'})
        services.assign(r.pk, self.acc1, self.sup)
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
        services.assign(r.pk, self.acc1, self.sup)
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
        services.assign(r.pk, self.acc1, self.sup)
        services.transition(r.pk, S.IN_PROGRESS, self.acc1)
        with self.assertRaises(RequestError):
            services.transition(r.pk, S.ESCALATED, self.acc1, '')
        services.transition(r.pk, S.ESCALATED, self.acc1, 'مبلغ كبير')
        self.assertTrue(Notification.objects.filter(recipient=self.sup, title__contains='مصعَّد').exists())
        r.refresh_from_db()
        self.assertEqual(r.escalation_count, 1)

    def test_status_changes_audited_with_actor(self):
        r = self.make()
        services.assign(r.pk, self.acc1, self.sup)
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
        services.assign(done.pk, self.acc1, self.sup)
        services.transition(done.pk, S.IN_PROGRESS, self.acc1)
        services.transition(done.pk, S.RESOLVED, self.acc1, resolution_note='ok')
        self.assertEqual(services.escalate_overdue(), 0)

    def test_returning_to_progress_resets_clock(self):
        r = self.overdue()
        services.escalate_overdue()
        services.assign(r.pk, self.acc1, self.sup)
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




class TypeAdminTests(Base):
    def test_access(self):
        for user, code in ((self.cfo, 200), (make_user('adm', RT.ADMIN), 200), (self.sup, 302), (self.acc1, 302)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('servicedesk:types')).status_code, code, user.username)

    def test_create_custom_type_with_dynamic_fields_and_use_it(self):
        self.client.force_login(self.cfo)
        schema = [{'key': 'city', 'label': 'المدينة', 'type': 'select', 'options': ['الرياض', 'جدة'], 'required': True}]
        r = self.client.post(reverse('servicedesk:type_new'), {
            'code': 'site-visit', 'name': 'زيارة موقع', 'destination_role': 'cs_supervisor', 'escalation_role': 'cfo',
            'sla_hours': '12', 'field_schema': json.dumps(schema), 'required_documents': 'صورة الموقع\n\n',
            'create_roles': ['accountant'], 'is_active': 'on'})
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
        base = {'code': 'x', 'name': 'x', 'destination_role': 'cs_supervisor', 'escalation_role': 'cfo', 'sla_hours': '12',
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


    def test_dashboard_counts_requests(self):
        from apps.reconciliation import kpis
        a = self.make()
        b = self.make()
        ServiceRequest.objects.filter(pk=b.pk).update(due_at=timezone.now() - datetime.timedelta(hours=1))
        services.assign(a.pk, self.acc1, self.sup)
        services.transition(a.pk, S.IN_PROGRESS, self.acc1)
        services.transition(a.pk, S.RESOLVED, self.acc1, resolution_note='ok')
        out = kpis.service_request_kpis('all')
        self.assertEqual((out['total'], out['open'], out['overdue'], out['resolved']), (2, 1, 1, 1))
        self.assertIsNotNone(out['avg_resolution'])
        self.client.force_login(self.cfo)
        html = self.client.get(reverse('reconciliation:executive')).content.decode()
        self.assertIn('طلبات الموردين', html)


class InvalidDateRegressionTests(Base):
    """parse_date يرمي ValueError لتاريخ مثل 2026-13-99 فيتحول المدخل إلى 500. يجب أن يُرفض بأدب."""
    BAD = '2026-13-99'

    def test_dates_helper(self):
        from apps.core.dates import safe_parse_date, safe_parse_datetime
        self.assertIsNone(safe_parse_date(self.BAD))
        self.assertIsNone(safe_parse_date(None))
        self.assertIsNone(safe_parse_datetime(self.BAD + 'T10:00'))
        self.assertEqual(safe_parse_date(' 2026-02-03 ').isoformat(), '2026-02-03')



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
        self.client.force_login(self.cfo)
        r = self.client.post(reverse('proposals:transition', args=[p.pk]),
                             {'to': 'dispatched', 'bank_reference': 'T1', 'payment_date': self.BAD}, follow=True)
        self.assertEqual(r.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, 'approved')


class IntakeScreenTests(Base):
    """شاشة استلام الطلبات: استلام ← إرسال للمطابق ← جاري المعالجة ← اكتمال المعالجة."""

    def stage(self, req):
        from .views import intake_stage
        req.refresh_from_db()
        return intake_stage(req)

    def post(self, user, name, req, data=None):
        self.client.force_login(user)
        return self.client.post(reverse(f'servicedesk:{name}', args=[req.pk]), data or {}, follow=True)

    def test_four_step_flow(self):
        req = self.make(self.t_pay, self.sup)
        self.assertEqual(self.stage(req), 1)
        self.post(self.sup, 'receive', req)
        self.assertEqual(self.stage(req), 2)
        self.post(self.sup, 'send', req, {'accountant': self.acc1.pk})
        req.refresh_from_db()
        self.assertEqual(req.assigned_to, self.acc1)
        self.assertEqual(self.stage(req), 3)
        self.assertEqual(req.status, S.NEW)                       # أُرسل للمطابق ولم يبدأ بعد
        self.post(self.acc1, 'start', req)
        req.refresh_from_db()
        self.assertEqual(req.status, S.IN_PROGRESS)
        self.post(self.acc1, 'complete', req, {'resolution_note': 'طُوبقت الأرصدة'})
        req.refresh_from_db()
        self.assertEqual((req.status, req.resolution_note), (S.RESOLVED, 'طُوبقت الأرصدة'))
        self.assertEqual(self.stage(req), 5)

    def test_only_supervisors_receive_and_send(self):
        req = self.make(self.t_pay, self.sup)
        self.post(self.acc2, 'send', req, {'accountant': self.acc1.pk})
        req.refresh_from_db()
        self.assertIsNone(req.assigned_to)

    def test_complete_requires_a_note(self):
        req = self.make(self.t_pay, self.sup)
        self.post(self.sup, 'send', req, {'accountant': self.acc1.pk})
        self.post(self.acc1, 'start', req)
        self.post(self.acc1, 'complete', req, {'resolution_note': '  '})
        req.refresh_from_db()
        self.assertEqual(req.status, S.IN_PROGRESS)

    def test_pages_render_and_accountant_sees_only_his_tasks(self):
        mine = self.make(self.t_pay, self.sup)
        other = self.make(self.t_pay, self.sup)
        self.post(self.sup, 'send', mine, {'accountant': self.acc1.pk})
        self.client.force_login(self.acc1)
        html = self.client.get(reverse('servicedesk:list') + '?tab=all').content.decode()
        self.assertIn(mine.reference, html)
        self.assertNotIn(other.reference, html)
        self.assertEqual(self.client.get(reverse('servicedesk:detail', args=[mine.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('servicedesk:detail', args=[other.pk])).status_code, 404)

    def test_detail_renders_history_entries_without_an_actor(self):
        req = self.make(self.t_pay, self.sup)
        RequestStatusHistory.objects.create(request=req, from_status='', to_status='new', changed_by=None)
        self.client.force_login(self.sup)
        r = self.client.get(reverse('servicedesk:detail', args=[req.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'النظام')


class StepActorsAndMyTasksTests(Base):
    """منفّذ كل خطوة في شاشة الاستلام، وشاشة مهام المطابق."""

    def test_each_step_shows_who_performed_it(self):
        from .views import intake_steps
        req = self.make(self.t_pay, self.sup)
        self.client.force_login(self.sup)
        self.client.post(reverse('servicedesk:receive', args=[req.pk]))
        self.client.post(reverse('servicedesk:send', args=[req.pk]), {'accountant': self.acc1.pk})
        self.client.force_login(self.acc1)
        self.client.post(reverse('servicedesk:start', args=[req.pk]))
        self.client.post(reverse('servicedesk:complete', args=[req.pk]), {'resolution_note': 'تمت'})
        req.refresh_from_db()
        steps = {s['n']: s for s in intake_steps(req)}
        self.assertEqual(steps[1]['who'], 'sup')
        self.assertIn('sup', steps[2]['who'])
        self.assertIn('acc1', steps[2]['who'])
        self.assertEqual(steps[3]['who'], 'acc1')
        self.assertEqual(steps[4]['who'], 'acc1')
        self.assertTrue(all(s['at'] for s in steps.values()))

    def test_my_tasks_shows_only_assigned_tasks_by_stage(self):
        new = self.make(self.t_pay, self.sup)
        working = self.make(self.t_pay, self.sup)
        other = self.make(self.t_pay, self.sup)
        for r, acc in ((new, self.acc1), (working, self.acc1), (other, self.acc2)):
            services.assign(r.pk, acc, self.sup)
        services.transition(working.pk, S.IN_PROGRESS, self.acc1)
        self.client.force_login(self.acc1)
        r = self.client.get(reverse('servicedesk:my_tasks'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x.pk for x in r.context['new']], [new.pk])
        self.assertEqual([x.pk for x in r.context['working']], [working.pk])
        self.assertNotContains(r, other.reference)
        part = self.client.get(reverse('servicedesk:my_tasks') + '?partial=1')
        self.assertNotContains(part, '<html')
        self.assertContains(part, 'data-new="1"')

    def test_assignment_notifies_the_reconciler_and_counts_in_badge(self):
        from apps.core import live
        req = self.make(self.t_pay, self.sup)
        Notification.objects.all().delete()
        services.assign(req.pk, self.acc1, self.sup)
        self.assertTrue(Notification.objects.filter(recipient=self.acc1).exists())
        self.assertEqual(live.badge_counts(self.acc1, ['my_tasks'])['my_tasks']['count'], 1)
