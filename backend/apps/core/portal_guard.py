"""
حارس بوابة الموردين: حساب المورد لا يصل إلا إلى /portal/ (وتسجيل الخروج)، مهما كان الرابط الذي يطلبه.

هذا الحد الأمني الأساسي: لا يُترك للعروض الفردية أن تتذكر استبعاد المورد، فكل مسار خارج البوابة مغلق افتراضيًا.
"""
from django.http import HttpResponseForbidden
from django.shortcuts import redirect

from .access import is_portal_supplier

ALLOWED_PREFIXES = ('/portal/', '/auth/logout/', '/static/')


class SupplierPortalGuard:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and is_portal_supplier(user):
            if not request.path.startswith(ALLOWED_PREFIXES):
                if request.method == 'GET' and 'text/html' in request.headers.get('Accept', 'text/html'):
                    return redirect('/portal/')
                return HttpResponseForbidden('غير مسموح')
        return self.get_response(request)
