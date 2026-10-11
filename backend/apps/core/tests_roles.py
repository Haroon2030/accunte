"""
الأدوار الخمسة: مدير النظام، المدير المالي، مشرف الدعم، المطابق، المورد. لا أثر للأدوار القديمة في الكود،
وترحيل البيانات ينقل المستخدمين وأنواع الخدمات بأمان.
"""
import importlib
import re
from io import StringIO
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.core.models import Role, UserProfile
from apps.servicedesk.models import ServiceType

User = get_user_model()
RETIRED = ('manager', 'auditor', 'branch_employee', 'cs_agent', 'payment_officer')


class FiveRolesTests(TestCase):
    def test_exactly_five_roles(self):
        self.assertEqual(set(Role.RoleType.values), {'admin', 'cfo', 'cs_supervisor', 'accountant', 'supplier'})

    def test_labels(self):
        labels = dict(Role.RoleType.choices)
        self.assertEqual((labels['accountant'], labels['cs_supervisor'], labels['supplier']),
                         ('مطابق', 'مشرف الدعم', 'مورد (بوابة الموردين)'))

    def test_setup_roles_creates_only_these(self):
        call_command('setup_roles', stdout=StringIO())
        self.assertEqual(set(Role.objects.values_list('role_type', flat=True)),
                         {'admin', 'cfo', 'cs_supervisor', 'accountant', 'supplier'})

    def test_no_code_refers_to_a_retired_role(self):
        pattern = re.compile(r"\b(?:RT|RoleType)\.(MANAGER|AUDITOR|BRANCH_EMPLOYEE|CS_AGENT|PAYMENT_OFFICER)\b|"
                             r"['\"](?:" + '|'.join(RETIRED) + r")['\"]")
        offenders = []
        for path in Path(settings.BASE_DIR, 'apps').rglob('*.py'):
            if 'migrations' in path.parts or path.name.startswith('tests'):
                continue
            for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f'{path.name}:{n}')
        self.assertEqual(offenders, [])


class RetireRolesMigrationTests(TestCase):
    def role(self, role_type, name):
        return Role.objects.create(role_type=role_type, name=name)

    def user(self, name, role):
        u = User.objects.create_user(name, password='x-Pass-12345')
        UserProfile.objects.create(user=u, role=role)
        return u

    def test_users_and_roles_are_migrated(self):
        cfo = Role.objects.filter(role_type='cfo').first() or self.role('cfo', 'المدير المالي')
        retired = {t: self.role(t, f'old-{t}') for t in RETIRED}
        manager = self.user('m', retired['manager'])
        others = [self.user(f'u_{t}', retired[t]) for t in RETIRED if t != 'manager']
        keeper = self.user('keeper', cfo)

        importlib.import_module('apps.core.migrations.0009_five_roles').retire_roles(django_apps, None)

        manager.profile.refresh_from_db()
        self.assertEqual(manager.profile.role, cfo)                       # المدير يصبح مديرًا ماليًا
        for u in others:                                                  # لا صلاحيات أوسع تلقائيًا
            u.profile.refresh_from_db()
            self.assertIsNone(u.profile.role, u.username)
        keeper.profile.refresh_from_db()
        self.assertEqual(keeper.profile.role, cfo)
        self.assertFalse(Role.objects.filter(role_type__in=RETIRED).exists())
        self.assertEqual(User.objects.count(), 6)                         # لا يُحذف أي مستخدم

    def test_service_types_are_remapped(self):
        t = ServiceType.objects.create(
            code='legacy', name='قديم', destination_role='cs_agent', escalation_role='manager',
            create_roles=['cs_agent', 'manager', 'cfo', 'auditor'], handle_roles=['payment_officer', 'accountant'])
        importlib.import_module('apps.servicedesk.migrations.0005_five_roles').retire_roles(django_apps, None)
        t.refresh_from_db()
        self.assertEqual((t.destination_role, t.escalation_role), ('cs_supervisor', 'cfo'))
        self.assertEqual(t.create_roles, ['cs_supervisor', 'cfo'])
        self.assertEqual(t.handle_roles, ['cs_supervisor', 'accountant'])

    def test_seeded_types_use_only_current_roles(self):
        valid = set(Role.RoleType.values)
        for t in ServiceType.objects.all():
            self.assertLessEqual({t.destination_role, t.escalation_role, *t.create_roles, *t.handle_roles}, valid, t.code)
