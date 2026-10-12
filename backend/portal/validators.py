"""Password rule and upload checks, kept identical to what the UI promises."""
import os
import re

from django.conf import settings
from rest_framework.exceptions import ValidationError

TAX_RE = re.compile(r'^\d{15}$')


def check_password_rule(pw):
    if not pw or len(pw) < 8:
        raise ValidationError('كلمة المرور 8 خانات على الأقل.')
    if not re.search(r'[A-Za-z]', pw) or not re.search(r'\d', pw):
        raise ValidationError('يجب أن تحتوي حروفاً إنجليزية وأرقاماً.')


ARABIC_DIGITS = {ord(c): str(i) for i, c in enumerate('٠١٢٣٤٥٦٧٨٩')}


def normalize_digits(v):
    return re.sub(r'\s', '', str(v or '').translate(ARABIC_DIGITS))


# extension -> (leading bytes that the real file must start with, or None for plain text)
ALLOWED_UPLOADS = {
    'pdf': (b'%PDF',),
    'xlsx': (b'PK\x03\x04',),
    'xls': (b'\xd0\xcf\x11\xe0',),
    'csv': None,
    'png': (b'\x89PNG',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'webp': (b'RIFF',),
}
INLINE_TYPES = {'pdf', 'png', 'jpg', 'jpeg', 'webp'}


def extension_of(name):
    return os.path.splitext(name or '')[1].lstrip('.').lower()


def validate_upload(f):
    ext = extension_of(f.name)
    if ext not in ALLOWED_UPLOADS:
        raise ValidationError('نوع الملف غير مدعوم. المسموح: PDF أو Excel أو CSV أو صورة.')
    if f.size > settings.MAX_UPLOAD_BYTES:
        raise ValidationError('حجم الملف أكبر من 15 ميجابايت.')
    if f.size == 0:
        raise ValidationError('الملف فارغ.')
    magic = ALLOWED_UPLOADS[ext]
    if magic:
        head = f.read(8)
        f.seek(0)
        if not any(head.startswith(m) for m in magic):
            raise ValidationError('محتوى الملف لا يطابق امتداده.')
    return ext
