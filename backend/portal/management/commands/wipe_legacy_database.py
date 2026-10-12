"""One-time cleanup before the first migrate of this app on a database that still holds the OLD app's tables.

Runs on every container start but acts only when the database is recognisably the old app's
(it has accounts_userprofile) and this app's own table (portal_user) does not exist yet.
After the first successful migrate that second condition is false forever, so a restart never wipes live data.
A database holding unrelated tables is refused unless RESET_DATABASE=DELETE_ALL_DATA is set.
Files the old app stored in R2 are not touched.
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

MARKER_TABLE = 'portal_user'
OLD_APP_TABLE = 'accounts_userprofile'


class Command(BaseCommand):
    help = 'Drop every table of the old app once, before the first migrate.'

    def handle(self, *args, **opts):
        tables = connection.introspection.table_names()
        if MARKER_TABLE in tables:
            self.stdout.write('Database already belongs to this app; nothing to wipe.')
            return
        if not tables:
            self.stdout.write('Database is empty; nothing to wipe.')
            return
        if OLD_APP_TABLE not in tables and os.environ.get('RESET_DATABASE') != 'DELETE_ALL_DATA':
            raise CommandError(
                f'The database holds {len(tables)} tables that do not look like the old app. Refusing to drop them. '
                'Set RESET_DATABASE=DELETE_ALL_DATA for one deploy if you really want them deleted.')
        self.stdout.write(f'Dropping {len(tables)} old tables...')
        vendor = connection.vendor
        with connection.cursor() as cur:
            if vendor == 'mysql':
                cur.execute('SET FOREIGN_KEY_CHECKS = 0')
            elif vendor == 'sqlite':
                cur.execute('PRAGMA foreign_keys = OFF')
            for t in tables:
                cur.execute('DROP TABLE IF EXISTS ' + connection.ops.quote_name(t))
            if vendor == 'mysql':
                cur.execute('SET FOREIGN_KEY_CHECKS = 1')
            elif vendor == 'sqlite':
                cur.execute('PRAGMA foreign_keys = ON')
        self.stdout.write(self.style.SUCCESS('Old tables dropped. migrate will now build the new schema.'))
