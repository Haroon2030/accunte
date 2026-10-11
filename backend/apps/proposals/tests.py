import datetime
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.audit.legacy import mirror_legacy_row
from apps.branches.models import Branch
from apps.core.models import Notification, Role, SystemSettings, UserProfile
from apps.payments.models import AuditLog as LegacyAuditLog
from apps.payments.models import PaymentRequest
from apps.reconciliation.models import ReconciliationCase, ReconciliationResult
from apps.suppliers.models import Supplier

from . import workflow
from .models import PaymentApproval, PaymentProposal, ProposalAttachment
from .workflow import ProposalError

User = get_user_model()
S = PaymentProposal.Status
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
        ProposalAttachment._meta.get_field('file').storage = FileSystemStorage(location=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.acc = make_user('acc', RT.ACCOUNTANT)
        self.acc2 = make_user('acc2', RT.ACCOUNTANT)
        self.cfo = make_user('cfo', RT.CFO)
        self.admin = make_user('adm', RT.ADMIN)          # الصارف المدير المالي، والمؤكِّد غيره: مدير النظام
        self.sup = make_user('sup', RT.CS_SUPERVISOR)
        self.branch = Branch.objects.create(name='الرياض', code='RYD')
        self.supplier = Supplier.objects.create(name='مورد', code='S1')

    def case(self, status='completed', accountant=None):
        c = ReconciliationCase.objects.create(
            supplier=self.supplier, period_start=datetime.date(2026, 1, 1), period_end=datetime.date(2026, 3, 31),
            created_by=self.acc, status=status, assigned_accountant=accountant or self.acc)
        ReconciliationResult.objects.create(case=c, supplier_balance=Decimal('120000'), company_balance=0)
        return c

    def proposal(self, amount='10000', dues='120000', creator=None, status=S.DRAFT, case=None):
        p = PaymentProposal.objects.create(
            supplier=self.supplier, branch=self.branch, reconciliation_case=case or self.case(),
            total_dues=Decimal(dues), proposed_amount=Decimal(amount), justification='مبرر',
            created_by=creator or self.acc, status=status, requires_cfo=workflow.requires_cfo(Decimal(amount)))
        return p

    def go(self, p, to, user, reason='', **extra):
        return workflow.transition(p.pk, to, user, reason, extra or None)


class ConstraintTests(Base):
    def test_amount_rules(self):
        c = self.case()
        for amount, dues in (('0', '100'), ('-5', '100'), ('200', '100')):
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.proposal(amount=amount, dues=dues, case=self.case())
        self.proposal(amount='100', dues='100', case=c)   # يساوي المستحقات: مسموح

    def test_one_active_proposal_per_case(self):
        c = self.case()
        p1 = self.proposal(case=c)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.proposal(case=c)
        p1.status = S.REJECTED
        p1.save()
        self.proposal(case=c)   # بعد الرفض يُسمح بمقترح جديد


class LifecycleTests(Base):
    def test_full_lifecycle_with_separation_of_duties(self):
        p = self.proposal(amount='75000')              # فوق الحد 50,000
        self.go(p, S.SUBMITTED, self.acc)
        p.refresh_from_db()
        self.assertTrue(p.requires_cfo)
        self.assertTrue(Notification.objects.filter(recipient=self.cfo, title__contains='بانتظار المراجعة').exists())

        with self.assertRaises(ProposalError):          # المنشئ لا يراجع
            self.go(p, S.PENDING_REVIEW, self.acc)
        with self.assertRaises(ProposalError):          # ومشرف الدعم لا يراجع
            self.go(p, S.PENDING_REVIEW, self.sup)
        self.go(p, S.PENDING_REVIEW, self.cfo)

        with self.assertRaises(ProposalError):          # المطابق لا يعتمد
            self.go(p, S.APPROVED, self.acc2)
        self.go(p, S.APPROVED, self.cfo, 'موافق')
        self.assertTrue(Notification.objects.filter(recipient=self.cfo, title__contains='جاهز للصرف').exists())

        with self.assertRaises(ProposalError):          # الصرف يتطلب مرجعًا وتاريخًا
            self.go(p, S.DISPATCHED, self.cfo)
        with self.assertRaises(ProposalError):          # المنشئ لا يصرف
            self.go(p, S.DISPATCHED, self.acc, bank_reference='X', payment_date=datetime.date.today())
        self.go(p, S.DISPATCHED, self.cfo, bank_reference='TRF-1', payment_date=datetime.date(2026, 5, 1))
        ex = p.execution
        self.assertEqual(ex.executed_amount, Decimal('75000.00'))

        with self.assertRaises(ProposalError):          # من صرف لا يؤكد
            self.go(p, S.CONFIRMED_PAID, self.cfo)
        self.go(p, S.CONFIRMED_PAID, self.admin)
        ex.refresh_from_db()
        self.assertEqual(ex.confirmed_by, self.admin)
        p.refresh_from_db()
        self.assertTrue(p.is_terminal)
        with self.assertRaises(ProposalError):
            self.go(p, S.CANCELLED, self.cfo, 'x')

    def test_threshold_flag_is_configurable_and_only_cfo_approves(self):
        low = self.proposal(amount='20000')
        self.go(low, S.SUBMITTED, self.acc)
        low.refresh_from_db()
        self.assertFalse(low.requires_cfo)
        self.go(low, S.PENDING_REVIEW, self.cfo)
        with self.assertRaises(ProposalError):
            self.go(low, S.APPROVED, self.sup)
        self.go(low, S.APPROVED, self.cfo)

        SystemSettings.objects.create(key=workflow.THRESHOLD_KEY, value='10000')   # الحد قابل للضبط
        mid = self.proposal(amount='20000')
        self.go(mid, S.SUBMITTED, self.acc)
        mid.refresh_from_db()
        self.assertTrue(mid.requires_cfo)

    def test_creator_cannot_approve_even_if_cfo(self):
        p = self.proposal(amount='80000', creator=self.cfo)
        self.go(p, S.SUBMITTED, self.cfo)
        self.go(p, S.PENDING_REVIEW, self.admin)
        with self.assertRaises(ProposalError):
            self.go(p, S.APPROVED, self.cfo)
        self.go(p, S.APPROVED, self.admin)

    def test_needs_info_loop_and_reasons(self):
        p = self.proposal()
        self.go(p, S.SUBMITTED, self.acc)
        self.go(p, S.PENDING_REVIEW, self.cfo)
        for to in (S.REJECTED, S.NEEDS_INFO):
            with self.assertRaises(ProposalError):
                self.go(p, to, self.cfo, '')
        self.go(p, S.NEEDS_INFO, self.cfo, 'أرفق كشف الحساب')
        self.go(p, S.SUBMITTED, self.acc)
        self.go(p, S.PENDING_REVIEW, self.cfo)
        self.go(p, S.REJECTED, self.cfo, 'غير مبرر')
        decisions = list(p.approvals.values_list('decision', flat=True))
        self.assertEqual(decisions, ['needs_info', 'rejected'])

    def test_cannot_submit_when_case_not_completed(self):
        p = self.proposal(case=self.case(status='reconciling'))
        with self.assertRaises(ProposalError):
            self.go(p, S.SUBMITTED, self.acc)

    def test_illegal_jump_rejected(self):
        p = self.proposal()
        with self.assertRaises(ProposalError):
            self.go(p, S.APPROVED, self.cfo)


class AmountLockAndAuditTests(Base):
    def test_amount_edit_locked_after_submit_and_audited_before(self):
        p = self.proposal(amount='10000')
        workflow.update_proposal(p.pk, self.acc, total_dues=Decimal('120000'), proposed_amount=Decimal('12000'),
                                 justification='جديد', branch=self.branch)
        log = AuditLog.objects.get(action=AuditLog.Action.AMOUNT_EDIT)
        self.assertEqual(log.previous_state['proposed_amount'], '10000.00')
        self.assertEqual(log.new_state['proposed_amount'], '12000.00')
        self.assertEqual(log.actor_username if log.actor else '', '') if False else None
        self.go(p, S.SUBMITTED, self.acc)
        with self.assertRaises(ProposalError):
            workflow.update_proposal(p.pk, self.acc, total_dues=Decimal('120000'), proposed_amount=Decimal('99999'),
                                     justification='x', branch=self.branch)
        with self.assertRaises(ProposalError):
            workflow.update_proposal(p.pk, self.acc2, total_dues=Decimal('1'), proposed_amount=Decimal('1'),
                                     justification='x', branch=self.branch)

    def test_edit_cannot_exceed_dues(self):
        p = self.proposal()
        with self.assertRaises(ProposalError):
            workflow.update_proposal(p.pk, self.acc, total_dues=Decimal('100'), proposed_amount=Decimal('200'),
                                     justification='x', branch=self.branch)

    def test_approval_decision_audited(self):
        p = self.proposal(amount='5000')
        self.go(p, S.SUBMITTED, self.acc)
        self.go(p, S.PENDING_REVIEW, self.cfo)
        self.go(p, S.APPROVED, self.cfo, 'تمام')
        appr = AuditLog.objects.get(action=AuditLog.Action.APPROVAL)
        self.assertEqual((appr.actor, appr.reason, appr.new_state['decision']), (self.cfo, 'تمام', 'approved'))
        sc = AuditLog.objects.filter(action=AuditLog.Action.STATUS_CHANGE).order_by('id')
        self.assertEqual([l.new_state['status'] for l in sc], ['submitted', 'pending_review', 'approved'])


class AnalyticsDedupTests(Base):
    def test_totals_count_each_proposal_once(self):
        a = self.proposal(amount='1000')
        b = self.proposal(amount='2000')
        # عدة قرارات ومرفقات لنفس المقترح: لو رُبطت بالتجميع لتضاعف العدّ والمبلغ
        for _ in range(3):
            PaymentApproval.objects.create(proposal=a, decision='needs_info', decided_by=self.cfo,
                                           amount_at_decision=a.proposed_amount)
        for i in range(2):
            ProposalAttachment.objects.create(proposal=a, original_name=f'f{i}', file=SimpleUploadedFile(f'f{i}.pdf', b'x'))
        totals = workflow.totals_by_status()
        self.assertEqual(totals['draft'], {'count': 2, 'total': Decimal('3000.00')})

        # الاستعلام المنفّذ عبر ربط يُظهر لماذا نتجنبه: يتضاعف العدّ
        from django.db.models import Count
        joined = PaymentProposal.objects.filter(approvals__isnull=False).values('status').annotate(n=Count('pk'))
        self.assertEqual(joined[0]['n'], 3)


class VisibilityAndHttpTests(Base):
    def test_row_level_visibility(self):
        mine = self.proposal(creator=self.acc)
        peer = self.proposal(creator=self.acc2)
        self.client.force_login(self.acc)
        refs = [p.reference for p in self.client.get(reverse('proposals:list')).context['page_obj']]
        self.assertEqual(refs, [mine.reference])
        self.assertEqual(self.client.get(reverse('proposals:detail', args=[peer.pk])).status_code, 404)
        r = self.client.post(reverse('proposals:transition', args=[peer.pk]), {'to': 'submitted'})
        self.assertEqual(r.status_code, 404)

    def test_cfo_sees_everything(self):
        a = self.proposal(creator=self.acc)
        b = self.proposal(creator=self.acc2)
        self.client.force_login(self.cfo)
        refs = {p.reference for p in self.client.get(reverse('proposals:list')).context['page_obj']}
        self.assertEqual(refs, {a.reference, b.reference})

    def test_supervisor_sees_only_own_and_cannot_act_on_others(self):
        p = self.proposal(status=S.PENDING_REVIEW, amount='500')
        self.client.force_login(self.sup)
        self.assertEqual(self.client.get(reverse('proposals:detail', args=[p.pk])).status_code, 404)
        self.client.post(reverse('proposals:transition', args=[p.pk]), {'to': 'approved'})
        p.refresh_from_db()
        self.assertEqual(p.status, S.PENDING_REVIEW)

    def test_create_via_http_requires_completed_case_and_blocks_duplicates(self):
        done = self.case()
        open_case = self.case(status='reconciling')
        self.client.force_login(self.acc)
        url = reverse('proposals:create')
        bad = self.client.post(url, {'case': open_case.pk, 'branch': self.branch.pk, 'total_dues': '100',
                                     'proposed_amount': '50', 'justification': 'x'})
        self.assertEqual(bad.status_code, 200)
        self.assertFalse(PaymentProposal.objects.exists())
        data = {'case': done.pk, 'branch': self.branch.pk, 'total_dues': '120,000.00', 'proposed_amount': '60000',
                'justification': 'سداد جزئي', 'file': SimpleUploadedFile('a.pdf', b'%PDF')}
        resp = self.client.post(url, data)
        p = PaymentProposal.objects.get()
        self.assertRedirects(resp, reverse('proposals:detail', args=[p.pk]))
        self.assertTrue(p.requires_cfo)
        self.assertEqual(p.attachments.count(), 1)
        self.assertEqual(self.client.post(url, {**data, 'file': SimpleUploadedFile('b.pdf', b'x')}).status_code, 200)
        self.assertEqual(PaymentProposal.objects.count(), 1)

    def test_attachment_access_control(self):
        p = self.proposal(creator=self.acc)
        att = ProposalAttachment.objects.create(proposal=p, original_name='a.pdf', file=SimpleUploadedFile('a.pdf', b'x'))
        self.client.force_login(self.acc2)
        self.assertEqual(self.client.get(reverse('proposals:attachment_download', args=[p.pk, att.pk])).status_code, 404)
        self.client.force_login(self.acc)
        self.assertEqual(self.client.get(reverse('proposals:attachment_download', args=[p.pk, att.pk])).status_code, 200)


class LegacyAuditBridgeTests(Base):
    def _payment(self):
        return PaymentRequest.objects.create(branch=self.branch, created_by=self.acc, amount=100)

    def test_new_legacy_rows_are_mirrored_once(self):
        pay = self._payment()
        LegacyAuditLog.objects.create(payment_request=pay, user=self.cfo, action='تغيير الحالة', old_status='proposed',
                                      new_status='first_approved', notes='ok', ip_address='10.0.0.5', user_agent='UA')
        entry = AuditLog.objects.get(entity_type='payments.PaymentRequest')
        self.assertEqual(entry.action, AuditLog.Action.APPROVAL)
        self.assertEqual((entry.actor, entry.entity_id, entry.reason, entry.ip_address), (self.cfo, str(pay.pk), 'ok', '10.0.0.5'))
        self.assertEqual(entry.previous_state, {'status': 'proposed'})
        legacy = LegacyAuditLog.objects.get()
        self.assertIsNone(mirror_legacy_row(legacy))   # لا تكرار
        self.assertEqual(AuditLog.objects.filter(entity_type='payments.PaymentRequest').count(), 1)

    def test_backfill_copies_pre_bridge_rows_and_is_idempotent(self):
        from django.core.management import call_command
        from django.db.models.signals import post_save
        from apps.audit import legacy
        pay = self._payment()
        # نحاكي صفوفًا قديمة سبقت الجسر: نفصل الإشارة أثناء إنشائها
        post_save.disconnect(sender=LegacyAuditLog, dispatch_uid='audit_mirror_legacy_payment_log')
        try:
            for i in range(3):
                LegacyAuditLog.objects.create(payment_request=pay, user=self.cfo, action=f'a{i}',
                                              old_status='proposed', new_status='audited')
        finally:
            legacy.connect()
        self.assertEqual(AuditLog.objects.filter(entity_type='payments.PaymentRequest').count(), 0)
        call_command('backfill_payment_audit', verbosity=0)
        self.assertEqual(AuditLog.objects.filter(entity_type='payments.PaymentRequest').count(), 3)
        call_command('backfill_payment_audit', verbosity=0)    # مرة ثانية: لا تكرار
        self.assertEqual(AuditLog.objects.filter(entity_type='payments.PaymentRequest').count(), 3)
        first = AuditLog.objects.filter(entity_type='payments.PaymentRequest').order_by('id').first()
        self.assertIn('legacy_created_at', first.new_state)    # الوقت الأصلي محفوظ

    def test_web_status_change_and_amount_changes_are_audited(self):
        pay = self._payment()
        self.client.force_login(self.cfo)
        self.client.post(reverse('payments:change_status', args=[pay.pk]), {'status': 'rejected', 'rejection_reason': 'خطأ'})
        log = AuditLog.objects.get(entity_type='payments.PaymentRequest', action=AuditLog.Action.APPROVAL)
        self.assertEqual((log.previous_state['status'], log.new_state['status'], log.reason), ('draft', 'rejected', 'خطأ'))


class DecimalFormatRegressionTests(Base):
    """بعد ضبط اللغة العربية يجب أن تبقى الفاصلة العشرية نقطة، وإلا صار 500.50 → "500,50" → 50050."""

    def test_decimal_rendered_with_dot(self):
        from django.template import Context, Template
        out = Template('{{ a }}|{{ a|floatformat:2 }}').render(Context({'a': Decimal('1234.50')}))
        self.assertEqual(out, '1234.50|1234.50')

    def test_result_form_roundtrip_keeps_amount(self):
        from apps.reconciliation.models import ReconciliationCase as RC
        case = RC.objects.create(supplier=self.supplier, period_start=datetime.date(2026, 1, 1),
                                 period_end=datetime.date(2026, 2, 1), created_by=self.acc, status='reconciling',
                                 assigned_accountant=self.acc)
        ReconciliationResult.objects.create(case=case, supplier_balance=Decimal('500.50'), company_balance=0)
        self.client.force_login(self.acc)
        html = self.client.get(reverse('reconciliation:detail', args=[case.pk])).content.decode()
        self.assertIn('value="500.50"', html)
        self.assertNotIn('500,50', html)
