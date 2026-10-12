"""Create or update one account. The password is read from the environment or a prompt,
never from the command line, so it does not end up in shell history.

  PORTAL_PASSWORD=... python manage.py create_portal_user --username 1 --role admin --name "مدير النظام"
"""
import getpass
import os

from django.core.management.base import BaseCommand, CommandError

from portal.models import User


class Command(BaseCommand):
    help = 'Create or update a portal account (idempotent).'

    def add_arguments(self, p):
        p.add_argument('--username', required=True)
        p.add_argument('--role', required=True, choices=[r for r, _ in User.ROLES])
        p.add_argument('--name', required=True)
        p.add_argument('--org', default='')
        p.add_argument('--code', default='')
        p.add_argument('--tax-no', default='')
        p.add_argument('--force-change', action='store_true', help='ask for a new password at first login')

    def handle(self, *a, **o):
        pw = os.environ.get('PORTAL_PASSWORD') or getpass.getpass('Password: ')
        if not pw:
            raise CommandError('password is empty')
        org = o['org'] or ('أسواق الرشيد' if o['role'] != 'supplier' else '')
        u, created = User.objects.get_or_create(username=o['username'], defaults={'name': o['name']})
        u.name, u.role, u.org = o['name'], o['role'], org
        u.code, u.tax_no = (o['code'] or None), o['tax_no']
        u.must_change_password = o['force_change']
        u.is_active = True
        u.set_password(pw)
        u.save()
        self.stdout.write(('created ' if created else 'updated ') + f"{u.username} ({u.role})")
