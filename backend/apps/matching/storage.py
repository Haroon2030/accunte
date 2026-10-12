"""
تخزين خاص للمرفقات: Cloudflare R2 (bucket خاص) عند USE_R2=True، وإلا قرص خارج MEDIA.
لا يوجد رابط عام: التنزيل عبر serve_file بعد فحص الصلاحية.
"""
from urllib.parse import quote

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse, Http404, HttpResponseRedirect


def get_private_storage():
    if getattr(settings, 'USE_R2', False):
        from storages.backends.s3 import S3Storage

        from config.r2 import storage_options
        return S3Storage(**storage_options(settings))
    return FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT), base_url=None)


private_storage = get_private_storage


def serve_file(fieldfile, filename):
    """يخدم ملفاً تحقق الاستدعاء من صلاحية صاحبه مسبقاً."""
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
