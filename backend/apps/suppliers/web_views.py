"""
واجهات الموردين: الاستيراد من Excel، التفاصيل، وجهات الاتصال.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.services import log_action, snapshot
from apps.core.access import SUPPLIER_IMPORT_ROLES, SUPPLIER_MANAGE_ROLES, SUPPLIER_VIEW_ROLES, has_role, role_required

from . import importer
from .models import Supplier, SupplierContact, SupplierImportJob

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@login_required
@role_required(*SUPPLIER_IMPORT_ROLES)
def import_upload(request):
    jobs = SupplierImportJob.objects.select_related('uploaded_by')[:10]
    if request.method == 'POST':
        f = request.FILES.get('file')
        if not f:
            messages.error(request, 'اختر ملف Excel أولًا')
        elif not f.name.lower().endswith('.xlsx'):
            messages.error(request, 'الصيغة المدعومة هي .xlsx فقط')
        elif f.size > MAX_UPLOAD_BYTES:
            messages.error(request, 'حجم الملف يتجاوز 10 ميجابايت')
        else:
            try:
                job = importer.stage(f, f.name, request.user)
            except importer.ImportFileError as exc:
                messages.error(request, str(exc))
            else:
                return redirect('suppliers:import_preview', pk=job.pk)
    return render(request, 'pages/suppliers/import_upload.html', {
        'page_title': 'استيراد الموردين', 'jobs': jobs,
    })


@login_required
@role_required(*SUPPLIER_IMPORT_ROLES)
def import_template(request):
    resp = HttpResponse(
        importer.build_template(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    resp['Content-Disposition'] = 'attachment; filename="suppliers_template.xlsx"'
    return resp


@login_required
@role_required(*SUPPLIER_IMPORT_ROLES)
def import_preview(request, pk):
    job = get_object_or_404(SupplierImportJob, pk=pk)
    flt = request.GET.get('status', '')
    rows = [r for r in job.rows if not flt or r['status'] == flt]
    return render(request, 'pages/suppliers/import_preview.html', {
        'page_title': 'معاينة الاستيراد', 'job': job, 'rows': rows[:500],
        'shown': min(len(rows), 500), 'total_filtered': len(rows), 'flt': flt,
        'can_commit': job.status == SupplierImportJob.Status.STAGED and job.valid_rows > 0,
    })


@login_required
@role_required(*SUPPLIER_IMPORT_ROLES)
@require_POST
def import_confirm(request, pk):
    job = get_object_or_404(SupplierImportJob, pk=pk)
    try:
        job = importer.commit(job, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('suppliers:import_preview', pk=pk)
    messages.success(request, f'تم استيراد {job.created_count} مورد بنجاح')
    return redirect('suppliers:list')


@login_required
@role_required(*SUPPLIER_IMPORT_ROLES)
@require_POST
def import_cancel(request, pk):
    job = get_object_or_404(SupplierImportJob, pk=pk, status=SupplierImportJob.Status.STAGED)
    job.status = SupplierImportJob.Status.CANCELLED
    job.save(update_fields=['status'])
    messages.info(request, 'تم إلغاء عملية الاستيراد')
    return redirect('suppliers:import')


@login_required
@role_required(*SUPPLIER_VIEW_ROLES)
def supplier_detail(request, pk):
    supplier = get_object_or_404(
        Supplier.objects.prefetch_related('contacts', 'branches'), pk=pk)
    return render(request, 'pages/suppliers/detail.html', {
        'page_title': supplier.name, 'supplier': supplier,
        'can_manage': has_role(request.user, *SUPPLIER_MANAGE_ROLES),
    })


@login_required
@role_required(*SUPPLIER_MANAGE_ROLES)
@require_POST
def contact_add(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    phone = importer.normalize_phone(request.POST.get('phone'))
    if not phone:
        messages.error(request, 'رقم الهاتف غير صالح')
        return redirect('suppliers:detail', pk=pk)
    if SupplierContact.objects.filter(supplier=supplier, phone=phone).exists():
        messages.error(request, 'هذا الرقم مضاف مسبقًا لنفس المورد')
        return redirect('suppliers:detail', pk=pk)
    is_primary = bool(request.POST.get('is_primary')) or not supplier.contacts.exists()
    if is_primary:
        supplier.contacts.update(is_primary=False)
    contact = SupplierContact.objects.create(
        supplier=supplier, phone=phone, name=request.POST.get('name', '').strip()[:150],
        job_title=request.POST.get('job_title', '').strip()[:100],
        email=request.POST.get('email', '').strip(), is_primary=is_primary,
    )
    log_action(AuditLog.Action.CREATE, contact, new=snapshot(contact))
    messages.success(request, 'تمت إضافة جهة الاتصال')
    return redirect('suppliers:detail', pk=pk)


@login_required
@role_required(*SUPPLIER_MANAGE_ROLES)
@require_POST
def contact_delete(request, pk, contact_pk):
    contact = get_object_or_404(SupplierContact, pk=contact_pk, supplier_id=pk)
    before = snapshot(contact)
    log_action(AuditLog.Action.DELETE, contact, previous=before)
    contact.delete()
    messages.success(request, 'تم حذف جهة الاتصال')
    return redirect('suppliers:detail', pk=pk)
