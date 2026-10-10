"""
تخزين خاص للمرفقات: خارج MEDIA_ROOT ولا يُخدَّم مباشرة. التنزيل يمر عبر عرض يتحقق من الصلاحية.

للانتقال إلى تخزين متوافق مع S3 اضبط RECONCILIATION_STORAGE في الإعدادات
(مسار كلاس Storage مثل storages.backends.s3.S3Storage) وثبّت django-storages.
"""
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.module_loading import import_string


def get_private_storage():
    path = getattr(settings, 'RECONCILIATION_STORAGE', None)
    if path:
        return import_string(path)()
    root = getattr(settings, 'PRIVATE_MEDIA_ROOT', settings.BASE_DIR / 'private_media')
    return FileSystemStorage(location=str(root), base_url=None)


private_storage = get_private_storage
