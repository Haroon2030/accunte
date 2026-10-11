"""
Django Template Views - واجهة الويب
"""
import math
import unicodedata

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.http import JsonResponse, HttpResponseForbidden
from functools import wraps

from apps.branches.models import Branch
from apps.banks.models import Bank
from apps.cost_centers.models import CostCenter
from apps.suppliers.models import Supplier
from apps.contracts.models import Contract
from apps.items.models import Item, ItemBatch
from apps.space_rentals.models import SpaceRental
from apps.payments.models import PaymentRequest, PaymentRequestItem
from apps.core.models import Role, Notification
from apps.core.access import SUPPLIER_MANAGE_ROLES, get_role_type, role_required
from apps.audit.models import AuditLog
from apps.audit.services import log_action, snapshot as audit_snapshot, diff as audit_diff
from apps.core.excel_export import ModernExcelBuilder
from apps.core.forms import SimplePasswordChangeForm
from apps.core.notifications import (
    mark_all_notifications_read,
    mark_notification_read,
    notify_payment_created,
    notify_payment_status_changed,
)


def _normalize_bank_name(name):
    if not name:
        return ''
    text = unicodedata.normalize('NFKC', str(name))
    return ' '.join(text.split()).casefold()


def unique_banks_for_select(banks_qs, selected_bank_id=None):
    """One entry per bank name (normalized) within each branch."""
    selected_id = int(selected_bank_id) if selected_bank_id else None
    seen = set()
    unique = []
    selected_bank = None

    for bank in banks_qs.order_by('name', 'code', 'id'):
        if selected_id and bank.id == selected_id:
            selected_bank = bank
        name_key = _normalize_bank_name(bank.name)
        if not name_key:
            continue
        branch_key = bank.branch_id or 0
        dedupe_key = (branch_key, name_key)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique.append(bank)

    if selected_bank and not any(b.id == selected_bank.id for b in unique):
        unique.append(selected_bank)
        unique.sort(key=lambda b: ((b.name or '').casefold(), b.code or ''))

    return unique


def banks_json_for_payment(banks_qs, selected_bank_id=None):
    return [
        {
            'id': str(bank.id),
            'name': bank.name,
            'code': bank.code or '',
            'branch_id': str(bank.branch_id) if bank.branch_id else '',
            'account_number': bank.account_number or '',
            'analytical_number': bank.analytical_number or '',
        }
        for bank in unique_banks_for_select(banks_qs, selected_bank_id)
    ]


def unique_suppliers_for_select(suppliers_qs, limit=20):
    """One entry per supplier name (normalized)."""
    seen = set()
    unique = []
    for supplier in suppliers_qs.order_by('name', 'code', 'id'):
        name_key = _normalize_bank_name(supplier.name)
        if not name_key or name_key in seen:
            continue
        seen.add(name_key)
        unique.append({
            'id': str(supplier.id),
            'code': supplier.code or '',
            'name': supplier.name or '',
        })
        if len(unique) >= limit:
            break
    return unique


def _supplier_ids_with_unpaid_item_batches():
    return ItemBatch.objects.filter(
        payment_status=ItemBatch.PaymentStatus.UNPAID,
    ).values_list('supplier_id', flat=True).distinct()


def suppliers_eligible_for_payment_qs():
    """موردون مسموح إدراجهم في طلب دفع (بدون ملف أصناف غير مدفوع)."""
    return Supplier.objects.filter(is_active=True).exclude(
        id__in=_supplier_ids_with_unpaid_item_batches(),
    )


def supplier_eligible_for_payment(supplier_id):
    if not supplier_id:
        return True
    return not ItemBatch.objects.filter(
        supplier_id=supplier_id,
        payment_status=ItemBatch.PaymentStatus.UNPAID,
    ).exists()


def _validate_payment_suppliers(supplier_ids):
    """يرجع أسماء الموردين غير المسموح بهم في طلب الدفع."""
    blocked = []
    seen = set()
    for supplier_id in supplier_ids:
        if not supplier_id or supplier_id in seen:
            continue
        seen.add(supplier_id)
        if not supplier_eligible_for_payment(supplier_id):
            name = Supplier.objects.filter(pk=supplier_id).values_list('name', flat=True).first()
            blocked.append(name or f'#{supplier_id}')
    return blocked


# =============================================================================
# Custom Decorators
# =============================================================================

def admin_required(view_func):
    """تحقق من أن المستخدم لديه دور أدمن"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('auth:login')

        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        try:
            user_role = request.user.profile.role
            if user_role and user_role.role_type == Role.RoleType.ADMIN:
                return view_func(request, *args, **kwargs)
        except Exception:
            pass

        messages.error(request, 'ليس لديك صلاحية للوصول إلى هذه الصفحة')
        return redirect('dashboard')
    return wrapper


class AdminRequiredMixin:
    """Mixin للتحقق من دور الأدمن في CBVs"""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('auth:login')

        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        try:
            user_role = request.user.profile.role
            if user_role and user_role.role_type == Role.RoleType.ADMIN:
                return super().dispatch(request, *args, **kwargs)
        except Exception:
            pass

        messages.error(request, 'ليس لديك صلاحية للوصول إلى هذه الصفحة')
        return redirect('dashboard')


# =============================================================================
# Authentication Views
# =============================================================================

def login_view(request):
    """صفحة تسجيل الدخول"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = (request.POST.get('password') or '').strip()
        remember = request.POST.get('remember')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            log_action(AuditLog.Action.LOGIN, user, actor=user, request=request)
            if not remember:
                request.session.set_expiry(0)
            messages.success(request, f'مرحباً {user.get_full_name() or user.username}')
            return redirect('dashboard')
        else:
            log_action(AuditLog.Action.LOGIN_FAILED, entity_type='auth.User', entity_repr=username[:150],
                       request=request)
            messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة')
    
    return render(request, 'auth/login.html')


def logout_view(request):
    """تسجيل الخروج"""
    if request.method == 'POST' or request.method == 'GET':
        if request.user.is_authenticated:
            log_action(AuditLog.Action.LOGOUT, request.user)
        logout(request)
        messages.success(request, 'تم تسجيل الخروج بنجاح')
        return redirect('auth:login')
    return redirect('dashboard')


@login_required
def change_password_view(request):
    """تغيير كلمة مرور المستخدم الحالي"""
    user = User.objects.get(pk=request.user.pk)
    form = SimplePasswordChangeForm(user, request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            updated_user = form.save()
            update_session_auth_hash(request, updated_user)
            messages.success(request, 'تم تغيير كلمة المرور بنجاح')
            return redirect('dashboard')

        first_error = next(iter(form.errors.values()), None)
        if first_error:
            messages.error(request, first_error[0])

    return render(request, 'auth/change_password.html', {
        'form': form,
        'username': user.username,
    })


# =============================================================================
# Home (يوجّه كل مستخدم إلى صفحة عمله حسب دوره)
# =============================================================================

# الصفحة الرئيسية لكل دور. يجب أن تسمح الصفحة المقصودة لهذا الدور، وإلا دار التحويل (رفض ← / ← رفض)
HOME_BY_ROLE = {
    Role.RoleType.ADMIN: 'reconciliation:executive',
    Role.RoleType.CFO: 'reconciliation:executive',
    Role.RoleType.ACCOUNTANT: 'reconciliation:list',
    Role.RoleType.CS_SUPERVISOR: 'whatsapp_inbox:inbox',
    Role.RoleType.SUPPLIER: 'portal:home',
}
DEFAULT_HOME = 'payments:list'


@login_required
def dashboard_view(request):
    """المسار `/` (اسمه dashboard): لا يعرض صفحة بنفسه، بل يحوّل إلى الصفحة الرئيسية للدور."""
    return redirect(HOME_BY_ROLE.get(get_role_type(request.user), DEFAULT_HOME))


# =============================================================================
# Branch Views
# =============================================================================

class BranchListView(LoginRequiredMixin, ListView):
    """قائمة الفروع"""
    model = Branch
    template_name = 'pages/branches/list.html'
    context_object_name = 'object_list'
    paginate_by = 15
    
    def get_queryset(self):
        queryset = Branch.objects.select_related('cost_center')
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'الفروع'
        context['page_subtitle'] = 'إدارة فروع المؤسسة'
        context['add_button_text'] = 'إضافة فرع'
        context['search_placeholder'] = 'البحث عن فرع...'
        context['cost_centers'] = CostCenter.objects.filter(is_active=True)
        return context


@login_required
def branch_create(request):
    """إنشاء فرع جديد"""
    if request.method == 'POST':
        Branch.objects.create(
            name=request.POST.get('name'),
            code=request.POST.get('code'),
            cost_center_id=request.POST.get('cost_center') or None,
            address=request.POST.get('address', ''),
            phone=request.POST.get('phone', ''),
        )
        messages.success(request, 'تم إضافة الفرع بنجاح')
    return redirect('branches:list')


@login_required
def branch_update(request, pk):
    """تعديل فرع"""
    branch = get_object_or_404(Branch, pk=pk)
    if request.method == 'POST':
        branch.name = request.POST.get('name')
        branch.code = request.POST.get('code')
        branch.cost_center_id = request.POST.get('cost_center') or None
        branch.address = request.POST.get('address', '')
        branch.phone = request.POST.get('phone', '')
        branch.save()
        messages.success(request, 'تم تعديل الفرع بنجاح')
    return redirect('branches:list')


@login_required
def branch_delete(request, pk):
    """حذف فرع"""
    branch = get_object_or_404(Branch, pk=pk)
    if request.method == 'POST':
        branch.delete()
        messages.success(request, 'تم حذف الفرع بنجاح')
    return redirect('branches:list')


# =============================================================================
# Bank Views
# =============================================================================

class BankListView(LoginRequiredMixin, ListView):
    """قائمة البنوك"""
    model = Bank
    template_name = 'pages/banks/list.html'
    context_object_name = 'object_list'
    paginate_by = 15
    
    def get_queryset(self):
        queryset = Bank.objects.select_related('branch')
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'البنوك'
        context['page_subtitle'] = 'إدارة حسابات البنوك'
        context['add_button_text'] = 'إضافة بنك'
        context['search_placeholder'] = 'البحث عن بنك...'
        context['branches'] = Branch.objects.filter(is_active=True)
        return context


@login_required
def bank_create(request):
    """إنشاء بنك جديد"""
    if request.method == 'POST':
        Bank.objects.create(
            name=request.POST.get('name'),
            code=request.POST.get('code'),
            branch_id=request.POST.get('branch') or None,
            account_number=request.POST.get('account_number', ''),
            iban=request.POST.get('iban', ''),
        )
        messages.success(request, 'تم إضافة البنك بنجاح')
    return redirect('banks:list')


@login_required
def bank_update(request, pk):
    """تعديل بنك"""
    bank = get_object_or_404(Bank, pk=pk)
    if request.method == 'POST':
        bank.name = request.POST.get('name')
        bank.code = request.POST.get('code')
        bank.branch_id = request.POST.get('branch') or None
        bank.account_number = request.POST.get('account_number', '')
        bank.iban = request.POST.get('iban', '')
        bank.save()
        messages.success(request, 'تم تعديل البنك بنجاح')
    return redirect('banks:list')


@login_required
def bank_delete(request, pk):
    """حذف بنك"""
    bank = get_object_or_404(Bank, pk=pk)
    if request.method == 'POST':
        bank.delete()
        messages.success(request, 'تم حذف البنك بنجاح')
    return redirect('banks:list')


# =============================================================================
# Cost Center Views
# =============================================================================

class CostCenterListView(LoginRequiredMixin, ListView):
    """قائمة مراكز التكلفة"""
    model = CostCenter
    template_name = 'pages/cost_centers/list.html'
    context_object_name = 'object_list'
    paginate_by = 15
    
    def get_queryset(self):
        queryset = CostCenter.objects.prefetch_related('branches')
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'مراكز التكلفة'
        context['page_subtitle'] = 'إدارة مراكز التكلفة'
        context['add_button_text'] = 'إضافة مركز تكلفة'
        context['search_placeholder'] = 'البحث عن مركز تكلفة...'
        return context


@login_required
def cost_center_create(request):
    """إنشاء مركز تكلفة جديد"""
    if request.method == 'POST':
        CostCenter.objects.create(
            name=request.POST.get('name'),
            code=request.POST.get('code'),
            description=request.POST.get('description', ''),
        )
        messages.success(request, 'تم إضافة مركز التكلفة بنجاح')
    return redirect('cost_centers:list')


@login_required
def cost_center_update(request, pk):
    """تعديل مركز تكلفة"""
    cc = get_object_or_404(CostCenter, pk=pk)
    if request.method == 'POST':
        cc.name = request.POST.get('name')
        cc.code = request.POST.get('code')
        cc.description = request.POST.get('description', '')
        cc.save()
        messages.success(request, 'تم تعديل مركز التكلفة بنجاح')
    return redirect('cost_centers:list')


@login_required
def cost_center_delete(request, pk):
    """حذف مركز تكلفة"""
    cc = get_object_or_404(CostCenter, pk=pk)
    if request.method == 'POST':
        cc.delete()
        messages.success(request, 'تم حذف مركز التكلفة بنجاح')
    return redirect('cost_centers:list')


# =============================================================================
# Supplier Views
# =============================================================================

class SupplierListView(LoginRequiredMixin, ListView):
    """قائمة الموردين"""
    model = Supplier
    template_name = 'pages/suppliers/list.html'
    context_object_name = 'object_list'
    paginate_by = 15
    
    def get_queryset(self):
        queryset = Supplier.objects.all()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'الموردين'
        context['page_subtitle'] = 'إدارة بيانات الموردين'
        context['add_button_text'] = 'إضافة مورد'
        context['search_placeholder'] = 'البحث عن مورد...'
        return context


@login_required
def suppliers_search_json(request):
    """بحث الموردين للقوائم المنسدلة — خفيف وسريع."""
    q = request.GET.get('q', '').strip()
    qs = Supplier.objects.filter(is_active=True)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return JsonResponse({
        'results': unique_suppliers_for_select(qs, limit=20),
    })


def _supplier_fields_from_post(post):
    fin = (post.get('financial_system_id') or '').strip()
    fields = {
        'name': (post.get('name') or '').strip(),
        'code': (post.get('code') or '').strip(),
        'financial_system_id': fin or None,
        'tax_number': (post.get('tax_number') or '').replace(' ', ''),
        'contact_person': (post.get('contact_person') or '').strip(),
        'phone': (post.get('phone') or '').strip(),
        'email': (post.get('email') or '').strip(),
        'bank_name': (post.get('bank_name') or '').strip(),
        'bank_account': (post.get('bank_account') or '').strip(),
        'iban': (post.get('iban') or '').strip(),
    }
    return fields


def _supplier_save_error(fields, exclude_pk=None):
    """رسالة خطأ عربية عند التكرار أو نقص البيانات، أو None."""
    if not fields['name'] or not fields['code']:
        return 'اسم المورد والكود مطلوبان'
    qs = Supplier.objects.exclude(pk=exclude_pk) if exclude_pk else Supplier.objects.all()
    if qs.filter(code=fields['code']).exists():
        return 'رقم المورد مستخدم مسبقًا'
    if fields['financial_system_id'] and qs.filter(financial_system_id=fields['financial_system_id']).exists():
        return 'رقم النظام المالي مستخدم مسبقًا'
    if fields['tax_number'] and qs.filter(tax_number=fields['tax_number']).exists():
        return 'الرقم الضريبي مستخدم مسبقًا'
    return None


@login_required
@role_required(*SUPPLIER_MANAGE_ROLES)
def supplier_create(request):
    """إنشاء مورد جديد"""
    if request.method == 'POST':
        fields = _supplier_fields_from_post(request.POST)
        error = _supplier_save_error(fields)
        if error:
            messages.error(request, error)
        else:
            supplier = Supplier.objects.create(**fields)
            log_action(AuditLog.Action.CREATE, supplier, new=audit_snapshot(supplier))
            messages.success(request, 'تم إضافة المورد بنجاح')
    return redirect('suppliers:list')


@login_required
@role_required(*SUPPLIER_MANAGE_ROLES)
def supplier_update(request, pk):
    """تعديل مورد"""
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        fields = _supplier_fields_from_post(request.POST)
        error = _supplier_save_error(fields, exclude_pk=pk)
        if error:
            messages.error(request, error)
        else:
            before = audit_snapshot(supplier)
            for k, v in fields.items():
                setattr(supplier, k, v)
            supplier.save()
            prev, new = audit_diff(before, audit_snapshot(supplier))
            if new:
                log_action(AuditLog.Action.UPDATE, supplier, previous=prev, new=new)
            messages.success(request, 'تم تعديل المورد بنجاح')
    return redirect('suppliers:list')


@login_required
@role_required(*SUPPLIER_MANAGE_ROLES)
def supplier_delete(request, pk):
    """حذف مورد"""
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        log_action(AuditLog.Action.DELETE, supplier, previous=audit_snapshot(supplier))
        supplier.delete()
        messages.success(request, 'تم حذف المورد بنجاح')
    return redirect('suppliers:list')


# =============================================================================
# Contract Views
# =============================================================================

class ContractListView(LoginRequiredMixin, ListView):
    """قائمة العقود"""
    model = Contract
    template_name = 'pages/contracts/list.html'
    context_object_name = 'object_list'
    paginate_by = 15

    def get_queryset(self):
        queryset = Contract.objects.select_related('supplier').all()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(code__icontains=search)
                | Q(supplier__name__icontains=search)
            )
        contract_type = self.request.GET.get('contract_type')
        if contract_type:
            queryset = queryset.filter(contract_type=contract_type)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'العقود'
        context['page_subtitle'] = 'إدارة عقود الموردين (خصم ثابت، حافز شهري، حافز سنوي)'
        context['add_button_text'] = 'إضافة عقد'
        context['search_placeholder'] = 'البحث عن عقد...'
        context['contract_types'] = Contract.ContractType.choices
        context['contract_types_json'] = [
            {'value': value, 'label': label}
            for value, label in Contract.ContractType.choices
        ]
        return context


@login_required
def contract_create(request):
    """إنشاء عقد جديد"""
    if request.method == 'POST':
        end_date = request.POST.get('end_date') or None
        Contract.objects.create(
            title=request.POST.get('title'),
            code=request.POST.get('code'),
            supplier_id=request.POST.get('supplier'),
            contract_type=request.POST.get('contract_type'),
            value=request.POST.get('value'),
            start_date=request.POST.get('start_date'),
            end_date=end_date,
            notes=request.POST.get('notes', ''),
        )
        messages.success(request, 'تم إضافة العقد بنجاح')
    return redirect('contracts:list')


@login_required
def contract_update(request, pk):
    """تعديل عقد"""
    contract = get_object_or_404(Contract, pk=pk)
    if request.method == 'POST':
        contract.title = request.POST.get('title')
        contract.code = request.POST.get('code')
        contract.supplier_id = request.POST.get('supplier')
        contract.contract_type = request.POST.get('contract_type')
        contract.value = request.POST.get('value')
        contract.start_date = request.POST.get('start_date')
        contract.end_date = request.POST.get('end_date') or None
        contract.notes = request.POST.get('notes', '')
        contract.save()
        messages.success(request, 'تم تعديل العقد بنجاح')
    return redirect('contracts:list')


@login_required
def contract_delete(request, pk):
    """حذف عقد"""
    contract = get_object_or_404(Contract, pk=pk)
    if request.method == 'POST':
        contract.delete()
        messages.success(request, 'تم حذف العقد بنجاح')
    return redirect('contracts:list')


# =============================================================================
# Space Rental Views
# =============================================================================

class SpaceRentalListView(LoginRequiredMixin, ListView):
    """قائمة إيجارات المساحات"""
    model = SpaceRental
    template_name = 'pages/space_rentals/list.html'
    context_object_name = 'object_list'
    paginate_by = 15

    def get_queryset(self):
        queryset = SpaceRental.objects.select_related('branch', 'supplier').all()
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(title__icontains=search)
                | Q(supplier__name__icontains=search)
                | Q(branch__name__icontains=search)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'إيجارات المساحات'
        context['page_subtitle'] = 'إدارة إيجارات المساحات والمحلات'
        context['add_button_text'] = 'إضافة إيجار'
        context['search_placeholder'] = 'البحث عن إيجار...'
        context['branches'] = Branch.objects.filter(is_active=True).order_by('name')
        context['rental_types'] = SpaceRental.RentalType.choices
        return context


@login_required
def space_rental_create(request):
    """إنشاء إيجار مساحة"""
    if request.method == 'POST':
        SpaceRental.objects.create(
            code=request.POST.get('code'),
            title=request.POST.get('title'),
            branch_id=request.POST.get('branch'),
            supplier_id=request.POST.get('supplier'),
            rental_type=request.POST.get('rental_type'),
            monthly_rent=request.POST.get('monthly_rent'),
            start_date=request.POST.get('start_date'),
            end_date=request.POST.get('end_date') or None,
            notes=request.POST.get('notes', ''),
        )
        messages.success(request, 'تم إضافة الإيجار بنجاح')
    return redirect('space_rentals:list')


@login_required
def space_rental_update(request, pk):
    """تعديل إيجار مساحة"""
    rental = get_object_or_404(SpaceRental, pk=pk)
    if request.method == 'POST':
        rental.code = request.POST.get('code')
        rental.title = request.POST.get('title')
        rental.branch_id = request.POST.get('branch')
        rental.supplier_id = request.POST.get('supplier')
        rental.rental_type = request.POST.get('rental_type')
        rental.monthly_rent = request.POST.get('monthly_rent')
        rental.start_date = request.POST.get('start_date')
        rental.end_date = request.POST.get('end_date') or None
        rental.notes = request.POST.get('notes', '')
        rental.save()
        messages.success(request, 'تم تعديل الإيجار بنجاح')
    return redirect('space_rentals:list')


@login_required
def space_rental_delete(request, pk):
    """حذف إيجار مساحة"""
    rental = get_object_or_404(SpaceRental, pk=pk)
    if request.method == 'POST':
        rental.delete()
        messages.success(request, 'تم حذف الإيجار بنجاح')
    return redirect('space_rentals:list')


# =============================================================================
# Item Views
# =============================================================================

class ItemListView(LoginRequiredMixin, ListView):
    """قائمة ملفات الأصناف"""
    model = ItemBatch
    template_name = 'pages/items/list.html'
    context_object_name = 'object_list'
    paginate_by = 15

    def get_queryset(self):
        queryset = ItemBatch.objects.select_related('supplier').annotate(
            items_count=Count('items'),
            total_amount=Sum('items__amount'),
        ).order_by('-created_at')

        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(supplier__name__icontains=search)
                | Q(items__barcode__icontains=search)
                | Q(items__name__icontains=search)
            ).distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'الأصناف'
        context['page_subtitle'] = 'ملفات أصناف الشركات والموردين'
        return context


class ItemBatchDetailView(LoginRequiredMixin, DetailView):
    """عرض محتوى ملف أصناف"""
    model = ItemBatch
    template_name = 'pages/items/detail.html'
    context_object_name = 'batch'

    def get_queryset(self):
        return ItemBatch.objects.select_related('supplier', 'created_by').prefetch_related('items')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = self.object.items.all()
        context['items'] = items
        context['items_count'] = items.count()
        context['total_amount'] = items.aggregate(total=Sum('amount'))['total'] or 0
        return context


@login_required
def item_create(request):
    """إنشاء ملف أصناف جديد"""
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        if not supplier_id:
            messages.error(request, 'يجب اختيار الشركة أو المورد')
            return redirect('items:create')

        items_count = int(request.POST.get('items_count', 0))
        batch_items = []

        for i in range(items_count):
            barcode = request.POST.get(f'items-{i}-barcode', '').strip()
            name = request.POST.get(f'items-{i}-name', '').strip()
            package = request.POST.get(f'items-{i}-package', '').strip()
            amount = request.POST.get(f'items-{i}-amount', '')

            if not (barcode and name and package and amount):
                continue

            if Item.objects.filter(barcode=barcode).exists():
                messages.warning(request, f'الباركود {barcode} موجود مسبقاً وتم تخطيه')
                continue

            batch_items.append({
                'barcode': barcode,
                'name': name,
                'package': package,
                'amount': amount,
            })

        if not batch_items:
            messages.error(request, 'لم يتم إضافة أي صنف، تأكد من تعبئة البيانات')
            return redirect('items:create')

        payment_status = request.POST.get('payment_status', ItemBatch.PaymentStatus.UNPAID)
        if payment_status not in ItemBatch.PaymentStatus.values:
            payment_status = ItemBatch.PaymentStatus.UNPAID

        batch = ItemBatch.objects.create(
            supplier_id=supplier_id,
            created_by=request.user,
            payment_status=payment_status,
        )
        for item_data in batch_items:
            Item.objects.create(batch=batch, **item_data)

        messages.success(request, f'تم حفظ ملف بـ {len(batch_items)} صنف بنجاح')
        return redirect('items:detail', pk=batch.pk)

    context = {
        'suppliers': Supplier.objects.filter(is_active=True).order_by('name'),
    }
    return render(request, 'pages/items/form.html', context)


@login_required
def item_batch_update_payment_status(request, pk):
    """تحديث حالة دفع ملف أصناف"""
    batch = get_object_or_404(ItemBatch, pk=pk)
    if request.method == 'POST':
        status = request.POST.get('payment_status')
        if status in ItemBatch.PaymentStatus.values:
            batch.payment_status = status
            batch.save(update_fields=['payment_status'])
            label = batch.get_payment_status_display()
            messages.success(request, f'تم تحديث حالة الدفع إلى: {label}')
    return redirect(request.POST.get('next') or 'items:list')


@login_required
def item_batch_delete(request, pk):
    """حذف ملف أصناف"""
    batch = get_object_or_404(ItemBatch, pk=pk)
    if request.method == 'POST':
        count = batch.items.count()
        batch.delete()
        messages.success(request, f'تم حذف الملف و{count} صنف')
    return redirect('items:list')


# =============================================================================
# Payment Views
# =============================================================================

class PaymentListView(LoginRequiredMixin, ListView):
    """قائمة طلبات الدفع"""
    model = PaymentRequest
    template_name = 'pages/payments/list.html'
    context_object_name = 'object_list'
    paginate_by = 15
    
    def get_queryset(self):
        queryset = PaymentRequest.objects.select_related('branch', 'bank', 'created_by')

        # تصفية حسب فرع المستخدم تلقائياً
        user_branch = getattr(getattr(self.request.user, 'profile', None), 'branch', None)
        if user_branch:
            queryset = queryset.filter(branch=user_branch)
        
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(Q(pk__icontains=search) | Q(notes__icontains=search))
        
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        if not user_branch:
            branch = self.request.GET.get('branch')
            if branch:
                queryset = queryset.filter(branch_id=branch)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_branch = getattr(getattr(self.request.user, 'profile', None), 'branch', None)
        if not user_branch:
            context['branches'] = Branch.objects.filter(is_active=True)
        context['user_branch'] = user_branch
        return context


class PaymentDetailView(LoginRequiredMixin, DetailView):
    """تفاصيل طلب الدفع"""
    model = PaymentRequest
    template_name = 'pages/payments/detail.html'
    context_object_name = 'payment'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_change_status'] = True  # TODO: Add permission check
        return context


@login_required
def payment_create(request):
    """إنشاء طلب دفع جديد"""
    if request.method == 'POST':
        items_count = int(request.POST.get('items_count', 0))
        supplier_ids = [
            request.POST.get(f'items-{i}-supplier')
            for i in range(items_count)
            if request.POST.get(f'items-{i}-supplier')
        ]
        blocked_suppliers = _validate_payment_suppliers(supplier_ids)
        if blocked_suppliers:
            messages.error(
                request,
                'لا يمكن إصدار طلب دفع لمورد لديه ملف أصناف غير مدفوع: '
                + '، '.join(blocked_suppliers),
            )
            return redirect('payments:create')

        payment = PaymentRequest.objects.create(
            branch_id=request.POST.get('branch'),
            bank_id=request.POST.get('bank') or None,
            cost_center=request.POST.get('cost_center', ''),
            bank_account_number=request.POST.get('bank_account_number', ''),
            supplier_account=request.POST.get('supplier_account', '21101001'),
            analytical_account=request.POST.get('analytical_account', ''),
            notes=request.POST.get('notes', ''),
            created_by=request.user,
            status='draft' if request.POST.get('action') == 'draft' else 'proposed',
        )
        
        # Add items
        items_count = int(request.POST.get('items_count', 0))
        total = 0
        total_proposed = 0
        for i in range(items_count):
            supplier_id = request.POST.get(f'items-{i}-supplier')
            current_balance = request.POST.get(f'items-{i}-current_balance', 0)
            proposed_amount = request.POST.get(f'items-{i}-proposed_amount', 0)
            sultan_approval = request.POST.get(f'items-{i}-sultan_approval', 'pending')
            auditor_status = request.POST.get(f'items-{i}-auditor_status', 'pending')
            cfo_approval = request.POST.get(f'items-{i}-cfo_approval', 'pending')
            abu_alaa_proposed = request.POST.get(f'items-{i}-abu_alaa_proposed', 0)
            abu_alaa_final = request.POST.get(f'items-{i}-abu_alaa_final', 'pending')
            notes = request.POST.get(f'items-{i}-notes', '')
            
            if supplier_id:
                PaymentRequestItem.objects.create(
                    payment_request=payment,
                    supplier_id=supplier_id,
                    current_balance=float(current_balance or 0),
                    proposed_amount=float(proposed_amount or 0),
                    sultan_approval=sultan_approval,
                    auditor_status=auditor_status,
                    cfo_approval=cfo_approval,
                    abu_alaa_proposed=float(abu_alaa_proposed or 0),
                    abu_alaa_final=abu_alaa_final,
                    amount=float(abu_alaa_proposed or 0),
                    notes=notes,
                )
                total += float(abu_alaa_proposed or 0)
                total_proposed += float(proposed_amount or 0)
        
        # Update total amount
        payment.amount = total
        payment.save()

        log_action(AuditLog.Action.CREATE, payment, new={'status': payment.status, 'amount': payment.amount})
        notify_payment_created(payment, request.user)
        
        messages.success(request, 'تم إنشاء طلب الدفع بنجاح')
        return redirect('payments:detail', pk=payment.pk)
    
    user_branch = getattr(getattr(request.user, 'profile', None), 'branch', None)
    if user_branch:
        branches_qs = Branch.objects.filter(is_active=True, pk=user_branch.pk).select_related('cost_center')
        banks_qs = Bank.objects.filter(is_active=True, branch=user_branch).select_related('branch')
    else:
        branches_qs = Branch.objects.filter(is_active=True).select_related('cost_center')
        banks_qs = Bank.objects.filter(is_active=True).select_related('branch')

    unique_banks = unique_banks_for_select(banks_qs)
    context = {
        'branches': branches_qs,
        'banks': unique_banks,
        'banks_json': banks_json_for_payment(banks_qs),
        'cost_centers': CostCenter.objects.filter(is_active=True),
        'suppliers': suppliers_eligible_for_payment_qs(),
        'blocked_supplier_ids': list(_supplier_ids_with_unpaid_item_batches()),
        'user_branch': user_branch,
    }
    return render(request, 'pages/payments/form.html', context)


@login_required
def payment_update(request, pk):
    """تعديل طلب دفع"""
    payment = get_object_or_404(PaymentRequest, pk=pk)
    
    if payment.status == 'final_approved':
        messages.error(request, 'لا يمكن تعديل طلب معتمد نهائياً')
        return redirect('payments:detail', pk=pk)
    
    amount_before = payment.amount
    if request.method == 'POST':
        items_count = int(request.POST.get('items_count', 0))
        supplier_ids = [
            request.POST.get(f'items-{i}-supplier')
            for i in range(items_count)
            if request.POST.get(f'items-{i}-supplier')
        ]
        blocked_suppliers = _validate_payment_suppliers(supplier_ids)
        if blocked_suppliers:
            messages.error(
                request,
                'لا يمكن إصدار طلب دفع لمورد لديه ملف أصناف غير مدفوع: '
                + '، '.join(blocked_suppliers),
            )
            return redirect('payments:update', pk=pk)

        payment.branch_id = request.POST.get('branch')
        payment.bank_id = request.POST.get('bank') or None
        payment.cost_center = request.POST.get('cost_center', '')
        payment.bank_account_number = request.POST.get('bank_account_number', '')
        payment.supplier_account = request.POST.get('supplier_account', '21101001')
        payment.analytical_account = request.POST.get('analytical_account', '')
        payment.notes = request.POST.get('notes', '')
        
        if request.POST.get('action') == 'submit':
            payment.status = 'proposed'
        
        payment.save()
        
        # Update items
        payment.items.all().delete()
        items_count = int(request.POST.get('items_count', 0))
        total = 0
        total_proposed = 0
        for i in range(items_count):
            supplier_id = request.POST.get(f'items-{i}-supplier')
            current_balance = request.POST.get(f'items-{i}-current_balance', 0)
            proposed_amount = request.POST.get(f'items-{i}-proposed_amount', 0)
            sultan_approval = request.POST.get(f'items-{i}-sultan_approval', 'pending')
            auditor_status = request.POST.get(f'items-{i}-auditor_status', 'pending')
            cfo_approval = request.POST.get(f'items-{i}-cfo_approval', 'pending')
            abu_alaa_proposed = request.POST.get(f'items-{i}-abu_alaa_proposed', 0)
            abu_alaa_final = request.POST.get(f'items-{i}-abu_alaa_final', 'pending')
            notes = request.POST.get(f'items-{i}-notes', '')
            
            if supplier_id:
                PaymentRequestItem.objects.create(
                    payment_request=payment,
                    supplier_id=supplier_id,
                    current_balance=float(current_balance or 0),
                    proposed_amount=float(proposed_amount or 0),
                    sultan_approval=sultan_approval,
                    auditor_status=auditor_status,
                    cfo_approval=cfo_approval,
                    abu_alaa_proposed=float(abu_alaa_proposed or 0),
                    abu_alaa_final=abu_alaa_final,
                    amount=float(abu_alaa_proposed or 0),
                    notes=notes,
                )
                total += float(abu_alaa_proposed or 0)
                total_proposed += float(proposed_amount or 0)
        
        payment.amount = total
        payment.save()
        payment.refresh_from_db(fields=['amount'])
        if payment.amount != amount_before:
            log_action(AuditLog.Action.AMOUNT_EDIT, payment, previous={'amount': amount_before},
                       new={'amount': payment.amount})
        else:
            log_action(AuditLog.Action.UPDATE, payment, new={'note': 'تعديل بيانات الطلب'})
        
        messages.success(request, 'تم تعديل طلب الدفع بنجاح')
        return redirect('payments:detail', pk=pk)
    
    user_branch = getattr(getattr(request.user, 'profile', None), 'branch', None)
    if user_branch:
        branches_qs = Branch.objects.filter(is_active=True, pk=user_branch.pk).select_related('cost_center')
        banks_qs = Bank.objects.filter(is_active=True, branch=user_branch).select_related('branch')
    else:
        branches_qs = Branch.objects.filter(is_active=True).select_related('cost_center')
        banks_qs = Bank.objects.filter(is_active=True).select_related('branch')

    unique_banks = unique_banks_for_select(banks_qs, payment.bank_id)
    context = {
        'payment': payment,
        'branches': branches_qs,
        'banks': unique_banks,
        'banks_json': banks_json_for_payment(banks_qs, payment.bank_id),
        'cost_centers': CostCenter.objects.filter(is_active=True),
        'suppliers': suppliers_eligible_for_payment_qs(),
        'blocked_supplier_ids': list(_supplier_ids_with_unpaid_item_batches()),
        'user_branch': user_branch,
    }
    return render(request, 'pages/payments/form.html', context)


@login_required
def payment_change_status(request, pk):
    """تغيير حالة طلب الدفع"""
    payment = get_object_or_404(PaymentRequest, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid_statuses = ['proposed', 'first_approved', 'audited', 'final_approved', 'rejected']
        
        if new_status in valid_statuses:
            old_status = payment.status
            payment.status = new_status
            if new_status == 'rejected':
                payment.rejection_reason = request.POST.get('rejection_reason', payment.rejection_reason)
            payment.save()
            log_action(
                AuditLog.Action.APPROVAL if new_status in ('first_approved', 'audited', 'final_approved', 'rejected')
                else AuditLog.Action.STATUS_CHANGE,
                payment, previous={'status': old_status}, new={'status': new_status},
                reason=request.POST.get('rejection_reason', '') if new_status == 'rejected' else '')
            notify_payment_status_changed(payment, old_status, new_status, request.user)
            messages.success(request, f'تم تغيير الحالة إلى {payment.get_status_display()}')
        else:
            messages.error(request, 'حالة غير صالحة')
    
    return redirect('payments:detail', pk=pk)


@login_required
def payment_delete(request, pk):
    """حذف طلب الدفع - للمدراء فقط"""
    if not hasattr(request.user, 'profile') or request.user.profile.role is None or request.user.profile.role.role_type != 'admin':
        messages.error(request, 'ليس لديك صلاحية حذف الطلبات')
        return redirect('payments:list')
    
    payment = get_object_or_404(PaymentRequest, pk=pk)
    if request.method == 'POST':
        log_action(AuditLog.Action.DELETE, payment, previous={'status': payment.status, 'amount': payment.amount})
        payment.delete()
        messages.success(request, f'تم حذف الطلب #{pk} بنجاح')
        return redirect('payments:list')
    
    return redirect('payments:list')


def _contracts_queryset(request):
    queryset = Contract.objects.select_related('supplier').all()
    search = request.GET.get('search')
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(code__icontains=search)
            | Q(supplier__name__icontains=search)
        )
    contract_type = request.GET.get('contract_type')
    if contract_type:
        queryset = queryset.filter(contract_type=contract_type)
    return queryset.order_by('-created_at')


def _space_rentals_queryset(request):
    queryset = SpaceRental.objects.select_related('branch', 'supplier').all()
    search = request.GET.get('search')
    if search:
        queryset = queryset.filter(
            Q(code__icontains=search)
            | Q(title__icontains=search)
            | Q(supplier__name__icontains=search)
            | Q(branch__name__icontains=search)
        )
    return queryset.order_by('-created_at')


def _items_batches_queryset(request):
    queryset = ItemBatch.objects.select_related('supplier').annotate(
        items_count=Count('items'),
        total_amount=Sum('items__amount'),
    ).order_by('-created_at')
    search = request.GET.get('search')
    if search:
        queryset = queryset.filter(
            Q(supplier__name__icontains=search)
            | Q(items__barcode__icontains=search)
            | Q(items__name__icontains=search)
        ).distinct()
    return queryset


def _payments_queryset(request):
    queryset = PaymentRequest.objects.select_related(
        'branch', 'bank', 'created_by'
    ).prefetch_related('items__supplier')

    user_branch = getattr(getattr(request.user, 'profile', None), 'branch', None)
    if user_branch:
        queryset = queryset.filter(branch=user_branch)

    search = request.GET.get('search')
    if search:
        queryset = queryset.filter(Q(pk__icontains=search) | Q(notes__icontains=search))

    status = request.GET.get('status')
    if status:
        queryset = queryset.filter(status=status)

    if not user_branch:
        branch = request.GET.get('branch')
        if branch:
            queryset = queryset.filter(branch_id=branch)

    return queryset.order_by('-created_at')


def _payment_suppliers_label(payment):
    names = []
    seen = set()
    for item in payment.items.all():
        if item.supplier_id not in seen:
            seen.add(item.supplier_id)
            names.append(item.supplier.name)
    return '، '.join(names) if names else '-'


@login_required
def contracts_export_excel(request):
    """تصدير قائمة العقود إلى Excel"""
    contracts = list(_contracts_queryset(request))
    headers = [
        '#', 'رقم العقد', 'العنوان', 'المورد', 'كود المورد', 'نوع العقد',
        'القيمة', 'تاريخ البداية', 'تاريخ النهاية', 'الحالة', 'ملاحظات',
    ]
    rows = []
    for idx, contract in enumerate(contracts, 1):
        rows.append([
            idx,
            contract.code,
            contract.title,
            contract.supplier.name,
            contract.supplier.code,
            contract.get_contract_type_display(),
            contract.value_display,
            contract.start_date.strftime('%Y/%m/%d'),
            contract.end_date.strftime('%Y/%m/%d') if contract.end_date else 'مفتوح',
            'نشط' if contract.is_active else 'منتهي',
            contract.notes or '-',
        ])

    search = request.GET.get('search', '')
    contract_type = request.GET.get('contract_type', '')
    meta = [('عدد العقود', len(contracts))]
    if search:
        meta.append(('بحث', search))
    if contract_type:
        meta.append(('نوع العقد', dict(Contract.ContractType.choices).get(contract_type, contract_type)))

    builder = ModernExcelBuilder('تقرير العقود', sheet_name='العقود')
    start_row = builder.write_report_header(len(headers), meta)
    builder.write_table(
        start_row, headers, rows,
        col_widths=[6, 14, 28, 22, 12, 16, 14, 14, 14, 10, 24],
    )
    return builder.to_response('contracts')


@login_required
def space_rentals_export_excel(request):
    """تصدير قائمة إيجارات المساحات إلى Excel"""
    rentals = list(_space_rentals_queryset(request))
    headers = [
        '#', 'رقم العقد', 'المساحة', 'الفرع', 'المورد', 'نوع الإيجار',
        'الإيجار الشهري', 'تاريخ البداية', 'تاريخ النهاية', 'الحالة', 'ملاحظات',
    ]
    rows = []
    total_rent = 0
    for idx, rental in enumerate(rentals, 1):
        total_rent += float(rental.monthly_rent)
        rows.append([
            idx,
            rental.code,
            rental.title,
            rental.branch.name,
            rental.supplier.name,
            rental.get_rental_type_display(),
            float(rental.monthly_rent),
            rental.start_date.strftime('%Y/%m/%d'),
            rental.end_date.strftime('%Y/%m/%d') if rental.end_date else 'مفتوح',
            'نشط' if rental.is_active else 'منتهي',
            rental.notes or '-',
        ])

    meta = [('عدد الإيجارات', len(rentals))]
    if request.GET.get('search'):
        meta.append(('بحث', request.GET.get('search')))

    builder = ModernExcelBuilder('تقرير إيجارات المساحات', sheet_name='إيجارات المساحات')
    start_row = builder.write_report_header(len(headers), meta)
    builder.write_table(
        start_row, headers, rows,
        col_widths=[6, 14, 22, 16, 22, 18, 14, 14, 14, 10, 24],
        totals_row=['', '', '', '', '', 'المجموع الشهري', total_rent, '', '', '', ''],
    )
    return builder.to_response('space_rentals')


@login_required
def items_export_excel(request):
    """تصدير الأصناف إلى Excel"""
    batches = list(_items_batches_queryset(request))
    batch_ids = [batch.id for batch in batches]

    summary_headers = ['#', 'رقم الملف', 'المورد / الشركة', 'عدد الأصناف', 'المبلغ الإجمالي', 'حالة الدفع', 'تاريخ الإنشاء']
    summary_rows = []
    grand_total = 0
    grand_count = 0
    for idx, batch in enumerate(batches, 1):
        amount = float(batch.total_amount or 0)
        count = batch.items_count or 0
        grand_total += amount
        grand_count += count
        summary_rows.append([
            idx,
            batch.id,
            batch.supplier.name,
            count,
            amount,
            batch.get_payment_status_display(),
            batch.created_at.strftime('%Y/%m/%d'),
        ])

    items = Item.objects.filter(batch_id__in=batch_ids).select_related(
        'batch', 'batch__supplier'
    ).order_by('batch_id', 'name') if batch_ids else Item.objects.none()

    detail_headers = ['#', 'رقم الملف', 'المورد', 'الباركود', 'اسم الصنف', 'العبوة', 'المبلغ']
    detail_rows = []
    for idx, item in enumerate(items, 1):
        detail_rows.append([
            idx,
            item.batch_id,
            item.batch.supplier.name,
            item.barcode,
            item.name,
            item.package,
            float(item.amount),
        ])

    search = request.GET.get('search', '')
    meta = [('عدد الملفات', len(batches)), ('إجمالي الأصناف', grand_count)]
    if search:
        meta.append(('بحث', search))

    builder = ModernExcelBuilder('تقرير الأصناف', sheet_name='ملخص الملفات')
    start_row = builder.write_report_header(len(summary_headers), meta)
    builder.write_table(
        start_row, summary_headers, summary_rows,
        col_widths=[6, 10, 26, 14, 16, 12, 14],
        totals_row=['', '', 'المجموع', grand_count, grand_total, '', ''],
    )

    detail_ws = builder.add_sheet('تفاصيل الأصناف')
    builder.write_sheet_table(
        detail_ws,
        'تفاصيل الأصناف',
        detail_headers,
        detail_rows,
        col_widths=[6, 10, 22, 16, 28, 14, 14],
        totals_row=['', '', '', '', '', 'المجموع', grand_total] if detail_rows else None,
    )
    return builder.to_response('items')


@login_required
def payments_list_export_excel(request):
    """تصدير قائمة طلبات الدفع إلى Excel"""
    payments = list(_payments_queryset(request))
    headers = [
        '#', 'رقم الطلب', 'الفرع', 'البنك', 'عدد البنود', 'المبلغ الإجمالي',
        'مقترح المشتريات', 'اقتراح أبو علاء', 'الموردون', 'التاريخ', 'الحالة',
    ]
    rows = []
    total_amount = 0
    total_proposed = 0
    total_abu_alaa = 0
    for idx, payment in enumerate(payments, 1):
        amount = float(payment.total_amount)
        proposed = float(payment.total_proposed_amount)
        abu_alaa = float(payment.total_abu_alaa_proposed)
        total_amount += amount
        total_proposed += proposed
        total_abu_alaa += abu_alaa
        rows.append([
            idx,
            payment.id,
            payment.branch.name,
            payment.bank.name if payment.bank else '-',
            payment.items_count,
            amount,
            proposed,
            abu_alaa,
            _payment_suppliers_label(payment),
            payment.created_at.strftime('%Y/%m/%d'),
            payment.get_status_display(),
        ])

    meta = [('عدد الطلبات', len(payments))]
    if request.GET.get('search'):
        meta.append(('بحث', request.GET.get('search')))
    if request.GET.get('status'):
        meta.append(('الحالة', dict(PaymentRequest.Status.choices).get(request.GET.get('status'), '')))
    if request.GET.get('branch'):
        branch = Branch.objects.filter(pk=request.GET.get('branch')).first()
        if branch:
            meta.append(('الفرع', branch.name))

    builder = ModernExcelBuilder('تقرير طلبات الدفع', sheet_name='طلبات الدفع')
    start_row = builder.write_report_header(len(headers), meta)
    builder.write_table(
        start_row, headers, rows,
        col_widths=[6, 12, 16, 16, 10, 14, 16, 16, 28, 12, 14],
        totals_row=['', '', '', '', 'المجموع', total_amount, total_proposed, total_abu_alaa, '', '', ''],
    )
    return builder.to_response('payments')


@login_required
def payment_export_excel(request, pk):
    """تصدير طلب دفع واحد إلى Excel"""
    payment = get_object_or_404(
        PaymentRequest.objects.select_related('branch', 'bank', 'created_by').prefetch_related('items__supplier'),
        pk=pk,
    )
    headers = [
        'رقم المورد', 'اسم المورد', 'رصيد المورد', 'دفعة المشتريات',
        'اعتماد سلطان', 'حالة المدقق', 'اعتماد المدير المالي',
        'اقتراح السداد', 'اعتماد أبو علاء', 'ملاحظات',
    ]
    rows = []
    for item in payment.items.all():
        rows.append([
            item.supplier.code,
            item.supplier.name,
            float(item.current_balance),
            float(item.proposed_amount),
            item.get_sultan_approval_display(),
            item.get_auditor_status_display(),
            item.get_cfo_approval_display(),
            float(item.abu_alaa_proposed),
            item.get_abu_alaa_final_display(),
            item.notes or '-',
        ])

    meta = [
        ('رقم الطلب', f'#{payment.id}'),
        ('الفرع', payment.branch.name),
        ('البنك', payment.bank.name if payment.bank else '-'),
        ('الحالة', payment.get_status_display()),
        ('التاريخ', payment.created_at.strftime('%Y/%m/%d')),
        ('عدد البنود', payment.items_count),
    ]
    if payment.notes:
        meta.append(('ملاحظات الطلب', payment.notes))

    builder = ModernExcelBuilder(f'طلب دفع رقم #{payment.id}', sheet_name=f'طلب {payment.id}')
    start_row = builder.write_report_header(len(headers), meta)
    builder.write_table(
        start_row, headers, rows,
        col_widths=[14, 28, 14, 14, 14, 14, 18, 14, 14, 24],
        totals_row=[
            '', 'المجموع الكلي', '', float(payment.total_proposed_amount),
            '', '', '', float(payment.total_abu_alaa_proposed), '', '',
        ],
    )
    return builder.to_response(f'payment_{payment.id}')


# =============================================================================
# User Management Views
# =============================================================================

class UserListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    """قائمة المستخدمين"""
    model = User
    template_name = 'pages/users/list.html'
    context_object_name = 'users'
    
    def get_queryset(self):
        return User.objects.all().order_by('-date_joined')


def _portal_supplier(role_id, code):
    """(المورد، رسالة خطأ) لحساب بوابة الموردين: الدور «مورد» يتطلب رمز مورد صحيحًا، وغيره لا يُربط بمورد."""
    role = Role.objects.filter(pk=role_id).first() if role_id else None
    if role is None or role.role_type != Role.RoleType.SUPPLIER:
        return None, None
    supplier = Supplier.objects.filter(code=(code or '').strip()).first()
    if supplier is None:
        return None, 'حساب المورد يتطلب رمز مورد صحيحًا'
    return supplier, None


@login_required
@admin_required
def user_create(request):
    """إنشاء مستخدم جديد"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email', '')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        is_staff = request.POST.get('is_staff') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        role_id = request.POST.get('role')
        branch_id = request.POST.get('branch')
        supplier, supplier_error = _portal_supplier(role_id, request.POST.get('supplier_code'))

        if User.objects.filter(username=username).exists():
            messages.error(request, 'اسم المستخدم موجود مسبقاً')
        elif supplier_error:
            messages.error(request, supplier_error)
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            user.is_staff = is_staff
            user.is_active = is_active
            user.save()
            
            # إنشاء أو تحديث UserProfile
            profile, created = UserProfile.objects.get_or_create(user=user)
            if role_id:
                profile.role_id = role_id
            if branch_id:
                profile.branch_id = branch_id
            profile.supplier = supplier
            profile.save()
            
            messages.success(request, 'تم إنشاء المستخدم بنجاح')
            return redirect('users:list')
    
    context = {
        'roles': Role.objects.filter(is_active=True),
        'branches': Branch.objects.filter(is_active=True),
    }
    return render(request, 'pages/users/form.html', context)


@login_required
@admin_required
def user_update(request, pk):
    """تعديل مستخدم"""
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        user.username = request.POST.get('username')
        user.email = request.POST.get('email', '')
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.is_staff = request.POST.get('is_staff') == 'on'
        user.is_active = request.POST.get('is_active') == 'on'

        role_id = request.POST.get('role')
        supplier, supplier_error = _portal_supplier(role_id, request.POST.get('supplier_code'))
        if supplier_error:
            messages.error(request, supplier_error)
            return redirect('users:update', pk=user.pk)

        password = request.POST.get('password')
        if password:
            user.set_password(password)
        
        user.save()
        
        # تحديث UserProfile
        profile, created = UserProfile.objects.get_or_create(user=user)
        profile.supplier = supplier
        branch_id = request.POST.get('branch')
        
        if role_id:
            profile.role_id = role_id
        else:
            profile.role = None
            
        if branch_id:
            profile.branch_id = branch_id
        else:
            profile.branch = None
            
        profile.save()
        
        messages.success(request, 'تم تعديل المستخدم بنجاح')
        return redirect('users:list')
    
    context = {
        'user_obj': user,
        'roles': Role.objects.filter(is_active=True),
        'branches': Branch.objects.filter(is_active=True),
    }
    return render(request, 'pages/users/form.html', context)


@login_required
@admin_required
def user_delete(request, pk):
    """حذف مستخدم"""
    user = get_object_or_404(User, pk=pk)
    
    if user == request.user:
        messages.error(request, 'لا يمكنك حذف حسابك الخاص')
    else:
        user.delete()
        messages.success(request, 'تم حذف المستخدم بنجاح')
    
    return redirect('users:list')


# =============================================================================
# Role Management Views
# =============================================================================

from apps.core.models import Role, UserProfile

class RoleListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    """قائمة الأدوار"""
    model = Role
    template_name = 'pages/roles/list.html'
    context_object_name = 'roles'
    
    def get_queryset(self):
        return Role.objects.all().order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # عدد المستخدمين لكل دور
        for role in context['roles']:
            role.users_count = UserProfile.objects.filter(role=role).count()
        return context


@login_required
@admin_required
def role_create(request):
    """إنشاء دور جديد"""
    if request.method == 'POST':
        name = request.POST.get('name')
        role_type = request.POST.get('role_type')
        description = request.POST.get('description', '')
        
        if Role.objects.filter(name=name).exists():
            messages.error(request, 'اسم الدور موجود مسبقاً')
        else:
            Role.objects.create(
                name=name,
                role_type=role_type,
                description=description,
                is_system_role=False,
                is_active=True
            )
            messages.success(request, 'تم إنشاء الدور بنجاح')
            return redirect('roles:list')
    
    return redirect('roles:list')


@login_required
@admin_required
def role_update(request, pk):
    """تعديل دور"""
    role = get_object_or_404(Role, pk=pk)
    
    if request.method == 'POST':
        if role.is_system_role:
            messages.error(request, 'لا يمكن تعديل أدوار النظام')
        else:
            role.name = request.POST.get('name')
            role.role_type = request.POST.get('role_type')
            role.description = request.POST.get('description', '')
            role.save()
            messages.success(request, 'تم تعديل الدور بنجاح')
        
        return redirect('roles:list')
    
    return redirect('roles:list')


@login_required
@admin_required
def role_delete(request, pk):
    """حذف دور"""
    role = get_object_or_404(Role, pk=pk)
    
    if role.is_system_role:
        messages.error(request, 'لا يمكن حذف أدوار النظام')
    else:
        users_count = UserProfile.objects.filter(role=role).count()
        if users_count > 0:
            messages.error(request, f'لا يمكن حذف الدور لأنه مرتبط بـ {users_count} مستخدم')
        else:
            role.delete()
            messages.success(request, 'تم حذف الدور بنجاح')
    
    return redirect('roles:list')


def _format_notification_time(dt):
    from django.utils import timezone
    now = timezone.localtime(timezone.now())
    local_dt = timezone.localtime(dt)
    diff = now - local_dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return 'الآن'
    if seconds < 3600:
        minutes = seconds // 60
        return f'منذ {minutes} د'
    if seconds < 86400:
        hours = seconds // 3600
        return f'منذ {hours} س'
    return local_dt.strftime('%Y/%m/%d %H:%M')


def _serialize_notification(notification):
    return {
        'id': notification.id,
        'title': notification.title,
        'message': notification.message,
        'link': notification.link,
        'category': notification.category,
        'is_read': notification.is_read,
        'time_ago': _format_notification_time(notification.created_at),
    }


@login_required
def notifications_json(request):
    """قائمة الإشعارات للمستخدم الحالي"""
    limit = min(int(request.GET.get('limit', 20)), 50)
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:limit]
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({
        'unread_count': unread_count,
        'notifications': [_serialize_notification(item) for item in notifications],
    })


@login_required
def notifications_mark_read(request):
    """تعليم إشعار أو جميع الإشعارات كمقروءة"""
    if request.method != 'POST':
        return JsonResponse({'error': 'طريقة غير مسموحة'}, status=405)

    if request.POST.get('all'):
        updated = mark_all_notifications_read(request.user)
        return JsonResponse({'success': True, 'updated': updated})

    notification_id = request.POST.get('id')
    if not notification_id:
        return JsonResponse({'error': 'معرّف الإشعار مطلوب'}, status=400)

    notification = Notification.objects.filter(pk=notification_id, recipient=request.user).first()
    if not notification:
        return JsonResponse({'error': 'الإشعار غير موجود'}, status=404)

    mark_notification_read(notification, request.user)
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'success': True, 'unread_count': unread_count})
