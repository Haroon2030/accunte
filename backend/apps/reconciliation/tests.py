import datetime
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.branches.models import Branch
from apps.core.models import Notification, Role, UserProfile
from apps.suppliers.models import Supplier

from . import services, workflow
from .models import (ReconciliationCase as Case, ReconciliationDifference, ReconciliationDocument,
                     ReconciliationResult, StatusHistory)
from .workflow import TransitionError

User = get_user_model()
S = Case.Status


def make_user(username, role_type):
    role, _ = Role.objects.get_or_create(
        role_type=role_type, defaults={'name': f'role-{role_type}', 'is_system_role': True})
    u = User.objects.create_user(username, password='x-Pass-12345')
    UserProfile.objects.create(user=u, role=role)
    return u


class Base(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp()
        for model, field in ((ReconciliationDocument, 'file'), (ReconciliationDifference, 'attachment')):
            model._meta.get_field(field).storage = FileSystemStorage(location=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.supervisor = make_user('sup', Role.RoleType.CS_SUPERVISOR)
        self.cfo = make_user('cfo', Role.RoleType.CFO)
        self.agent = make_user('agent', Role.RoleType.CS_SUPERVISOR)
        self.acc = make_user('acc1', Role.RoleType.ACCOUNTANT)
        self.acc2 = make_user('acc2', Role.RoleType.ACCOUNTANT)
        self.supplier = Supplier.objects.create(name='مورد تجريبي', code='S1')

    def new_case(self, status=S.NEW, **kw):
        defaults = dict(supplier=self.supplier, period_start=datetime.date(2026, 1, 1),
                        period_end=datetime.date(2026, 3, 31), created_by=self.agent, status=status)
        defaults.update(kw)
        return Case.objects.create(**defaults)

    def add_statement(self, case):
        return ReconciliationDocument.objects.create(
            case=case, doc_type='statement', original_name='s.xlsx',
            file=SimpleUploadedFile('s.xlsx', b'data'), uploaded_by=self.agent)


class WorkflowTests(Base):
    def test_reference_and_period_constraint(self):
        c = self.new_case()
        self.assertRegex(c.reference, r'^RC-\d{4}-\d{5}$')
        from django.db import IntegrityError, transaction
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.new_case(period_start=datetime.date(2026, 5, 1), period_end=datetime.date(2026, 4, 1))

    def test_invalid_transition_rejected(self):
        c = self.new_case()
        with self.assertRaises(TransitionError):
            workflow.transition(c.pk, S.COMPLETED, self.cfo)

    def test_ready_requires_statement(self):
        c = self.new_case()
        with self.assertRaises(TransitionError):
            workflow.transition(c.pk, S.READY_FOR_DISTRIBUTION, self.agent)
        self.add_statement(c)
        workflow.transition(c.pk, S.READY_FOR_DISTRIBUTION, self.agent)

    def test_cancel_requires_reason(self):
        c = self.new_case()
        with self.assertRaises(TransitionError):
            workflow.transition(c.pk, S.CANCELLED, self.supervisor, '')
        workflow.transition(c.pk, S.CANCELLED, self.supervisor, 'مكرر')
        c.refresh_from_db()
        self.assertEqual(c.status, S.CANCELLED)
        with self.assertRaises(TransitionError):    # نهائية
            workflow.transition(c.pk, S.NEW, self.supervisor)

    def test_discrepancy_requires_difference_row(self):
        c = self.new_case(status=S.RECONCILING, assigned_accountant=self.acc)
        with self.assertRaises(TransitionError):
            workflow.transition(c.pk, S.DISCREPANCY_FOUND, self.acc)
        ReconciliationDifference.objects.create(case=c, supplier_amount=100, company_amount=80)
        workflow.transition(c.pk, S.DISCREPANCY_FOUND, self.acc)

    def test_accountant_cannot_approve_own_review(self):
        c = self.new_case(status=S.PENDING_REVIEW, assigned_accountant=self.acc)
        with self.assertRaises(TransitionError):
            workflow.transition(c.pk, S.COMPLETED, self.acc)

    def test_completion_blocked_by_unresolved_differences(self):
        c = self.new_case(status=S.PENDING_REVIEW, assigned_accountant=self.acc)
        d = ReconciliationDifference.objects.create(case=c, supplier_amount=100, company_amount=80)
        with self.assertRaises(TransitionError):
            workflow.transition(c.pk, S.COMPLETED, self.cfo)
        d.is_resolved = True
        d.save()
        workflow.transition(c.pk, S.COMPLETED, self.cfo)

    def test_review_rejection_needs_reason(self):
        c = self.new_case(status=S.PENDING_REVIEW, assigned_accountant=self.acc)
        with self.assertRaises(TransitionError):
            workflow.transition(c.pk, S.RECONCILING, self.cfo, '')
        workflow.transition(c.pk, S.RECONCILING, self.cfo, 'الرصيد غير مطابق')


class EndToEndLifecycleTests(Base):
    """إنشاء ← توزيع ← مطابقة ← اعتماد ← إغلاق، مع ملفات."""


    def test_upload_rejects_bad_extension_and_size(self):
        c = self.new_case(status=S.ASSIGNED, assigned_accountant=self.acc)
        self.client.force_login(self.acc)
        self.client.post(reverse('reconciliation:document_upload', args=[c.pk]),
                         {'file': SimpleUploadedFile('evil.exe', b'MZ')})
        self.assertEqual(c.documents.count(), 0)
        big = SimpleUploadedFile('big.pdf', b'0' * (services.MAX_FILE_BYTES + 1))
        self.client.post(reverse('reconciliation:document_upload', args=[c.pk]), {'file': big})
        self.assertEqual(c.documents.count(), 0)


class WorkloadBalanceTests(Base):

    def test_capacity_view_counts_overdue(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        self.new_case(status=S.RECONCILING, assigned_accountant=self.acc, due_date=yesterday)
        self.new_case(status=S.COMPLETED, assigned_accountant=self.acc, due_date=yesterday)   # لا تُحسب
        row = next(u for u in services.accountant_loads() if u.pk == self.acc.pk)
        self.assertEqual((row.open_count, row.overdue_count), (1, 1))





class AccessControlTests(Base):
    def setUp(self):
        super().setUp()
        self.mine = self.new_case(status=S.RECONCILING, assigned_accountant=self.acc)
        self.peer = self.new_case(status=S.RECONCILING, assigned_accountant=self.acc2)


    def test_accountant_gets_404_on_peer_case(self):
        self.client.force_login(self.acc)
        self.assertEqual(self.client.get(reverse('reconciliation:detail', args=[self.peer.pk])).status_code, 404)

    def test_accountant_cannot_modify_peer_case(self):
        self.client.force_login(self.acc)
        pk = self.peer.pk
        for name, data in (('transition', {'to': 'pending_review'}),
                           ('result_save', {'supplier_balance': '1', 'company_balance': '0'}),
                           ('difference_add', {'supplier_amount': '5'}),
                           ('document_upload', {'file': SimpleUploadedFile('a.pdf', b'x')})):
            r = self.client.post(reverse(f'reconciliation:{name}', args=[pk]), data)
            self.assertEqual(r.status_code, 404, name)
        self.peer.refresh_from_db()
        self.assertEqual(self.peer.status, S.RECONCILING)
        self.assertFalse(ReconciliationResult.objects.filter(case=self.peer).exists())
        self.assertEqual(self.peer.differences.count(), 0)

    def test_accountant_cannot_download_peer_document(self):
        doc = self.add_statement(self.peer)
        self.client.force_login(self.acc)
        r = self.client.get(reverse('reconciliation:document_download', args=[self.peer.pk, doc.pk]))
        self.assertEqual(r.status_code, 404)






class AuditIntegrityTests(Base):
    def test_transitions_amount_edits_and_approval_are_audited(self):
        c = self.new_case(status=S.RECONCILING, assigned_accountant=self.acc)
        self.client.force_login(self.acc)
        save = lambda sb: self.client.post(reverse('reconciliation:result_save', args=[c.pk]),
                                           {'supplier_balance': sb, 'company_balance': '100'})
        save('500')
        save('650')
        edit = AuditLog.objects.get(action=AuditLog.Action.AMOUNT_EDIT)
        self.assertEqual(edit.previous_state['supplier_balance'], '500.00')
        self.assertEqual(edit.new_state['supplier_balance'], '650.00')
        self.assertEqual(edit.actor_username, 'acc1')

        self.client.post(reverse('reconciliation:transition', args=[c.pk]), {'to': 'pending_review'})
        self.client.force_login(self.cfo)
        self.client.post(reverse('reconciliation:transition', args=[c.pk]), {'to': 'completed', 'reason': 'مطابق'})
        sc = AuditLog.objects.filter(action=AuditLog.Action.STATUS_CHANGE).order_by('id')
        self.assertEqual([(l.previous_state['status'], l.new_state['status']) for l in sc],
                         [('reconciling', 'pending_review'), ('pending_review', 'completed')])
        appr = AuditLog.objects.get(action=AuditLog.Action.APPROVAL)
        self.assertEqual((appr.actor_username, appr.reason), ('cfo', 'مطابق'))

    def test_audit_failed_transition_not_logged_as_change(self):
        c = self.new_case()
        with self.assertRaises(TransitionError):
            workflow.transition(c.pk, S.COMPLETED, self.cfo)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.STATUS_CHANGE).exists())
        self.assertEqual(StatusHistory.objects.count(), 0)


class CaseTrackingTests(TestCase):
    """صفحة تتبّع المسار: مراحل، من تقف عنده الحالة، وسلسلة الأحداث."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        from apps.core.models import Role, UserProfile
        from apps.suppliers.models import Supplier
        User = get_user_model()
        cls.cfo = User.objects.create_user('trk_cfo', password='x', first_name='مدير')
        role, _ = Role.objects.get_or_create(role_type=Role.RoleType.CFO, defaults={'name': 'المدير المالي'})
        UserProfile.objects.update_or_create(user=cls.cfo, defaults={'role': role})
        cls.acc = User.objects.create_user('trk_acc', password='x', first_name='محاسب')
        cls.supplier = Supplier.objects.create(name='مورد تتبّع', code='TRK1')
        cls.case = Case.objects.create(supplier=cls.supplier, period_start=datetime.date(2026, 1, 1), period_end=datetime.date(2026, 1, 31),
                                       created_by=cls.cfo, status=Case.Status.RECONCILING, assigned_accountant=cls.acc)
        from .models import StatusHistory, WorkAssignment
        WorkAssignment.objects.create(case=cls.case, accountant=cls.acc, assigned_by=cls.cfo, note='عاجل')
        StatusHistory.objects.create(case=cls.case, from_status='new', to_status='ready_for_distribution', changed_by=cls.cfo)
        StatusHistory.objects.create(case=cls.case, from_status='ready_for_distribution', to_status='assigned', changed_by=cls.cfo)
        StatusHistory.objects.create(case=cls.case, from_status='assigned', to_status='reconciling', changed_by=cls.acc)

    def test_build_tracks_stage_holder_and_events(self):
        from . import tracking
        t = tracking.build(self.case)
        states = {s['key']: s['state'] for s in t['stages']}
        self.assertEqual(states['working'], 'current')
        self.assertEqual(states['intake'], 'done')
        self.assertEqual(states['assigned'], 'done')
        self.assertEqual(states['review'], 'upcoming')
        self.assertIn('محاسب', t['holder']['name'])
        self.assertEqual(len(t['chain']), 1)
        titles = ' '.join(e['title'] for e in t['events'])
        self.assertIn('أُسندت إلى', titles)
        self.assertTrue(0 < t['progress'] < 100)

    def test_cancelled_case_marks_stage_cancelled(self):
        from . import tracking
        from .models import StatusHistory
        self.case.status = Case.Status.CANCELLED
        self.case.save()
        StatusHistory.objects.create(case=self.case, from_status='reconciling', to_status='cancelled',
                                     changed_by=self.cfo, reason='طلب المورد')
        t = tracking.build(self.case)
        self.assertTrue(t['cancelled'])
        self.assertEqual([s['key'] for s in t['stages'] if s['state'] == 'cancelled'], ['working'])
        self.assertIsNone(t['holder'])

    def test_page_renders_for_supervisor_only_visible_cases(self):
        self.client.force_login(self.cfo)
        r = self.client.get(f'/reconciliation/{self.case.pk}/track/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'عند من الآن')
        self.assertContains(r, 'مورد تتبّع')
        other = __import__('django.contrib.auth', fromlist=['get_user_model']).get_user_model().objects.create_user('trk_other', password='x')
        self.client.force_login(other)
        self.assertIn(self.client.get(f'/reconciliation/{self.case.pk}/track/').status_code, (302, 403, 404))

    def test_approve_and_close_in_one_step_from_track_page(self):
        from .models import ReconciliationResult
        Case.objects.filter(pk=self.case.pk).update(status=Case.Status.PENDING_REVIEW)
        ReconciliationResult.objects.create(case=self.case, supplier_balance=100, company_balance=100, recorded_by=self.acc)
        self.client.force_login(self.cfo)
        page = self.client.get(f'/reconciliation/{self.case.pk}/track/')
        self.assertContains(page, 'اعتماد وإغلاق')
        r = self.client.post(f'/reconciliation/{self.case.pk}/transition/',
                             {'to': 'completed', 'then_close': '1', 'next': 'track'})
        self.assertRedirects(r, f'/reconciliation/{self.case.pk}/track/', fetch_redirect_response=False)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, Case.Status.CLOSED)
