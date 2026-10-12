from django.contrib import admin

from .models import Attachment, Complaint, MatchRequest, Message


@admin.register(MatchRequest)
class MatchRequestAdmin(admin.ModelAdmin):
    list_display = ('code', 'supplier_org', 'period', 'stage', 'matcher', 'created_at')
    list_filter = ('stage',)
    search_fields = ('code', 'supplier_org')


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('code', 'supplier_org', 'category', 'stage', 'created_at')
    list_filter = ('stage', 'category')
    search_fields = ('code', 'supplier_org', 'subject')


admin.site.register(Message)
admin.site.register(Attachment)
