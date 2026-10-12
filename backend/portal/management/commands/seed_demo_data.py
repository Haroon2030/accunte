"""Demo operations in every shape, clearly marked "[تجريبي]", and removable in one command.

  python manage.py seed_demo_data            # add demo requests, complaints, chats and files
  python manage.py seed_demo_data --clear    # delete only what this command created

Uses the supplier and matcher accounts that already exist; it creates no accounts.
Safe to run twice: it adds nothing while demo records are still there (clear first to start over).
"""
import io
import zipfile
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from portal.models import SLA_DAYS, Attachment, Complaint, MatchRequest, Message, User

TAG = '[تجريبي]'

PDF = (b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n'
       b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n'
       b'4 0 obj<</Length 44>>stream\nBT /F1 14 Tf 20 60 Td (Demo statement) Tj ET\nendstream\nendobj\n'
       b'5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n')
PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a52dd4f00000000049454e44ae426082')
CSV = 'التاريخ,رقم المستند,البيان,مدين,دائن\n01/09/2026,INV-1001,فاتورة مشتريات,0,12500.00\n05/09/2026,PAY-2001,سداد,8000.00,0\n'.encode('utf-8-sig')


def xlsx_bytes():
    """A minimal but valid one-sheet workbook."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Statement" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Date</t></is></c><c r="B1" t="inlineStr"><is><t>Doc</t></is></c><c r="C1" t="inlineStr"><is><t>Amount</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>2026-09-01</t></is></c><c r="B2" t="inlineStr"><is><t>INV-1001</t></is></c><c r="C2"><v>12500</v></c></row></sheetData></worksheet>')
    return buf.getvalue()


FILES = {
    'pdf': ('كشف-حساب-تجريبي.pdf', PDF),
    'xlsx': ('كشف-حساب-تجريبي.xlsx', None),
    'csv': ('كشف-حساب-تجريبي.csv', CSV),
    'png': ('إشعار-سداد-تجريبي.png', PNG),
}


class Command(BaseCommand):
    help = 'Create (or with --clear remove) demo requests and complaints in every stage.'

    def add_arguments(self, p):
        p.add_argument('--clear', action='store_true', help='delete the demo records created by this command')

    # ---------------------------------------------------------------- helpers
    def attach(self, name_key, user, **parent):
        name, data = FILES[name_key]
        data = data if data is not None else xlsx_bytes()
        a = Attachment(original_name=name, size=len(data), uploaded_by=user, **parent)
        a.file.save(name, ContentFile(data), save=False)
        a.save()
        return a

    def say(self, req_or_c, kind, text, at, sender=None, files=()):
        field = {'request': 'request', 'complaint': 'complaint'}[req_or_c.__class__.__name__.lower().replace('matchrequest', 'request')]
        m = Message.objects.create(**{field: req_or_c}, kind=kind, sender=sender, text=text, created_at=at)
        for f in files:
            self.attach(f, sender, message=m)
        return m

    def clear(self):
        reqs = MatchRequest.objects.filter(notes__startswith=TAG)
        comps = Complaint.objects.filter(subject__startswith=TAG)
        files = list(Attachment.objects.filter(request__in=reqs)) + list(Attachment.objects.filter(message__request__in=reqs)) + \
            list(Attachment.objects.filter(message__complaint__in=comps))
        for a in files:
            try:
                a.file.delete(save=False)
            except Exception as exc:  # a file that is already gone must not block the cleanup
                self.stderr.write(f'could not delete {a.original_name}: {exc}')
        n1, n2 = comps.count(), reqs.count()
        comps.delete()
        reqs.delete()
        self.stdout.write(self.style.SUCCESS(f'Removed {n2} demo requests and {n1} demo complaints (with their messages and files).'))

    # ---------------------------------------------------------------- main
    @transaction.atomic
    def handle(self, *a, **o):
        if o['clear']:
            return self.clear()
        if MatchRequest.objects.filter(notes__startswith=TAG).exists() or Complaint.objects.filter(subject__startswith=TAG).exists():
            self.stdout.write('Demo data is already there. Run with --clear first to start over.')
            return
        sups = list(User.objects.filter(role=User.SUPPLIER, is_active=True).order_by('id')[:3])
        if not sups:
            raise CommandError('Create at least one supplier account first (users page), then run this again.')
        matchers = list(User.objects.filter(role__in=[User.MATCHER, User.MANAGER, User.ADMIN], is_active=True).order_by('role', 'id')[:2])
        mgr = User.objects.filter(role__in=[User.MANAGER, User.ADMIN], is_active=True).order_by('role', 'id').first()
        now = timezone.now()
        pick = lambda i, seq: seq[i % len(seq)] if seq else None  # noqa: E731

        # (period, stage, age in days, with matcher?, difference, chat?, statement file kind)
        plan = [
            ('أغسطس 2026', 1, 0, False, None, False, 'pdf'),
            ('سبتمبر 2026', 1, 7, False, None, False, 'xlsx'),      # waiting too long: late
            ('الربع الثالث 2026', 2, 2, True, 7340, False, 'csv'),
            ('يوليو 2026', 2, 8, True, 10260, False, 'pdf'),        # matching and late
            ('سبتمبر 2026', 3, 3, True, 8070, True, 'xlsx'),        # open dialogue
            ('أغسطس 2026', 3, 6, True, 5150, True, 'png'),          # dialogue and late
            ('الربع الثاني 2026', 4, 12, True, 0, True, 'pdf'),     # done, no difference
            ('يونيو 2026', 4, 20, True, 1250.5, True, 'csv'),       # done, with difference
        ]
        reqs = []
        for i, (period, stage, age, has_m, diff, chat, kind) in enumerate(plan):
            sup = pick(i, sups)
            created = now - timedelta(days=age, hours=2)
            r = MatchRequest.objects.create(
                supplier=sup, period=period, notes=f'{TAG} طلب مطابقة لأغراض التجربة', stage=stage,
                matcher=pick(i, matchers) if has_m else None, diff=diff, due_at=created + timedelta(days=SLA_DAYS),
                created_at=created, reached={'1': created.isoformat()})
            r.number = f'MT-{created:%y%m}-{r.pk:04d}'
            reached = {'1': created}
            for s in range(2, stage + 1):
                reached[str(s)] = created + timedelta(days=min(age, s - 1), hours=s)
            r.reached = {k: v.isoformat() for k, v in reached.items()}
            r.save()
            self.attach(kind, sup, request=r, kind=Attachment.STATEMENT)
            notes = {2: 'بدأت المطابقة على كشف الحساب', 3: 'فُتحت قناة المراسلة مع المورد', 4: 'أُغلقت المراسلة وأُنجز الطلب'}
            for s in range(2, stage + 1):
                Message.objects.create(request=r, kind=Message.SYSTEM, text=notes[s], created_at=reached[str(s)])
            if chat:
                m = pick(i, matchers)
                t0 = reached['3']
                self.say(r, Message.MATCHER, 'وجدنا فرقاً في فاتورتين. أرسل لنا نسخة الفاتورة والإشعار.', t0 + timedelta(hours=1), m)
                self.say(r, Message.SUPPLIER, 'مرفق نسخة الفاتورة. الإشعار أُرسل بالبريد أمس.', t0 + timedelta(hours=5), sup, files=['pdf'])
                self.say(r, Message.MATCHER, 'استلمنا المستند، سنحدّث القيد ونعود إليك.', t0 + timedelta(hours=9), m)
                if stage == 3 and i % 2 == 0:
                    self.say(r, Message.SUPPLIER, 'شكراً. هذا إثبات تحويل الدفعة.', t0 + timedelta(hours=20), sup, files=['png'])
            reqs.append(r)

        # complaints: every stage, every category style, linked and unlinked, with chat and files
        comp_plan = [
            ('دفعة غير مستلمة', 'دفعة سبتمبر لم تصل رغم اعتمادها', 1, 0, True, ['pdf']),
            ('تأخر في السداد', 'تأخر اعتماد الدفعة بعد انتهاء المطابقة', 1, 1, False, []),
            ('فرق في الرصيد لم يُحسم', 'فرق بين كشفنا وكشفكم في فواتير أغسطس', 2, 3, True, ['xlsx']),
            ('تأخر الرد على الطلبات', 'لم يصلنا رد على طلب المطابقة منذ أسبوع', 2, 5, True, []),
            ('تعامل موظف', 'ملاحظة على أسلوب التعامل في الاتصال الأخير', 3, 9, False, ['png']),
            ('أخرى', 'استفسار عن موعد صرف المستحقات', 3, 15, False, ['csv']),
        ]
        for i, (cat, subject, stage, age, link, files) in enumerate(comp_plan):
            sup = pick(i, sups)
            created = now - timedelta(days=age, hours=3)
            c = Complaint.objects.create(
                supplier=sup, category=cat, subject=f'{TAG} {subject}', stage=stage, created_at=created,
                related=next((r for r in reqs if r.supplier_id == sup.pk), None) if link else None, reached={'1': created.isoformat()})
            c.number = f'SH-{created:%y%m}-{c.pk:04d}'
            reached = {'1': created}
            for s in range(2, stage + 1):
                reached[str(s)] = created + timedelta(days=min(age, s), hours=s)
            c.reached = {k: v.isoformat() for k, v in reached.items()}
            c.save()
            self.say(c, Message.SUPPLIER, f'{TAG} تفاصيل الشكوى: نرجو المتابعة والرد خلال أقرب وقت.', created, sup, files=files)
            if stage >= 2:
                Message.objects.create(complaint=c, kind=Message.SYSTEM, text='بدأ المدير المالي مراجعة الشكوى', created_at=reached['2'])
                self.say(c, Message.MANAGER, 'استلمنا شكواك ونراجعها مع الحسابات.', reached['2'] + timedelta(hours=2), mgr)
                self.say(c, Message.SUPPLIER, 'شكراً، بانتظار ردكم.', reached['2'] + timedelta(hours=6), sup)
            if stage == 3:
                self.say(c, Message.MANAGER, 'تمت المعالجة وصُرفت المستحقات. أُغلقت الشكوى.', reached['3'], mgr)
                Message.objects.create(complaint=c, kind=Message.SYSTEM, text='أُغلقت الشكوى بعد رد المدير المالي', created_at=reached['3'])

        self.stdout.write(self.style.SUCCESS(
            f'Created {len(reqs)} demo requests (stages 1-4, some late), {len(comp_plan)} complaints (stages 1-3), '
            f'chats and PDF / Excel / CSV / image files, for {len(sups)} supplier account(s). Remove with: --clear'))
