from django.contrib import admin
from .models import HealthCheckup, HealthIndicator, HealthAdvice, DocumentProcessing, SystemSettings


@admin.register(HealthCheckup)
class HealthCheckupAdmin(admin.ModelAdmin):
    list_display = ['user', 'checkup_date', 'hospital', 'created_at']
    list_filter = ['checkup_date', 'hospital', 'created_at']
    search_fields = ['user__username', 'hospital', 'notes']
    date_hierarchy = 'checkup_date'
    ordering = ['-checkup_date']


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
