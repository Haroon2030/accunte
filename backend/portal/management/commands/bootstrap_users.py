"""Create the first admin at deploy time. Nothing to configure.

On the very first deploy (the database has no accounts) it creates one admin:
  username  ADMIN_USERNAME, default "1"
  password  ADMIN_PASSWORD, default "526400"
The admin must choose a new password at first login, then creates everyone else from the users page.
Later deploys leave it alone once someone has signed in (or deleted it), except that an admin nobody has used yet
is kept on the current default password.

BOOTSTRAP_USERS (optional JSON list) creates extra accounts that do not exist yet:
  [{"username": "4", "role": "supplier", "name": "...", "org": "...", "code": "S-1001", "taxNo": "...", "password": "..."}]
Existing accounts are never touched and their passwords are never reset here.
"""
import json
import os

from django.core.management.base import BaseCommand, CommandError

from portal.models import User
from portal.validators import normalize_digits

ROLES = {r for r, _ in User.ROLES}
DEFAULT_ADMIN_PASSWORD = '526400'


class Command(BaseCommand):
    help = 'Create the first admin (and any BOOTSTRAP_USERS accounts) that do not exist yet.'

    def handle(self, *args, **opts):
        raw = os.environ.get('BOOTSTRAP_USERS', '').strip()
        if raw:
            self.create_listed(raw)
        self.create_first_admin(refresh=not raw)

    def create_first_admin(self, refresh=True):
        username = normalize_digits(os.environ.get('ADMIN_USERNAME') or '1').strip().lower()
        pw = os.environ.get('ADMIN_PASSWORD') or DEFAULT_ADMIN_PASSWORD
        unused = User.objects.filter(username=username, role=User.ADMIN, last_login__isnull=True, must_change_password=True).first()
        if unused and refresh:
            # created by an earlier deploy and nobody has signed in yet: keep it in step with the current default
            unused.set_password(pw)
            unused.save(update_fields=['password'])
            self.stdout.write(f'First admin "{username}" has not been used yet; its starting password was refreshed.')
            return
        if User.objects.exists():
            self.stdout.write('Accounts already exist; the first admin is not recreated.')
            return
        user = User(username=username, role=User.ADMIN, name='مدير النظام', org='أسواق الراشد',
                    is_staff=True, is_superuser=True, must_change_password=True)
        user.set_password(pw)
        user.save()
        self.stdout.write(self.style.SUCCESS(f'First admin "{username}" created; a new password is required at first login.'))

    def create_listed(self, raw):
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
