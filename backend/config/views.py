"""تقديم صفحتي الواجهة (HTML ثابت) مع رمز CSRF، وفحص صحة بسيط."""
from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

_cache = {}
BASE_TAG = '<base href="/static/frontend/">'


def _html(name):
    """يقرأ ملف الواجهة ويحقن <base> كي تُحلّ المسارات النسبية (css/ و js/) على /static/frontend/."""
    path = settings.FRONTEND_DIR / name
    try:
        mtime = path.stat().st_mtime
    except OSError:
        raise Http404
    hit = _cache.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    html = path.read_text(encoding='utf-8')
    if '<base ' not in html:
        html = html.replace('<head>', '<head>\n' + BASE_TAG, 1)
    _cache[name] = (mtime, html)
    return html


@never_cache
@ensure_csrf_cookie
def staff_page(request):
    return HttpResponse(_html('index.html'), content_type='text/html; charset=utf-8')


@never_cache
@ensure_csrf_cookie
def supplier_page(request):
    return HttpResponse(_html('supplier.html'), content_type='text/html; charset=utf-8')


def healthz(request):
    return HttpResponse('ok', content_type='text/plain')
