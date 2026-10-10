"""
تخزين خاص للمرفقات (مطابقة، مقترحات دفع، طلبات خدمة).

- عند USE_R2=True تُحفظ في Cloudflare R2 (bucket خاص) داخل مجلد R2_PREFIX.
- وإلا تُحفظ على القرص خارج MEDIA_ROOT. في الحالتين لا يوجد رابط عام: التنزيل يمر عبر serve_file بعد فحص الصلاحية.
- تخزين S3 آخر: اضبط RECONCILIATION_STORAGE بمسار الكلاس.
"""
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.utils.module_loading import import_string


def get_private_storage():
    path = getattr(settings, 'RECONCILIATION_STORAGE', None)
    if path:
        return import_string(path)()
    if getattr(settings, 'USE_R2', False):
        from storages.backends.s3 import S3Storage

        from config.r2 import storage_options
        return S3Storage(**storage_options(settings))
    root = getattr(settings, 'PRIVATE_MEDIA_ROOT', settings.BASE_DIR / 'private_media')
    return FileSystemStorage(location=str(root), base_url=None)


private_storage = get_private_storage


def serve_file(fieldfile, filename):
    """يخدم ملفًا لمستخدم تحقق الاستدعاء من صلاحيته مسبقًا.

    - الوضع الافتراضي (وكذلك القرص المحلي): يمرّر التطبيق البايتات بنفسه، فلا يرى المستخدم رابط التخزين.
    - R2 مع R2_PROXY_MEDIA=false: يُعاد توجيه المستخدم إلى رابط موقّع مؤقت (R2_SIGNED_URL_EXPIRE).
    """
    if getattr(settings, 'USE_R2', False) and not getattr(settings, 'R2_PROXY_MEDIA', True):
        disposition = "attachment; filename*=UTF-8''" + quote(filename)
        try:
            url = fieldfile.storage.url(fieldfile.name, parameters={'ResponseContentDisposition': disposition},
                                        expire=getattr(settings, 'R2_SIGNED_URL_EXPIRE', 3600))
        except Exception:
            raise Http404
        return HttpResponseRedirect(url)
    try:
        handle = fieldfile.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404
    return FileResponse(handle, as_attachment=True, filename=filename)
