"""
بوابة الموردين: شاشة واحدة يدخلها المورد فقط، يطلب منها الخدمة التي يريدها ويتابع طلباته.

من الخدمات: التحدث مع الدعم عبر واتساب (يرد المساعد الآلي أولًا ثم فريق الدعم من صندوق واتساب).
الوصول محصور بحساب المورد المرتبط بمورد، والحارس (apps.core.portal_guard) يغلق كل ما عداها.
"""
import urllib.parse
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import format_html

from apps.core.access import is_portal_supplier

from apps.whatsapp import client as wa_client

from . import services
from .models import ServiceRequest, ServiceType
from .services import RequestError


def supplier_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_portal_supplier(request.user):
            return redirect('dashboard')
        if request.user.profile.supplier_id is None:
            return render(request, 'pages/portal/unlinked.html', status=403)
        return view(request, *args, **kwargs)
    return wrapper


def _services():
    return ServiceType.objects.filter(is_active=True, portal_menu=True).order_by('sort_order', 'name')


def support_number():
    """رقم واتساب الدعم: المضبوط في الإعدادات، وإلا الرقم المربوط فعلًا بالنظام (يُخزَّن 10 دقائق)."""
    number = ''.join(ch for ch in (settings.WHATSAPP_SUPPORT_NUMBER or '') if ch.isdigit())
    if number or not (settings.WHATSAPP_ENABLED and wa_client.is_configured()):
        return number
    number = cache.get('wa_support_number')
    if number is None:
        number = wa_client.instance_info().get('number', '')
        cache.set('wa_support_number', number, 600 if number else 60)
    return number


def whatsapp_link():
    """رابط محادثة واتساب الدعم، أو None إن لم يتوفر رقم."""
    number = support_number()
    if not number:
        return None
    return 'https://wa.me/' + number + '?text=' + urllib.parse.quote('مرحبا')


def _my_requests(request):
    return ServiceRequest.objects.filter(supplier_id=request.user.profile.supplier_id).select_related('service_type')


@supplier_required
def home(request):
    return render(request, 'pages/portal/home.html', {
        'supplier': request.user.profile.supplier, 'service_types': _services(), 'wa_link': whatsapp_link(),
        'recent': _my_requests(request)[:5],
    })


@supplier_required
def request_new(request, code):
    stype = get_object_or_404(_services(), code=code)
    errors = []
    post = request.POST if request.method == 'POST' else {}
    if request.method == 'POST':
        try:
            req = services.create_from_portal(request.user, stype, post.get('subject', ''), post.get('details', ''),
                                              getter=post.get)
        except RequestError as exc:
            errors.append(str(exc))
        else:
            messages.success(request, format_html('تم استلام طلبك. رقمه المرجعي {}', req.reference))
            return redirect('portal:detail', pk=req.pk)
    return render(request, 'pages/portal/form.html', {
        'stype': stype, 'schema': stype.field_schema or [], 'errors': errors, 'post': post,
        'supplier': request.user.profile.supplier,
    })


@supplier_required
def requests_list(request):
    return render(request, 'pages/portal/list.html', {
        'supplier': request.user.profile.supplier, 'requests': _my_requests(request)[:100]})


@supplier_required
def request_detail(request, pk):
    req = get_object_or_404(_my_requests(request), pk=pk)          # طلبات هذا المورد فقط
    return render(request, 'pages/portal/detail.html', {
        'supplier': request.user.profile.supplier, 'r': req, 'fields': services.labelled_data(req),
        'history': req.history.all(),
    })
