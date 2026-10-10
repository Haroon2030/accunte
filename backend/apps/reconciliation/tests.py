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
        self.agent = make_user('agent', Role.RoleType.CS_AGENT)
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

    def test_full_lifecycle_via_http(self):
        # 1) الوكيل ينشئ الحالة مع كشف الحساب
        self.client.force_login(self.agent)
        stmt = SimpleUploadedFile('statement.xlsx', b'PK-fake-xlsx')
        resp = self.client.post(reverse('reconciliation:create'), {
            'supplier': self.supplier.pk, 'period_start': '2026-01-01', 'period_end': '2026-03-31',
            'priority': 'high', 'due_date': '2026-12-31', 'statement': stmt})
        case = Case.objects.get()
        self.assertRedirects(resp, reverse('reconciliation:detail', args=[case.pk]))
        self.assertEqual(case.status, S.READY_FOR_DISTRIBUTION)
        self.assertEqual(case.documents.count(), 1)
        self.assertEqual(len(case.documents.get().sha256), 64)

        # 2) المشرف يوزع
        self.client.force_login(self.supervisor)
        self.client.post(reverse('reconciliation:distribution'),
                         {'action': 'assign', 'accountant': self.acc.pk, 'case_ids': [case.pk]})
        case.refresh_from_db()
        self.assertEqual((case.status, case.assigned_accountant), (S.ASSIGNED, self.acc))
        self.assertTrue(Notification.objects.filter(recipient=self.acc).exists())

        # 3) المحاسب يطابق: يبدأ، يسجل النتيجة والفرق، يرفع مستندًا
        self.client.force_login(self.acc)
        url = lambda name, *a: reverse(f'reconciliation:{name}', args=[case.pk, *a])
        self.client.post(url('transition'), {'to': 'reconciling'})
        self.client.post(url('result_save'), {'supplier_balance': '1,500.50', 'company_balance': '1000'})
        self.client.post(url('difference_add'), {'kind': 'missing_invoice', 'document_ref': 'INV-9',
                                                  'supplier_amount': '500.50', 'company_amount': '0',
                                                  'attachment': SimpleUploadedFile('inv.pdf', b'%PDF-1.4')})
        self.client.post(url('document_upload'), {'file': SimpleUploadedFile('x.pdf', b'%PDF'), 'doc_type': 'supporting'})
        self.client.post(url('transition'), {'to': 'discrepancy_found'})
        case.refresh_from_db()
        self.assertEqual(case.status, S.DISCREPANCY_FOUND)
        result = case.result
        self.assertEqual(result.difference, Decimal('500.50'))
        self.assertEqual(case.documents.count(), 2)

        diff = case.differences.get()
        self.client.post(url('difference_toggle', diff.pk))
        self.client.post(url('transition'), {'to': 'pending_review'})
        case.refresh_from_db()
        self.assertEqual(case.status, S.PENDING_REVIEW)

        # 4) المحاسب لا يعتمد، والمدير المالي يعتمد ثم المشرف يغلق
        self.client.post(url('transition'), {'to': 'completed'})
        case.refresh_from_db()
        self.assertEqual(case.status, S.PENDING_REVIEW)
        self.client.force_login(self.cfo)
        self.client.post(url('transition'), {'to': 'completed'})
        self.client.force_login(self.supervisor)
        self.client.post(url('transition'), {'to': 'closed'})
        case.refresh_from_db()
        self.assertEqual(case.status, S.CLOSED)
        self.assertIsNotNone(case.closed_at)

        # 5) التحميل يعمل ويُدقَّق
        self.client.force_login(self.cfo)
        doc = case.documents.first()
        r = self.client.get(url('document_download', doc.pk))
        self.assertEqual(r.status_code, 200)
        self.assertIn('attachment', r['Content-Disposition'])

        # سجل الحالات كامل
        path = list(case.history.values_list('to_status', flat=True))
        self.assertEqual(path, ['new', 'ready_for_distribution', 'assigned', 'reconciling', 'discrepancy_found',
                                'pending_review', 'completed', 'closed'])

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
    def test_distribution_across_8_accountants_is_balanced(self):
        accs = [make_user(f'a{i}', Role.RoleType.ACCOUNTANT) for i in range(6)] + [self.acc, self.acc2]
        # حمل مسبق: المحاسب 0 عنده 5 حالات مفتوحة
        for _ in range(5):
            self.new_case(status=S.RECONCILING, assigned_accountant=accs[0])
        ready = [self.new_case(status=S.READY_FOR_DISTRIBUTION,
                               priority='urgent' if i < 3 else 'normal') for i in range(24)]

        plan = services.suggest_distribution(ready)
        self.assertEqual(len(plan), 24)
        counts = {}
        for _, u in plan:
            counts[u.pk] = counts.get(u.pk, 0) + 1
        self.assertEqual(len(services.accountants()), 8)
        self.assertLessEqual(counts.get(accs[0].pk, 0), min(counts.values()))   # الأكثر حملًا يأخذ الأقل
        totals = [counts.get(a.pk, 0) + (5 if a.pk == accs[0].pk else 0) for a in accs]
        self.assertLessEqual(max(totals) - min(totals), 2)

        services.assign_cases([(c.pk, u) for c, u in plan], self.supervisor)
        loads = {u.pk: u.open_count for u in services.accountant_loads()}
        self.assertEqual(sum(loads.values()), 29)

    def test_capacity_view_counts_overdue(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        self.new_case(status=S.RECONCILING, assigned_accountant=self.acc, due_date=yesterday)
        self.new_case(status=S.COMPLETED, assigned_accountant=self.acc, due_date=yesterday)   # لا تُحسب
        row = next(u for u in services.accountant_loads() if u.pk == self.acc.pk)
        self.assertEqual((row.open_count, row.overdue_count), (1, 1))

    def test_non_supervisor_cannot_assign(self):
        c = self.new_case(status=S.READY_FOR_DISTRIBUTION)
        with self.assertRaises(TransitionError):
            services.assign_cases([(c.pk, self.acc)], self.agent)

    def test_assigning_non_accountant_rejected(self):
        c = self.new_case(status=S.READY_FOR_DISTRIBUTION)
        with self.assertRaises(TransitionError):
            services.assign_cases([(c.pk, self.agent)], self.supervisor)

    def test_reassign_keeps_single_active_assignment(self):
        c = self.new_case(status=S.READY_FOR_DISTRIBUTION)
        services.assign_cases([(c.pk, self.acc)], self.supervisor)
        services.assign_cases([(c.pk, self.acc2)], self.supervisor)
        self.assertEqual(c.assignments.filter(is_active=True).count(), 1)
        self.assertEqual(c.assignments.count(), 2)


class AccessControlTests(Base):
    def setUp(self):
        super().setUp()
        self.mine = self.new_case(status=S.RECONCILING, assigned_accountant=self.acc)
        self.peer = self.new_case(status=S.RECONCILING, assigned_accountant=self.acc2)

    def test_accountant_list_shows_only_own_cases(self):
        self.client.force_login(self.acc)
        resp = self.client.get(reverse('reconciliation:list'))
        refs = [c.reference for c in resp.context['page_obj']]
        self.assertEqual(refs, [self.mine.reference])

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

    def test_accountant_cannot_open_distribution_or_create(self):
        self.client.force_login(self.acc)
        self.assertEqual(self.client.get(reverse('reconciliation:distribution')).status_code, 302)
        self.assertEqual(self.client.get(reverse('reconciliation:create')).status_code, 302)

    def test_branch_employee_has_no_access(self):
        u = make_user('emp', Role.RoleType.BRANCH_EMPLOYEE)
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('reconciliation:list')).status_code, 302)

    def test_anonymous_redirected_to_login(self):
        self.assertEqual(self.client.get(reverse('reconciliation:list')).status_code, 302)

    def test_cfo_sees_all_but_cs_agent_cannot_work(self):
        self.client.force_login(self.cfo)
        self.assertEqual(len(self.client.get(reverse('reconciliation:list')).context['page_obj']), 2)
        self.client.force_login(self.agent)
        self.client.post(reverse('reconciliation:result_save', args=[self.mine.pk]),
                         {'supplier_balance': '9', 'company_balance': '1'})
        self.assertFalse(ReconciliationResult.objects.filter(case=self.mine).exists())


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
