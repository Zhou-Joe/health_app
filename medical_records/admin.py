from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from .models import (
    HealthCheckup, HealthIndicator, HealthAdvice,
    DocumentProcessing, SystemSettings, Medication, MedicationRecord,
    HealthEvent, EventItem, EventTemplate, SymptomEntry, VitalEntry
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


class EventItemInline(GenericTabularInline):
    """事件项目内联编辑"""
    model = EventItem
    extra = 0
    readonly_fields = ['content_object', 'added_by', 'added_at']
    fields = ['content_object', 'notes', 'added_by', 'added_at']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(HealthEvent)
class HealthEventAdmin(admin.ModelAdmin):
    list_display = ['user', 'name', 'event_type', 'status', 'start_date', 'end_date', 'duration_display', 'item_count', 'is_auto_generated', 'created_at']
    list_filter = ['event_type', 'status', 'is_auto_generated', 'start_date', 'created_at']
    search_fields = ['user__username', 'name', 'description']
    date_hierarchy = 'start_date'
    ordering = ['-start_date']
    readonly_fields = ['created_at', 'updated_at', 'item_count', 'duration_days']
    inlines = [EventItemInline]

    fieldsets = (
        ('基本信息', {
            'fields': ('user', 'name', 'event_type', 'status', 'is_auto_generated')
        }),
        ('时间范围', {
            'fields': ('start_date', 'end_date', 'duration_days')
        }),
        ('描述', {
            'fields': ('description',)
        }),
        ('元数据', {
            'fields': ('created_at', 'updated_at', 'item_count'),
            'classes': ('collapse',)
        }),
    )

    def duration_display(self, obj):
        """显示持续时长"""
        days = obj.duration_days
        if days == 1:
            return "1天"
        return f"{days}天"
    duration_display.short_description = '持续时长'

    def item_count(self, obj):
        """显示关联记录数"""
        return obj.get_item_count()
    item_count.short_description = '记录数'

    actions = ['auto_cluster_selected']

    def auto_cluster_selected(self, request, queryset):
        """为选中用户的记录自动聚类"""
        users = queryset.values_list('user', flat=True).distinct()
        events_created = 0
        for user_id in users:
            from django.contrib.auth.models import User
            user = User.objects.get(id=user_id)
            events_created += HealthEvent.auto_cluster_user_records(user)

        from django.contrib import messages
        messages.success(request, f'已为 {len(users)} 个用户自动聚类，创建了 {events_created} 个事件')
    auto_cluster_selected.short_description = '为选中记录的用户执行自动聚类'


@admin.register(EventItem)
class EventItemAdmin(admin.ModelAdmin):
    list_display = ['event', 'content_type', 'object_summary', 'added_by', 'added_at']
    list_filter = ['content_type', 'added_by', 'added_at']
    search_fields = ['event__name', 'event__user__username', 'notes']
    ordering = ['-added_at']
    readonly_fields = ['added_at']

    def object_summary(self, obj):
        """显示对象摘要"""
        return obj.item_summary
    object_summary.short_description = '记录摘要'


@admin.register(EventTemplate)
class EventTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'event_type', 'suggested_duration_days', 'is_system_template', 'is_active', 'created_at']
    list_filter = ['event_type', 'is_system_template', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['is_system_template', 'name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'description', 'event_type')
        }),
        ('模板配置', {
            'fields': ('suggested_duration_days', 'default_name_template', 'is_system_template', 'is_active')
        }),
        ('元数据', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['create_default_templates']

    def create_default_templates(self, request, queryset):
        """创建默认的系统模板"""
        templates = [
            {
                'name': '年度体检',
                'description': '年度健康体检事件',
                'event_type': 'checkup',
                'suggested_duration_days': 1,
                'default_name_template': '{date} 年度体检',
                'is_system_template': True,
            },
            {
                'name': '感冒治疗',
                'description': '普通感冒或流感治疗过程',
                'event_type': 'illness',
                'suggested_duration_days': 7,
                'default_name_template': '{date} 感冒治疗',
                'is_system_template': True,
            },
            {
                'name': '高血压管理',
                'description': '高血压慢性病管理',
                'event_type': 'chronic_management',
                'suggested_duration_days': 365,
                'default_name_template': '高血压管理',
                'is_system_template': True,
            },
            {
                'name': '糖尿病管理',
                'description': '糖尿病慢性病管理',
                'event_type': 'chronic_management',
                'suggested_duration_days': 365,
                'default_name_template': '糖尿病管理',
                'is_system_template': True,
            },
            {
                'name': '急诊',
                'description': '急诊就诊事件',
                'event_type': 'emergency',
                'suggested_duration_days': 1,
                'default_name_template': '{date} 急诊',
                'is_system_template': True,
            },
            {
                'name': '健康体检套餐',
                'description': '全面健康体检套餐',
                'event_type': 'checkup',
                'suggested_duration_days': 3,
                'default_name_template': '{date} 健康体检套餐',
                'is_system_template': True,
            },
            {
                'name': '抗生素疗程',
                'description': '抗生素药物治疗疗程',
                'event_type': 'medication_course',
                'suggested_duration_days': 7,
                'default_name_template': '抗生素疗程',
                'is_system_template': True,
            },
            {
                'name': '疫苗接种',
                'description': '疫苗接种记录',
                'event_type': 'wellness',
                'suggested_duration_days': 1,
                'default_name_template': '{date} 疫苗接种',
                'is_system_template': True,
            },
        ]

        created_count = 0
        for template_data in templates:
            # 检查是否已存在同名模板
            if not EventTemplate.objects.filter(name=template_data['name']).exists():
                EventTemplate.objects.create(**template_data)
                created_count += 1

        from django.contrib import messages
        messages.success(request, f'已创建 {created_count} 个默认模板')
    create_default_templates.short_description = '创建默认系统模板'


@admin.register(SymptomEntry)
class SymptomEntryAdmin(admin.ModelAdmin):
    """症状日志管理"""
    list_display = ['user', 'entry_date', 'symptom', 'severity_display', 'related_checkup', 'related_medication', 'created_at']
    list_filter = ['severity', 'entry_date', 'created_at']
    search_fields = ['user__username', 'symptom', 'notes']
    date_hierarchy = 'entry_date'
    ordering = ['-entry_date', '-created_at']
    readonly_fields = ['created_at', 'updated_at']

    def severity_display(self, obj):
        """显示严重程度"""
        return dict(obj.SEVERITY_CHOICES).get(obj.severity, obj.severity)
    severity_display.short_description = '严重程度'


@admin.register(VitalEntry)
class VitalEntryAdmin(admin.ModelAdmin):
    """体征日志管理"""
    list_display = ['user', 'entry_date', 'vital_type_display', 'value', 'unit', 'related_checkup', 'related_medication', 'created_at']
    list_filter = ['vital_type', 'entry_date', 'created_at']
    search_fields = ['user__username', 'value', 'notes']
    date_hierarchy = 'entry_date'
    ordering = ['-entry_date', '-created_at']
    readonly_fields = ['created_at', 'updated_at']

    def vital_type_display(self, obj):
        """显示体征类型"""
        return dict(obj.VITAL_TYPE_CHOICES).get(obj.vital_type, obj.vital_type)
    vital_type_display.short_description = '体征类型'
