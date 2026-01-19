from django.contrib import admin
from .models import (
    HealthCheckup, HealthIndicator, HealthAdvice,
    DocumentProcessing, SystemSettings, Medication, MedicationRecord
)


@admin.register(HealthCheckup)
class HealthCheckupAdmin(admin.ModelAdmin):
    list_display = ['user', 'checkup_date', 'hospital', 'notes_preview', 'created_at']
    list_filter = ['checkup_date', 'hospital', 'created_at']
    search_fields = ['user__username', 'hospital', 'notes']
    date_hierarchy = 'checkup_date'
    ordering = ['-checkup_date']

    def notes_preview(self, obj):
        if obj.notes and len(obj.notes) > 30:
            return obj.notes[:30] + '...'
        return obj.notes or '-'
    notes_preview.short_description = '备注'


@admin.register(HealthIndicator)
class HealthIndicatorAdmin(admin.ModelAdmin):
    list_display = ['checkup', 'indicator_name', 'indicator_type', 'value', 'unit', 'status']
    list_filter = ['indicator_type', 'status', 'checkup__checkup_date']
    search_fields = ['indicator_name', 'value', 'checkup__user__username']
    date_hierarchy = 'checkup__checkup_date'
    ordering = ['-checkup__checkup_date']


@admin.register(HealthAdvice)
class HealthAdviceAdmin(admin.ModelAdmin):
    list_display = ['user', 'question_short', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'question', 'answer']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']

    def question_short(self, obj):
        return obj.question[:50] + '...' if len(obj.question) > 50 else obj.question
    question_short.short_description = '问题'


@admin.register(DocumentProcessing)
class DocumentProcessingAdmin(admin.ModelAdmin):
    list_display = ['user', 'health_checkup', 'status', 'progress', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'health_checkup__hospital']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ['name', 'key', 'value_preview', 'is_active', 'updated_at']
    list_filter = ['is_active', 'updated_at']
    search_fields = ['name', 'key', 'description']
    list_editable = ['is_active']
    ordering = ['name']

    def value_preview(self, obj):
        if len(obj.value) > 50:
            return obj.value[:50] + '...'
        return obj.value
    value_preview.short_description = '设置值'


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ['user', 'medicine_name', 'dosage', 'start_date', 'end_date', 'progress_info', 'is_active', 'created_at']
    list_filter = ['is_active', 'start_date', 'created_at']
    search_fields = ['user__username', 'medicine_name', 'dosage', 'notes']
    date_hierarchy = 'start_date'
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']

    def progress_info(self, obj):
        return f"{obj.days_taken}/{obj.total_days}天 ({obj.progress_percentage}%)"
    progress_info.short_description = '服药进度'


@admin.register(MedicationRecord)
class MedicationRecordAdmin(admin.ModelAdmin):
    list_display = ['medication', 'record_date', 'get_frequency_display', 'taken_at', 'notes']
    list_filter = ['frequency', 'record_date', 'taken_at']
    search_fields = ['medication__medicine_name', 'medication__user__username', 'notes']
    date_hierarchy = 'record_date'
    ordering = ['-record_date', '-taken_at']
    readonly_fields = ['taken_at']
