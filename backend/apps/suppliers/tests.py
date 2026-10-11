import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from apps.audit.models import AuditLog
from apps.core.models import Role, UserProfile

from . import importer
from .models import Supplier, SupplierContact, SupplierImportJob

User = get_user_model()
HEADERS = ['رقم المورد', 'رقم المورد في النظام المالي', 'اسم المورد', 'الرقم الضريبي', 'الهاتف']


def make_xlsx(rows, headers=HEADERS):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def user_with_role(username, role_type):
    role, _ = Role.objects.get_or_create(
        role_type=role_type, defaults={'name': f'role-{role_type}', 'is_system_role': True})
    u = User.objects.create_user(username, password='x-Pass-12345')
    UserProfile.objects.create(user=u, role=role)
    return u


class PhoneNormalizationTests(TestCase):
    def test_saudi_formats(self):
        for raw in ('0501234567', '501234567', '+966501234567', '00966501234567', '050 123 4567'):
            self.assertEqual(importer.normalize_phone(raw), '966501234567', raw)

    def test_invalid(self):
        self.assertIsNone(importer.normalize_phone('abc'))
        self.assertIsNone(importer.normalize_phone('123'))


class BulkImportTests(TestCase):
    def setUp(self):
        self.cfo = user_with_role('cfo1', Role.RoleType.CFO)

    def _rows(self, n):
        return [[f'S{i:05d}', f'F{i:05d}', f'مورد {i}', f'3{i:014d}', f'05{i % 100000000:08d}'] for i in range(n)]

    def test_2000_rows_with_duplicate_flagging(self):
        rows = self._rows(2000)
        rows[10][0] = rows[5][0]            # كود مكرر داخل الملف
        rows[20][3] = rows[6][3]            # رقم ضريبي مكرر داخل الملف
        rows[30][2] = ''                    # اسم ناقص
        rows[40][3] = '123'                 # رقم ضريبي غير صالح
        Supplier.objects.create(name='موجود', code=rows[50][0], tax_number='')   # مكرر مع القاعدة

        job = importer.stage(make_xlsx(rows), 'big.xlsx', self.cfo)
        self.assertEqual(job.total_rows, 2000)
        self.assertEqual(job.duplicate_rows, 3)    # الصفوف 10 و20 و50
        self.assertEqual(job.error_rows, 2)        # الصفوف 30 و40
        self.assertEqual(job.valid_rows, 1995)
        # المعاينة لا تكتب شيئًا
        self.assertEqual(Supplier.objects.count(), 1)

        job = importer.commit(job, self.cfo)
        self.assertEqual(job.created_count, 1995)
        self.assertEqual(Supplier.objects.count(), 1996)
        self.assertTrue(SupplierContact.objects.filter(is_primary=True).exists())
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.IMPORT).count(), 1)

    def test_commit_twice_rejected(self):
        job = importer.stage(make_xlsx(self._rows(3)), 'a.xlsx', self.cfo)
        importer.commit(job, self.cfo)
        with self.assertRaises(ValueError):
            importer.commit(job, self.cfo)

    def test_missing_columns(self):
        with self.assertRaises(importer.ImportFileError):
            importer.stage(make_xlsx([['x']], headers=['عمود غريب']), 'bad.xlsx', self.cfo)

    def test_multiple_phones_become_contacts(self):
        rows = [['S1', '', 'مورد', '', '0501234567, 0559876543']]
        job = importer.commit(importer.stage(make_xlsx(rows), 'p.xlsx', self.cfo), self.cfo)
        s = Supplier.objects.get(code='S1')
        self.assertEqual(s.contacts.count(), 2)
        self.assertEqual(s.contacts.filter(is_primary=True).count(), 1)
        self.assertEqual(job.created_count, 1)

    def test_db_unique_constraints(self):
        from django.db import IntegrityError, transaction
        Supplier.objects.create(name='a', code='1', tax_number='300000000000003')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Supplier.objects.create(name='b', code='2', tax_number='300000000000003')
        # الرقم الضريبي الفارغ لا يتعارض
        Supplier.objects.create(name='c', code='3')
        Supplier.objects.create(name='d', code='4')


class SupplierAccessTests(TestCase):
    def test_accountant_cannot_import(self):
        u = user_with_role('acc1', Role.RoleType.ACCOUNTANT)
        self.client.force_login(u)
        resp = self.client.get(reverse('suppliers:import'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('dashboard'))

    def test_cs_supervisor_cannot_create_supplier(self):
        u = user_with_role('cs1', Role.RoleType.CS_SUPERVISOR)
        self.client.force_login(u)
        self.client.post(reverse('suppliers:create'), {'name': 'x', 'code': 'x1'})
        self.assertFalse(Supplier.objects.exists())

    def test_cfo_can_upload_and_confirm(self):
        u = user_with_role('cfo2', Role.RoleType.CFO)
        self.client.force_login(u)
        f = make_xlsx([['S1', '', 'مورد', '', '']])
        f.name = 's.xlsx'
        resp = self.client.post(reverse('suppliers:import'), {'file': f})
        job = SupplierImportJob.objects.get()
        self.assertRedirects(resp, reverse('suppliers:import_preview', args=[job.pk]))
        self.client.post(reverse('suppliers:import_confirm', args=[job.pk]))
        self.assertTrue(Supplier.objects.filter(code='S1').exists())

    def test_supplier_create_update_audited_and_duplicates_rejected(self):
        u = user_with_role('mgr1', Role.RoleType.ACCOUNTANT)
        self.client.force_login(u)
        self.client.post(reverse('suppliers:create'), {'name': 'أ', 'code': 'A1', 'tax_number': '300000000000003'})
        s = Supplier.objects.get(code='A1')
        self.client.post(reverse('suppliers:create'), {'name': 'ب', 'code': 'B1', 'tax_number': '300000000000003'})
        self.assertFalse(Supplier.objects.filter(code='B1').exists())
        self.client.post(reverse('suppliers:update', args=[s.pk]), {'name': 'أ جديد', 'code': 'A1',
                                                                   'tax_number': '300000000000003'})
        log = AuditLog.objects.get(action=AuditLog.Action.UPDATE)
        self.assertEqual(log.previous_state, {'name': 'أ'})
        self.assertEqual(log.new_state, {'name': 'أ جديد'})
        self.assertEqual(log.actor_username, 'mgr1')
