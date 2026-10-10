from django.contrib import admin

from .models import (ReconciliationCase, ReconciliationDifference, ReconciliationDocument, ReconciliationResult,
                     StatusHistory, WorkAssignment)


class ReadOnlyInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class HistoryInline(ReadOnlyInline):
    model = StatusHistory


@admin.register(ReconciliationCase)
class ReconciliationCaseAdmin(admin.ModelAdmin):
    list_display = ('reference', 'supplier', 'status', 'priority', 'assigned_accountant', 'due_date')
    list_filter = ('status', 'priority')
    search_fields = ('reference', 'supplier__name', 'supplier__code')
    inlines = [HistoryInline]


admin.site.register([ReconciliationDocument, ReconciliationResult, ReconciliationDifference, WorkAssignment])
