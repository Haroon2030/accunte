"""Create the first accounts at deploy time from the BOOTSTRAP_USERS environment variable.

BOOTSTRAP_USERS is a JSON list, set in the hosting panel (never committed):
  [{"username": "1", "role": "admin", "name": "مدير النظام", "password": "..."},
   {"username": "4", "role": "supplier", "name": "مسؤول المورد", "org": "اسم المورد", "code": "S-1001",
    "taxNo": "300000000000003", "password": "...", "forceChange": false}]

Safe to run on every start: an account that already exists is left untouched (its password is never reset here).
forceChange defaults to true: the person must choose their own password at first login.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError

from portal.models import User
from portal.validators import normalize_digits

ROLES = {r for r, _ in User.ROLES}


class Command(BaseCommand):
    help = 'Create accounts listed in BOOTSTRAP_USERS that do not exist yet.'

    def handle(self, *args, **opts):
        raw = os.environ.get('BOOTSTRAP_USERS', '').strip()
        if not raw:
            self.stdout.write('BOOTSTRAP_USERS is not set; no accounts to create.')
            return
        try:
            entries = json.loads(raw)
            assert isinstance(entries, list)
        except (ValueError, AssertionError):
            raise CommandError('BOOTSTRAP_USERS must be a JSON list of account objects.')
        for i, e in enumerate(entries, 1):
            username = normalize_digits(e.get('username')).strip().lower()
            role, pw = e.get('role'), e.get('password') or ''
            if not username or role not in ROLES or not pw:
                raise CommandError(f'BOOTSTRAP_USERS entry {i}: username, role (admin/manager/matcher/supplier) and password are required.')
            if User.objects.filter(username=username).exists():
                self.stdout.write(f'{username}: exists, left unchanged.')
                continue
            code = (e.get('code') or '').strip() or None
            if code and User.objects.filter(code__iexact=code).exists():
                raise CommandError(f'BOOTSTRAP_USERS entry {i}: supplier code {code} is already used.')
            user = User(
                username=username, role=role, name=e.get('name') or username,
                org=e.get('org') or ('' if role == User.SUPPLIER else 'أسواق الراشد'),
                code=code, tax_no=normalize_digits(e.get('taxNo')),
                must_change_password=bool(e.get('forceChange', True)))
            user.set_password(pw)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'{username}: created ({role}).'))
