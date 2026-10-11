"""
Web URLs - روابط واجهة الويب
"""
from django.urls import path, include
from django.views.generic import RedirectView
from apps.core import web_views
from apps.suppliers import web_views as supplier_views
from apps.audit import web_views as audit_views
from apps.reconciliation import views as recon_views
from apps.reconciliation import dashboard_views
from apps.proposals import views as proposal_views
from apps.whatsapp import views as whatsapp_views
from apps.core import live as core_live
from apps.whatsapp import inbox_views
from apps.servicedesk import portal as portal_views
from apps.servicedesk import views as sd_views

# Authentication URLs
auth_patterns = [
    path('login/', web_views.login_view, name='login'),
    path('logout/', web_views.logout_view, name='logout'),
    path('change-password/', web_views.change_password_view, name='change_password'),
]

# Branch URLs
branch_patterns = [
    path('', web_views.BranchListView.as_view(), name='list'),
    path('create/', web_views.branch_create, name='create'),
    path('<int:pk>/update/', web_views.branch_update, name='update'),
    path('<int:pk>/delete/', web_views.branch_delete, name='delete'),
]

# Bank URLs
bank_patterns = [
    path('', web_views.BankListView.as_view(), name='list'),
    path('create/', web_views.bank_create, name='create'),
    path('<int:pk>/update/', web_views.bank_update, name='update'),
    path('<int:pk>/delete/', web_views.bank_delete, name='delete'),
]

# Cost Center URLs
cost_center_patterns = [
    path('', web_views.CostCenterListView.as_view(), name='list'),
    path('create/', web_views.cost_center_create, name='create'),
    path('<int:pk>/update/', web_views.cost_center_update, name='update'),
    path('<int:pk>/delete/', web_views.cost_center_delete, name='delete'),
]

# Supplier URLs
supplier_patterns = [
    path('search.json', web_views.suppliers_search_json, name='search'),
    path('import/', supplier_views.import_upload, name='import'),
    path('import/template/', supplier_views.import_template, name='import_template'),
    path('import/<int:pk>/', supplier_views.import_preview, name='import_preview'),
    path('import/<int:pk>/confirm/', supplier_views.import_confirm, name='import_confirm'),
    path('import/<int:pk>/cancel/', supplier_views.import_cancel, name='import_cancel'),
    path('<int:pk>/', supplier_views.supplier_detail, name='detail'),
    path('<int:pk>/contacts/add/', supplier_views.contact_add, name='contact_add'),
    path('<int:pk>/contacts/<int:contact_pk>/delete/', supplier_views.contact_delete, name='contact_delete'),
    path('', web_views.SupplierListView.as_view(), name='list'),
    path('create/', web_views.supplier_create, name='create'),
    path('<int:pk>/update/', web_views.supplier_update, name='update'),
    path('<int:pk>/delete/', web_views.supplier_delete, name='delete'),
]

# Contract URLs
contract_patterns = [
    path('', web_views.ContractListView.as_view(), name='list'),
    path('export-excel/', web_views.contracts_export_excel, name='export_excel'),
    path('create/', web_views.contract_create, name='create'),
    path('<int:pk>/update/', web_views.contract_update, name='update'),
    path('<int:pk>/delete/', web_views.contract_delete, name='delete'),
]

# Item URLs
item_patterns = [
    path('', web_views.ItemListView.as_view(), name='list'),
    path('export-excel/', web_views.items_export_excel, name='export_excel'),
    path('create/', web_views.item_create, name='create'),
    path('<int:pk>/', web_views.ItemBatchDetailView.as_view(), name='detail'),
    path('<int:pk>/payment-status/', web_views.item_batch_update_payment_status, name='update_payment_status'),
    path('<int:pk>/delete/', web_views.item_batch_delete, name='delete'),
]

# Space Rental URLs
space_rental_patterns = [
    path('', web_views.SpaceRentalListView.as_view(), name='list'),
    path('export-excel/', web_views.space_rentals_export_excel, name='export_excel'),
    path('create/', web_views.space_rental_create, name='create'),
    path('<int:pk>/update/', web_views.space_rental_update, name='update'),
    path('<int:pk>/delete/', web_views.space_rental_delete, name='delete'),
]

# Payment URLs
payment_patterns = [
    path('', web_views.PaymentListView.as_view(), name='list'),
    path('export-excel/', web_views.payments_list_export_excel, name='list_export_excel'),
    path('create/', web_views.payment_create, name='create'),
    path('<int:pk>/', web_views.PaymentDetailView.as_view(), name='detail'),
    path('<int:pk>/update/', web_views.payment_update, name='update'),
    path('<int:pk>/status/', web_views.payment_change_status, name='change_status'),
    path('<int:pk>/delete/', web_views.payment_delete, name='delete'),
    path('<int:pk>/export-excel/', web_views.payment_export_excel, name='export_excel'),
]

# User URLs
user_patterns = [
    path('', web_views.UserListView.as_view(), name='list'),
    path('create/', web_views.user_create, name='create'),
    path('<int:pk>/update/', web_views.user_update, name='update'),
    path('<int:pk>/delete/', web_views.user_delete, name='delete'),
]

# Role URLs
role_patterns = [
    path('', web_views.RoleListView.as_view(), name='list'),
    path('create/', web_views.role_create, name='create'),
    path('<int:pk>/update/', web_views.role_update, name='update'),
    path('<int:pk>/delete/', web_views.role_delete, name='delete'),
]

# Notification URLs
notification_patterns = [
    path('json/', web_views.notifications_json, name='json'),
    path('mark-read/', web_views.notifications_mark_read, name='mark_read'),
]

# Audit URLs
audit_patterns = [
    path('', audit_views.audit_list, name='list'),
]

# Reconciliation URLs
reconciliation_patterns = [
    path('', recon_views.case_list, name='list'),
    path('create/', recon_views.case_create, name='create'),
    path('export-excel/', recon_views.case_export_excel, name='export_excel'),
    path('print/', recon_views.case_print, name='print'),
    path('executive/', dashboard_views.executive_dashboard, name='executive'),
    path('executive/export-excel/', dashboard_views.executive_export_excel, name='executive_excel'),
    path('executive/print/', dashboard_views.executive_print, name='executive_print'),
    path('distribution/', recon_views.distribution, name='distribution'),
    path('<int:pk>/', recon_views.case_detail, name='detail'),
    path('<int:pk>/transition/', recon_views.case_transition, name='transition'),
    path('<int:pk>/documents/upload/', recon_views.document_upload, name='document_upload'),
    path('<int:pk>/documents/<int:doc_pk>/download/', recon_views.document_download, name='document_download'),
    path('<int:pk>/documents/<int:doc_pk>/delete/', recon_views.document_delete, name='document_delete'),
    path('<int:pk>/result/', recon_views.result_save, name='result_save'),
    path('<int:pk>/differences/add/', recon_views.difference_add, name='difference_add'),
    path('<int:pk>/differences/<int:diff_pk>/toggle/', recon_views.difference_toggle, name='difference_toggle'),
    path('<int:pk>/differences/<int:diff_pk>/delete/', recon_views.difference_delete, name='difference_delete'),
]

# Payment proposal URLs
proposal_patterns = [
    path('', proposal_views.proposal_list, name='list'),
    path('create/', proposal_views.proposal_create, name='create'),
    path('<int:pk>/', proposal_views.proposal_detail, name='detail'),
    path('<int:pk>/edit/', proposal_views.proposal_edit, name='edit'),
    path('<int:pk>/transition/', proposal_views.proposal_transition, name='transition'),
    path('<int:pk>/attachments/upload/', proposal_views.attachment_upload, name='attachment_upload'),
    path('<int:pk>/attachments/<int:att_pk>/download/', proposal_views.attachment_download, name='attachment_download'),
    path('<int:pk>/attachments/<int:att_pk>/delete/', proposal_views.attachment_delete, name='attachment_delete'),
]

# WhatsApp URLs
whatsapp_patterns = [
    path('', whatsapp_views.connect_page, name='connect'),
    path('status/', whatsapp_views.status, name='status'),
    path('qr/', whatsapp_views.request_qr, name='qr'),
    path('disconnect/', whatsapp_views.disconnect, name='disconnect'),
    path('test/', whatsapp_views.send_test, name='test'),
    path('webhook/setup/', inbox_views.setup_webhook, name='setup_webhook'),
    path('webhook/<str:secret>/', inbox_views.webhook, name='webhook'),
]

# WhatsApp inbox URLs
inbox_patterns = [
    path('', inbox_views.inbox, name='inbox'),
    path('live/', inbox_views.inbox_live, name='live'),
    path('<int:pk>/', inbox_views.conversation, name='conversation'),
    path('<int:pk>/live/', inbox_views.conversation_live, name='conversation_live'),
    path('<int:pk>/send-ajax/', inbox_views.send_ajax, name='send_ajax'),
    path('<int:pk>/claim/', inbox_views.claim, name='claim'),
    path('<int:pk>/release/', inbox_views.release, name='release'),
    path('<int:pk>/assign/', inbox_views.assign, name='assign'),
    path('<int:pk>/status/', inbox_views.set_status, name='set_status'),
    path('<int:pk>/send/', inbox_views.send, name='send'),
    path('<int:pk>/typing/', inbox_views.typing, name='typing'),
    path('<int:pk>/messages/<int:msg_pk>/resend/', inbox_views.resend, name='resend'),
    path('<int:pk>/messages/<int:msg_pk>/media/', inbox_views.media_download, name='media'),
    path('<int:pk>/link-supplier/', inbox_views.link_supplier, name='link_supplier'),
    path('<int:pk>/create-supplier/', inbox_views.create_supplier, name='create_supplier'),
    path('<int:pk>/link-case/', inbox_views.link_case, name='link_case'),
]

# Service desk URLs
servicedesk_patterns = [
    path('', sd_views.request_list, name='list'),
    path('create/', sd_views.request_create, name='create'),
    path('types/', sd_views.type_list, name='types'),
    path('types/new/', sd_views.type_edit, name='type_new'),
    path('types/<int:pk>/', sd_views.type_edit, name='type_edit'),
    path('appointments/', sd_views.appointment_list, name='appointments'),
    path('<int:pk>/', sd_views.request_detail, name='detail'),
    path('<int:pk>/claim/', sd_views.request_claim, name='claim'),
    path('<int:pk>/assign/', sd_views.request_assign, name='assign'),
    path('<int:pk>/transition/', sd_views.request_transition, name='transition'),
    path('<int:pk>/documents/upload/', sd_views.document_upload, name='document_upload'),
    path('<int:pk>/documents/<int:doc_pk>/download/', sd_views.document_download, name='document_download'),
    path('<int:pk>/documents/<int:doc_pk>/delete/', sd_views.document_delete, name='document_delete'),
    path('<int:pk>/appointments/add/', sd_views.appointment_add, name='appointment_add'),
    path('<int:pk>/appointments/<int:appt_pk>/status/', sd_views.appointment_status, name='appointment_status'),
]

portal_patterns = [
    path('', portal_views.home, name='home'),
    path('requests/', portal_views.requests_list, name='list'),
    path('requests/<int:pk>/', portal_views.request_detail, name='detail'),
    path('requests/<int:pk>/documents/<int:doc_pk>/', portal_views.document_download, name='document'),
    path('new/<slug:code>/', portal_views.request_new, name='new'),
]

# Main URL patterns
urlpatterns = [
    path('live/badges/', core_live.badges_view, name='live_badges'),
    # Dashboard
    path('', web_views.dashboard_view, name='dashboard'),
    
    # Auth
    path('auth/', include((auth_patterns, 'auth'))),
    
    # Redirect /login/ to /auth/login/
    path('login/', RedirectView.as_view(pattern_name='auth:login', permanent=True)),
    
    # CRUD
    path('branches/', include((branch_patterns, 'branches'))),
    path('banks/', include((bank_patterns, 'banks'))),
    path('cost-centers/', include((cost_center_patterns, 'cost_centers'))),
    path('suppliers/', include((supplier_patterns, 'suppliers'))),
    path('contracts/', include((contract_patterns, 'contracts'))),
    path('items/', include((item_patterns, 'items'))),
    path('space-rentals/', include((space_rental_patterns, 'space_rentals'))),
    path('payments/', include((payment_patterns, 'payments'))),
    path('users/', include((user_patterns, 'users'))),
    path('roles/', include((role_patterns, 'roles'))),
    path('notifications/', include((notification_patterns, 'notifications'))),
    path('audit/', include((audit_patterns, 'audit'))),
    path('reconciliation/', include((reconciliation_patterns, 'reconciliation'))),
    path('proposals/', include((proposal_patterns, 'proposals'))),
    path('whatsapp/', include((whatsapp_patterns, 'whatsapp'))),
    path('inbox/', include((inbox_patterns, 'whatsapp_inbox'))),
    path('service-requests/', include((servicedesk_patterns, 'servicedesk'))),
    path('portal/', include((portal_patterns, 'portal'))),
]
