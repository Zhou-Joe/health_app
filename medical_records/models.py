from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from datetime import date, timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver


class HealthCheckup(models.Model):
    """体检报告模型"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    checkup_date = models.DateField(verbose_name='体检日期')
    hospital = models.CharField(max_length=200, verbose_name='体检机构')
    report_file = models.FileField(upload_to='reports/%Y/%m/', blank=True, null=True, verbose_name='报告文件')
    notes = models.TextField(blank=True, null=True, verbose_name='备注')
    ai_summary = models.TextField(blank=True, null=True, verbose_name='AI解读总结')
    ai_summary_created_at = models.DateTimeField(blank=True, null=True, verbose_name='AI总结生成时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '体检报告'
        verbose_name_plural = '体检报告'
        ordering = ['-checkup_date']

    def __str__(self):
        return f"{self.user.username} - {self.checkup_date} - {self.hospital}"


class HealthIndicator(models.Model):
    """健康指标模型"""
    INDICATOR_TYPES = [
        # 一般检查
        ('general_exam', '一般检查'),

        # 血液检验
        ('blood_routine', '血常规'),
        ('biochemistry', '生化检验'),
        ('liver_function', '肝功能'),
        ('kidney_function', '肾功能'),
        ('thyroid', '甲状腺'),
        ('cardiac', '心脏标志物'),
        ('tumor_markers', '肿瘤标志物'),
        ('infection', '感染炎症'),
        ('blood_rheology', '血液流变'),
        ('coagulation', '凝血功能'),

        # 体液检验
        ('urine', '尿液检查'),
        ('stool', '粪便检查'),
        ('pathology', '病理检查'),

        # 影像学检查
        ('ultrasound', '超声检查'),
        ('X_ray', 'X线检查'),
        ('CT_MRI', 'CT和MRI'),
        ('endoscopy', '内镜检查'),

        # 功能和专科检查
        ('special_organs', '专科检查'),

        # 其他
        ('other', '其他检查'),
    ]

    checkup = models.ForeignKey(HealthCheckup, on_delete=models.CASCADE, verbose_name='体检报告', related_name='indicators')
    indicator_type = models.CharField(max_length=50, choices=INDICATOR_TYPES, verbose_name='指标类型')
    indicator_name = models.CharField(max_length=100, verbose_name='指标名称')
    value = models.CharField(max_length=100, verbose_name='检测值')
    unit = models.CharField(max_length=20, blank=True, null=True, verbose_name='单位')
    reference_range = models.CharField(max_length=100, blank=True, null=True, verbose_name='参考范围')
    status = models.CharField(max_length=20, choices=[
        ('normal', '正常'),
        ('abnormal', '异常'),
        ('attention', '关注'),
    ], default='normal', verbose_name='状态')

    class Meta:
        verbose_name = '健康指标'
        verbose_name_plural = '健康指标'

    def __str__(self):
        return f"{self.checkup.checkup_date} - {self.indicator_name}: {self.value}"


class Conversation(models.Model):
    """对话模型"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    title = models.CharField(max_length=200, verbose_name='对话标题')
    ai_summary = models.TextField(blank=True, null=True, verbose_name='AI对话总结')
    ai_summary_created_at = models.DateTimeField(blank=True, null=True, verbose_name='AI总结生成时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    is_active = models.BooleanField(default=True, verbose_name='是否活跃')

    class Meta:
        verbose_name = '对话'
        verbose_name_plural = '对话'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"

    @classmethod
    def get_user_conversations(cls, user, limit=20):
        """获取用户的对话列表"""
        return cls.objects.filter(user=user, is_active=True).order_by('-updated_at')[:limit]

    @classmethod
    def create_new_conversation(cls, user, title=None):
        """创建新对话"""
        if not title:
            title = f"新对话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        return cls.objects.create(user=user, title=title)

    def get_latest_message(self):
        """获取对话中的最新消息"""
        latest_advice = self.healthadvice_set.order_by('-created_at').first()
        return latest_advice

    def get_message_count(self):
        """获取对话中的消息数量"""
        return self.healthadvice_set.count()


class HealthAdvice(models.Model):
    """AI健康建议模型"""
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, null=True, blank=True, verbose_name='所属对话')
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    question = models.TextField(verbose_name='用户问题')
    answer = models.TextField(verbose_name='AI建议')
    is_generating = models.BooleanField(default=False, verbose_name='是否正在生成')
    prompt_sent = models.TextField(blank=True, null=True, verbose_name='发送的Prompt')
    conversation_context = models.TextField(blank=True, null=True, verbose_name='对话上下文')
    selected_reports = models.TextField(blank=True, null=True, verbose_name='选中的报告ID列表（JSON格式）')
    selected_medications = models.TextField(blank=True, null=True, verbose_name='选中的药单ID列表（JSON格式）')
    selected_event = models.IntegerField(blank=True, null=True, verbose_name='选中的健康事件ID')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '健康建议'
        verbose_name_plural = '健康建议'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @classmethod
    def get_conversation_messages(cls, conversation_id):
        """获取对话中的所有消息"""
        return cls.objects.filter(conversation_id=conversation_id).order_by('created_at')

    @classmethod
    def get_user_messages_without_conversation(cls, user):
        """获取用户没有关联对话的消息（旧数据兼容）"""
        return cls.objects.filter(user=user, conversation__isnull=True).order_by('-created_at')


class DocumentProcessing(models.Model):
    """文档处理状态跟踪"""
    PROCESSING_STATUS = [
        ('pending', '等待处理'),
        ('uploading', '上传中'),
        ('ocr_processing', 'OCR识别中'),
        ('ai_processing', 'AI处理中'),
        ('saving_data', '保存数据中'),
        ('completed', '处理完成'),
        ('failed', '处理失败'),
    ]

    WORKFLOW_TYPES = [
        ('ocr_llm', 'MinerU Pipeline 模式 (OCR + LLM)'),
        ('vlm_transformers', 'MinerU VLM-Transformers 模式 (OCR + LLM)'),
        ('vl_model', '多模态大模型模式 (直接识别)'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    health_checkup = models.OneToOneField(HealthCheckup, on_delete=models.CASCADE, verbose_name='体检报告')
    workflow_type = models.CharField(
        max_length=20,
        choices=WORKFLOW_TYPES,
        default='ocr_llm',
        verbose_name='处理工作流'
    )
    status = models.CharField(max_length=20, choices=PROCESSING_STATUS, default='pending', verbose_name='处理状态')
    progress = models.IntegerField(default=0, verbose_name='处理进度(%)')
    ocr_result = models.TextField(blank=True, null=True, verbose_name='OCR识别结果')
    ai_result = models.JSONField(blank=True, null=True, verbose_name='AI处理结果')
    vl_model_result = models.JSONField(blank=True, null=True, verbose_name='多模态模型处理结果')
    error_message = models.TextField(blank=True, null=True, verbose_name='错误信息')
    processing_time = models.DurationField(blank=True, null=True, verbose_name='处理耗时')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '文档处理'
        verbose_name_plural = '文档处理'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.get_status_display()}"


class SystemSettings(models.Model):
    """系统设置模型"""

    name = models.CharField(max_length=100, unique=True, verbose_name='设置名称')
    key = models.CharField(max_length=100, unique=True, verbose_name='设置键名')
    value = models.TextField(verbose_name='设置值')
    description = models.TextField(blank=True, verbose_name='描述')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '系统设置'
        verbose_name_plural = '系统设置'
        ordering = ['name']

    def __str__(self):
        return f"{self.name}: {self.value}"

    @classmethod
    def get_setting(cls, key, default=None):
        """获取设置值"""
        try:
            setting = cls.objects.get(key=key, is_active=True)
            return setting.value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_setting(cls, key, value, name=None, description=''):
        """设置值"""
        setting, created = cls.objects.update_or_create(
            key=key,
            defaults={
                'name': name or key,
                'value': value,
                'description': description,
                'is_active': True
            }
        )
        if not created:
            setting.value = value
            setting.description = description
            setting.save()
        return setting

    @classmethod
    def get_default_workflow(cls):
        """获取默认工作流（已废弃，保留兼容性）"""
        return cls.get_setting('default_workflow', 'ocr_llm')

    @classmethod
    def get_pdf_ocr_workflow(cls):
        """获取PDF文件OCR工作流"""
        return cls.get_setting('pdf_ocr_workflow', 'ocr_llm')

    @classmethod
    def get_vl_model_config(cls):
        """获取多模态模型配置"""
        return {
            'provider': cls.get_setting('vl_model_provider', 'openai'),
            'api_url': cls.get_setting('vl_model_api_url', ''),
            'api_key': cls.get_setting('vl_model_api_key', ''),
            'model_name': cls.get_setting('vl_model_name', 'gpt-4-vision-preview'),
            'timeout': cls.get_setting('vl_model_timeout', '300'),
            'max_tokens': cls.get_setting('vl_model_max_tokens', '4000'),
        }

    @classmethod
    def get_gemini_config(cls):
        """获取Google Gemini配置"""
        return {
            'api_key': cls.get_setting('gemini_api_key', ''),
            'model_name': cls.get_setting('gemini_model_name', 'gemini-3.0-flash'),
            'timeout': cls.get_setting('gemini_timeout', '300'),
        }

    @classmethod
    def get_ai_doctor_config(cls):
        """获取AI医生配置"""
        return {
            'api_url': cls.get_setting('ai_doctor_api_url', ''),
            'api_key': cls.get_setting('ai_doctor_api_key', ''),
            'model_name': cls.get_setting('ai_doctor_model_name', ''),
            'timeout': cls.get_setting('ai_doctor_timeout', '120'),
            'provider': cls.get_setting('ai_doctor_provider', 'openai'),  # 'openai' 或 'gemini'
        }

    @classmethod
    def get_llm_config(cls):
        """获取数据整合LLM配置"""
        return {
            'api_url': cls.get_setting('llm_api_url', ''),
            'api_key': cls.get_setting('llm_api_key', ''),
            'model_name': cls.get_setting('llm_model_name', ''),
            'timeout': cls.get_setting('llm_timeout', '3600'),
            'provider': cls.get_setting('llm_provider', 'openai'),  # 'openai' 或 'gemini'
        }


class UserProfile(models.Model):
    """用户信息扩展"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='用户')
    avatar_url = models.URLField(max_length=500, blank=True, null=True, verbose_name='头像URL')
    birth_date = models.DateField(null=True, blank=True, verbose_name='出生日期')
    gender = models.CharField(
        max_length=10,
        choices=[
            ('male', '男'),
            ('female', '女'),
        ],
        blank=True,
        verbose_name='性别'
    )
    # AI处理模式
    processing_mode = models.CharField(
        max_length=20,
        choices=[
            ('stream', '实时模式'),  # 流式响应，需要保持页面打开
            ('background', '后台模式'),  # 后台任务，可以离开页面
        ],
        default='background',  # 默认后台模式
        verbose_name='AI处理模式'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '用户信息'
        verbose_name_plural = '用户信息'

    def __str__(self):
        return f"{self.user.username} 的基本信息"

    @property
    def age(self):
        """计算年龄"""
        if self.birth_date:
            today = date.today()
            return today.year - self.birth_date.year - ((today.month, today.day) < (self.birth_date.month, self.birth_date.day))
        return None

    def get_gender_display(self):
        """获取性别显示文本"""
        gender_map = {
            'male': '男',
            'female': '女',
        }
        return gender_map.get(self.gender, '未设置')


# 自动创建UserProfile
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """当用户创建时自动创建UserProfile"""
    if created:
        UserProfile.objects.create(user=instance)


class MedicationGroup(models.Model):
    """药单组模型 - 用于存储一次图片识别产生的多条药单"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    name = models.CharField(max_length=200, verbose_name='药单组名称')
    source_image = models.ImageField(upload_to='medication_images/%Y/%m/', blank=True, null=True, verbose_name='来源图片')
    ai_summary = models.TextField(blank=True, null=True, verbose_name='AI总结')
    raw_result = models.JSONField(blank=True, null=True, verbose_name='原始识别结果')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '药单组'
        verbose_name_plural = '药单组'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.name}"

    @property
    def medication_count(self):
        """药单数量"""
        return self.medications.count()


class Medication(models.Model):
    """药单模型"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    group = models.ForeignKey(MedicationGroup, on_delete=models.SET_NULL, blank=True, null=True, verbose_name='所属药单组', related_name='medications')
    medicine_name = models.CharField(max_length=200, verbose_name='药名')
    dosage = models.CharField(max_length=100, verbose_name='服药方式')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(verbose_name='结束日期')
    notes = models.TextField(blank=True, null=True, verbose_name='备注')
    is_active = models.BooleanField(default=True, verbose_name='是否有效')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '药单'
        verbose_name_plural = '药单'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.medicine_name}"

    @property
    def total_days(self):
        """计算总天数"""
        return (self.end_date - self.start_date).days + 1

    @property
    def days_taken(self):
        """已服药天数"""
        return self.medicationrecord_set.count()

    @property
    def progress_percentage(self):
        """完成百分比"""
        if self.total_days > 0:
            return int((self.days_taken / self.total_days) * 100)
        return 0


class MedicationRecord(models.Model):
    """服药记录模型"""
    FREQUENCY_CHOICES = [
        ('once', '一次'),
        ('daily', '每日一次'),
        ('twice_daily', '每日两次'),
        ('three_times_daily', '每日三次'),
        ('four_times_daily', '每日四次'),
        ('weekly', '每周一次'),
        ('as_needed', '按需服用'),
    ]

    medication = models.ForeignKey(Medication, on_delete=models.CASCADE, verbose_name='药单')
    record_date = models.DateField(verbose_name='服药日期')
    taken_at = models.DateTimeField(auto_now_add=True, verbose_name='服药时间')
    notes = models.TextField(blank=True, null=True, verbose_name='备注')
    frequency = models.CharField(
        max_length=20,
        choices=FREQUENCY_CHOICES,
        default='daily',
        verbose_name='服药频率'
    )

    class Meta:
        verbose_name = '服药记录'
        verbose_name_plural = '服药记录'
        ordering = ['-record_date']
        unique_together = ['medication', 'record_date']  # 同一天只能有一条记录

    def __str__(self):
        return f"{self.medication.medicine_name} - {self.record_date}"


class SymptomEntry(models.Model):
    """症状日志"""
    SEVERITY_CHOICES = [
        (1, '轻微'),
        (2, '轻度'),
        (3, '中度'),
        (4, '严重'),
        (5, '非常严重'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    entry_date = models.DateField(verbose_name='日期', default=date.today)
    symptom = models.CharField(max_length=200, verbose_name='症状')
    severity = models.IntegerField(choices=SEVERITY_CHOICES, default=3, verbose_name='严重程度')
    notes = models.TextField(blank=True, null=True, verbose_name='备注')
    related_checkup = models.ForeignKey(HealthCheckup, on_delete=models.SET_NULL, blank=True, null=True, verbose_name='关联体检')
    related_medication = models.ForeignKey(Medication, on_delete=models.SET_NULL, blank=True, null=True, verbose_name='关联药单')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '症状日志'
        verbose_name_plural = '症状日志'
        ordering = ['-entry_date', '-created_at']

    def __str__(self):
        return f"{self.entry_date} - {self.symptom}"


class VitalEntry(models.Model):
    """体征日志"""
    VITAL_TYPE_CHOICES = [
        ('blood_pressure', '血压'),
        ('heart_rate', '心率'),
        ('weight', '体重'),
        ('temperature', '体温'),
        ('blood_sugar', '血糖'),
        ('oxygen', '血氧'),
        ('other', '其他'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    entry_date = models.DateField(verbose_name='日期', default=date.today)
    vital_type = models.CharField(max_length=50, choices=VITAL_TYPE_CHOICES, verbose_name='体征类型')
    value = models.CharField(max_length=100, verbose_name='数值')
    unit = models.CharField(max_length=20, blank=True, null=True, verbose_name='单位')
    notes = models.TextField(blank=True, null=True, verbose_name='备注')
    related_checkup = models.ForeignKey(HealthCheckup, on_delete=models.SET_NULL, blank=True, null=True, verbose_name='关联体检')
    related_medication = models.ForeignKey(Medication, on_delete=models.SET_NULL, blank=True, null=True, verbose_name='关联药单')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '体征日志'
        verbose_name_plural = '体征日志'
        ordering = ['-entry_date', '-created_at']

    def __str__(self):
        return f"{self.entry_date} - {self.get_vital_type_display()} {self.value}{self.unit or ''}"


class CarePlan(models.Model):
    """健康管理计划"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    title = models.CharField(max_length=200, verbose_name='计划标题')
    description = models.TextField(blank=True, null=True, verbose_name='计划描述')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '健康管理计划'
        verbose_name_plural = '健康管理计划'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class CareGoal(models.Model):
    """健康目标"""
    STATUS_CHOICES = [
        ('active', '进行中'),
        ('completed', '已完成'),
        ('paused', '已暂停'),
    ]

    plan = models.ForeignKey(CarePlan, on_delete=models.CASCADE, related_name='goals', verbose_name='所属计划')
    title = models.CharField(max_length=200, verbose_name='目标标题')
    target_value = models.CharField(max_length=100, blank=True, null=True, verbose_name='目标值')
    unit = models.CharField(max_length=20, blank=True, null=True, verbose_name='单位')
    due_date = models.DateField(blank=True, null=True, verbose_name='目标日期')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name='状态')
    progress_percent = models.IntegerField(default=0, verbose_name='进度百分比')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '健康目标'
        verbose_name_plural = '健康目标'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.plan.title} - {self.title}"

    def recalculate_progress(self):
        actions = self.actions.all()
        total = actions.count()
        if total == 0:
            self.progress_percent = 0
        else:
            done = actions.filter(status='done').count()
            self.progress_percent = int((done / total) * 100)
        self.save(update_fields=['progress_percent'])


class CareAction(models.Model):
    """健康行动"""
    STATUS_CHOICES = [
        ('pending', '待完成'),
        ('done', '已完成'),
    ]

    goal = models.ForeignKey(CareGoal, on_delete=models.CASCADE, related_name='actions', verbose_name='所属目标')
    title = models.CharField(max_length=200, verbose_name='行动')
    frequency = models.CharField(max_length=50, blank=True, null=True, verbose_name='频率')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    suggested_by_ai = models.BooleanField(default=False, verbose_name='AI建议')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '健康行动'
        verbose_name_plural = '健康行动'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.goal.title} - {self.title}"


class CaregiverAccess(models.Model):
    """家属/照护者访问授权"""
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='caregiver_links', verbose_name='授权人')
    caregiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='caregiver_accesses', verbose_name='照护者')
    relationship = models.CharField(max_length=50, blank=True, null=True, verbose_name='关系')
    can_view_records = models.BooleanField(default=True, verbose_name='可查看体检报告')
    can_view_medications = models.BooleanField(default=True, verbose_name='可查看药单')
    can_view_events = models.BooleanField(default=False, verbose_name='可查看事件')
    can_view_diary = models.BooleanField(default=False, verbose_name='可查看日志')
    can_manage_medications = models.BooleanField(default=False, verbose_name='可管理药单')
    is_active = models.BooleanField(default=True, verbose_name='是否有效')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        verbose_name = '照护者授权'
        verbose_name_plural = '照护者授权'
        constraints = [
            models.UniqueConstraint(fields=['owner', 'caregiver'], name='unique_caregiver_access')
        ]

    def __str__(self):
        return f"{self.owner.username} -> {self.caregiver.username}"


class HealthEvent(models.Model):
    """健康事件聚合模型"""
    EVENT_TYPE_CHOICES = [
        ('illness', '疾病事件'),
        ('checkup', '体检事件'),
        ('chronic_management', '慢性病管理'),
        ('emergency', '急诊事件'),
        ('wellness', '健康管理'),
        ('medication_course', '用药疗程'),
        ('other', '其他'),
    ]
    STATUS_PENDING = 'pending'
    STATUS_OBSERVING = 'observing'
    STATUS_RECOVERED = 'recovered'
    EVENT_STATUS_CHOICES = [
        (STATUS_PENDING, '待处理'),
        (STATUS_OBSERVING, '观察中'),
        (STATUS_RECOVERED, '治愈'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户', related_name='health_events')
    name = models.CharField(max_length=200, verbose_name='事件名称')
    description = models.TextField(blank=True, null=True, verbose_name='事件描述')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(blank=True, null=True, verbose_name='结束日期')
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES, default='other', verbose_name='事件类型')
    status = models.CharField(max_length=20, choices=EVENT_STATUS_CHOICES, default=STATUS_OBSERVING, verbose_name='状态')
    is_auto_generated = models.BooleanField(default=False, verbose_name='是否自动生成')
    ai_summary = models.TextField(blank=True, null=True, verbose_name='AI事件总结')
    ai_summary_created_at = models.DateTimeField(blank=True, null=True, verbose_name='AI总结生成时间')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '健康事件'
        verbose_name_plural = '健康事件'
        ordering = ['-start_date']
        indexes = [
            models.Index(fields=['user', '-start_date']),
            models.Index(fields=['event_type']),
            models.Index(fields=['status']),
            models.Index(fields=['is_auto_generated']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.name} ({self.start_date})"

    @property
    def duration_days(self):
        """计算事件持续天数"""
        if self.end_date:
            return (self.end_date - self.start_date).days + 1
        # 如果没有结束日期，计算到今天
        return (date.today() - self.start_date).days + 1

    def get_all_items(self):
        """获取事件关联的所有健康记录"""
        return self.event_items.all()

    def get_checkups(self):
        """获取关联的体检报告"""
        return self.event_items.filter(
            content_type__model='healthcheckup'
        )

    def get_medications(self):
        """获取关联的药单"""
        return self.event_items.filter(
            content_type__model='medication'
        )

    def get_indicators(self):
        """获取关联的健康指标"""
        return self.event_items.filter(
            content_type__model='healthindicator'
        )

    def get_item_count(self):
        """获取关联记录总数"""
        return self.event_items.count()

    @classmethod
    def auto_cluster_user_records(cls, user, days_threshold=7):
        """
        自动聚类用户的健康记录为事件
        将所有类型的记录（体检报告、药单组、药单、症状日志等）按时间统一聚类

        Args:
            user: 用户对象
            days_threshold: 时间阈值（天），在此时间窗口内的记录会被聚为一类

        Returns:
            创建的事件数量
        """
        from django.db.models import Q

        events_created = 0

        all_records = []

        for checkup in HealthCheckup.objects.filter(user=user):
            all_records.append({
                'type': 'healthcheckup',
                'date': checkup.checkup_date,
                'obj': checkup,
                'name': f"体检报告 - {checkup.hospital}"
            })

        for group in MedicationGroup.objects.filter(user=user):
            group_date = group.created_at.date() if hasattr(group.created_at, 'date') else group.created_at
            all_records.append({
                'type': 'medicationgroup',
                'date': group_date,
                'obj': group,
                'name': f"药单组 - {group.name}"
            })

        for med in Medication.objects.filter(user=user, is_active=True, group__isnull=True):
            all_records.append({
                'type': 'medication',
                'date': med.start_date,
                'obj': med,
                'name': f"药单 - {med.medicine_name}"
            })

        try:
            from .models import SymptomEntry
            for symptom in SymptomEntry.objects.filter(user=user):
                all_records.append({
                    'type': 'symptomentry',
                    'date': symptom.entry_date,
                    'obj': symptom,
                    'name': f"症状 - {symptom.symptom[:20]}"
                })
        except Exception:
            pass

        try:
            from .models import VitalEntry
            for vital in VitalEntry.objects.filter(user=user):
                all_records.append({
                    'type': 'vitalentry',
                    'date': vital.entry_date,
                    'obj': vital,
                    'name': f"体征 - {vital.get_vital_type_display()}"
                })
        except Exception:
            pass

        all_records.sort(key=lambda x: x['date'])

        if not all_records:
            return 0

        clusters = []
        current_cluster = []

        for record in all_records:
            if not current_cluster:
                current_cluster.append(record)
            else:
                first_date = current_cluster[0]['date']
                days_diff = abs((record['date'] - first_date).days)

                if days_diff <= days_threshold:
                    current_cluster.append(record)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [record]

        if current_cluster:
            clusters.append(current_cluster)

        for cluster in clusters:
            if not cluster:
                continue

            dates = [r['date'] for r in cluster]
            start_date = min(dates)
            end_date = max(dates)

            type_counts = {}
            for r in cluster:
                t = r['type']
                type_counts[t] = type_counts.get(t, 0) + 1

            type_names = {
                'healthcheckup': '体检报告',
                'medicationgroup': '药单组',
                'medication': '药单',
                'symptomentry': '症状日志',
                'vitalentry': '体征记录',
            }

            type_desc_parts = []
            for t, count in type_counts.items():
                type_name = type_names.get(t, t)
                type_desc_parts.append(f"{count}个{type_name}")
            type_desc = '、'.join(type_desc_parts)

            if end_date == start_date:
                event_name = f"{start_date} 健康记录"
            else:
                event_name = f"{start_date} 至 {end_date} 健康事件"

            existing = cls.objects.filter(
                user=user,
                is_auto_generated=True,
                start_date=start_date,
                end_date=end_date if end_date != start_date else None
            ).first()

            if existing:
                event = existing
            else:
                event_type = 'other'
                if len(type_counts) == 1:
                    if 'healthcheckup' in type_counts:
                        event_type = 'checkup'
                    elif 'medicationgroup' in type_counts or 'medication' in type_counts:
                        event_type = 'medication_course'
                    elif 'symptomentry' in type_counts:
                        event_type = 'illness'

                event = cls.objects.create(
                    user=user,
                    name=event_name,
                    start_date=start_date,
                    end_date=end_date if end_date != start_date else None,
                    event_type=event_type,
                    is_auto_generated=True,
                    description=f"自动聚类: {type_desc}"
                )
                events_created += 1

            for record in cluster:
                try:
                    EventItem.objects.get_or_create(
                        event=event,
                        content_type=ContentType.objects.get_for_model(record['obj']),
                        object_id=record['obj'].id,
                        defaults={'added_by': 'auto'}
                    )
                except Exception as e:
                    print(f"Error adding record to event: {e}")

        return events_created

    @classmethod
    def _cluster_by_time(cls, queryset, date_field, threshold_days):
        """根据时间聚类记录"""
        if not queryset.exists():
            return []

        clusters = []
        current_cluster = []

        for obj in queryset:
            obj_date = getattr(obj, date_field)

            if not current_cluster:
                current_cluster.append(obj)
            else:
                # 检查与聚类中第一条记录的时间差
                first_date = getattr(current_cluster[0], date_field)
                days_diff = abs((obj_date - first_date).days)

                if days_diff <= threshold_days:
                    current_cluster.append(obj)
                else:
                    # 开始新聚类
                    clusters.append(current_cluster)
                    current_cluster = [obj]

        if current_cluster:
            clusters.append(current_cluster)

        return clusters

    @classmethod
    def _cluster_medications(cls, medications, threshold_days):
        """聚类药单（基于时间重叠或相近性）"""
        if not medications:
            return []

        clusters = []
        used_indices = set()

        for i, med1 in enumerate(medications):
            if i in used_indices:
                continue

            cluster = [med1]
            used_indices.add(i)

            for j, med2 in enumerate(medications):
                if j <= i or j in used_indices:
                    continue

                # 检查时间是否重叠或相近
                if cls._medications_overlap_or_near(med1, med2, threshold_days):
                    cluster.append(med2)
                    used_indices.add(j)
                    # 更新基准时间范围
                    med1 = cls._merge_medication_time_range(cluster)

            clusters.append(cluster)

        return clusters

    @classmethod
    def _medications_overlap_or_near(cls, med1, med2, threshold_days):
        """检查两个药单是否时间重叠或相近"""
        # 检查重叠
        if not (med1.end_date < med2.start_date or med2.end_date < med1.start_date):
            return True

        # 检查相近性
        gap = min(abs((med1.end_date - med2.start_date).days),
                  abs((med2.end_date - med1.start_date).days))
        return gap <= threshold_days

    @classmethod
    def _merge_medication_time_range(cls, medications):
        """合并药单时间范围"""
        if not medications:
            return None

        start = min(m.start_date for m in medications)
        end = max(m.end_date for m in medications)

        # 返回一个虚拟对象用于比较
        from collections import namedtuple
        MedicationRange = namedtuple('MedicationRange', ['start_date', 'end_date'])
        return MedicationRange(start_date=start, end_date=end)

    @classmethod
    def _detect_illness_events(cls, user, threshold_days):
        """检测疾病事件（通过异常指标和药单关联）"""
        # 获取有异常指标的体检
        checkups_with_abnormal = HealthCheckup.objects.filter(
            user=user,
            indicators__status__in=['abnormal', 'attention']
        ).distinct()

        for checkup in checkups_with_abnormal:
            # 查找附近时间的药单
            nearby_meds = Medication.objects.filter(
                user=user,
                start_date__gte=checkup.checkup_date - timedelta(days=threshold_days),
                start_date__lte=checkup.checkup_date + timedelta(days=threshold_days)
            )

            if nearby_meds.exists():
                # 创建疾病事件
                event_name = f"{checkup.checkup_date} 健康关注"

                existing = cls.objects.filter(
                    user=user,
                    event_type='illness',
                    is_auto_generated=True,
                    start_date=checkup.checkup_date
                ).first()

                if existing:
                    event = existing
                else:
                    event = cls.objects.create(
                        user=user,
                        name=event_name,
                        start_date=checkup.checkup_date,
                        end_date=checkup.checkup_date + timedelta(days=30),
                        event_type='illness',
                        is_auto_generated=True,
                        description=f"检测到异常指标和用药，自动创建关注事件"
                    )

                # 添加体检报告
                EventItem.objects.get_or_create(
                    event=event,
                    content_type=ContentType.objects.get_for_model(checkup),
                    object_id=checkup.id,
                    defaults={'added_by': 'auto'}
                )

                # 添加药单
                for med in nearby_meds:
                    EventItem.objects.get_or_create(
                        event=event,
                        content_type=ContentType.objects.get_for_model(med),
                        object_id=med.id,
                        defaults={'added_by': 'auto'}
                    )


class EventItem(models.Model):
    """事件项目关联模型 - 将健康记录关联到事件"""
    ADDED_BY_CHOICES = [
        ('auto', '自动添加'),
        ('manual', '手动添加'),
    ]

    event = models.ForeignKey(HealthEvent, on_delete=models.CASCADE, verbose_name='事件', related_name='event_items')
    # Generic foreign key to link to any health record model
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, verbose_name='内容类型')
    object_id = models.PositiveIntegerField(verbose_name='对象ID')
    content_object = GenericForeignKey('content_type', 'object_id')

    notes = models.TextField(blank=True, null=True, verbose_name='备注')
    added_by = models.CharField(max_length=10, choices=ADDED_BY_CHOICES, default='manual', verbose_name='添加方式')
    added_at = models.DateTimeField(auto_now_add=True, verbose_name='添加时间')

    class Meta:
        verbose_name = '事件项目'
        verbose_name_plural = '事件项目'
        ordering = ['event', '-added_at']
        indexes = [
            models.Index(fields=['event', 'content_type', 'object_id']),
            models.Index(fields=['added_by']),
        ]
        # 确保同一记录不会重复添加到同一事件
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'content_type', 'object_id'],
                name='unique_event_item'
            )
        ]

    def __str__(self):
        return f"{self.event.name} - {self.content_type.model}"

    @property
    def item_summary(self):
        """获取关联记录的摘要信息"""
        obj = self.content_object
        if not obj:
            return "已删除的记录"

        model_name = self.content_type.model

        if model_name == 'healthcheckup':
            return f"体检报告: {obj.checkup_date} - {obj.hospital}"
        elif model_name == 'medication':
            return f"药单: {obj.medicine_name} ({obj.start_date} 至 {obj.end_date})"
        elif model_name == 'healthindicator':
            return f"指标: {obj.indicator_name} = {obj.value} {obj.unit or ''}"
        elif model_name == 'medicationrecord':
            return f"服药记录: {obj.medication.medicine_name} - {obj.record_date}"
        elif model_name == 'medicationgroup':
            med_names = ', '.join([m.medicine_name for m in obj.medications.all()[:3]])
            if obj.medication_count > 3:
                med_names += f' 等{obj.medication_count}个'
            return f"药单组: {obj.name} ({med_names})"
        elif model_name == 'symptomentry':
            return f"症状日志: {obj.entry_date} - {obj.symptom}"
        elif model_name == 'vitalentry':
            return f"体征记录: {obj.entry_date} - {obj.get_vital_type_display()} {obj.value}{obj.unit or ''}"
        else:
            return f"{model_name}: {str(obj)}"


class EventTemplate(models.Model):
    """事件模板 - 预设的常见健康事件配置"""
    EVENT_TYPE_CHOICES = [
        ('illness', '疾病事件'),
        ('checkup', '体检事件'),
        ('chronic_management', '慢性病管理'),
        ('emergency', '急诊事件'),
        ('wellness', '健康管理'),
        ('medication_course', '用药疗程'),
        ('other', '其他'),
    ]

    name = models.CharField(max_length=200, verbose_name='模板名称')
    description = models.TextField(blank=True, null=True, verbose_name='模板描述')
    event_type = models.CharField(max_length=30, choices=EVENT_TYPE_CHOICES, verbose_name='事件类型')
    suggested_duration_days = models.PositiveIntegerField(blank=True, null=True, verbose_name='建议持续天数')
    default_name_template = models.CharField(max_length=200, blank=True, verbose_name='默认名称模板')
    is_system_template = models.BooleanField(default=False, verbose_name='系统模板')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '事件模板'
        verbose_name_plural = '事件模板'
        ordering = ['is_system_template', 'name']

    def __str__(self):
        return f"{self.name} ({self.get_event_type_display()})"

    def apply_template(self, user, start_date=None, custom_name=None):
        """
        应用模板创建新事件

        Args:
            user: 用户对象
            start_date: 开始日期（默认今天）
            custom_name: 自定义事件名称（可选）

        Returns:
            创建的 HealthEvent 对象
        """
        from datetime import timedelta

        if not start_date:
            start_date = date.today()

        end_date = None
        if self.suggested_duration_days:
            end_date = start_date + timedelta(days=self.suggested_duration_days - 1)

        event_name = custom_name or self.default_name_template or self.name
        # 可以在名称模板中使用 {date} 占位符
        event_name = event_name.format(date=start_date.strftime('%Y-%m-%d'))

        event = HealthEvent.objects.create(
            user=user,
            name=event_name,
            event_type=self.event_type,
            start_date=start_date,
            end_date=end_date,
            description=self.description,
            is_auto_generated=False
        )

        return event
