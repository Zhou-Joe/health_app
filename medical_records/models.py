from django.db import models
from django.contrib.auth.models import User
from datetime import date
from django.db.models.signals import post_save
from django.dispatch import receiver


class HealthCheckup(models.Model):
    """体检报告模型"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
    checkup_date = models.DateField(verbose_name='体检日期')
    hospital = models.CharField(max_length=200, verbose_name='体检机构')
    report_file = models.FileField(upload_to='reports/%Y/%m/', blank=True, null=True, verbose_name='报告文件')
    notes = models.TextField(blank=True, null=True, verbose_name='备注')
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
    prompt_sent = models.TextField(blank=True, null=True, verbose_name='发送的Prompt')
    conversation_context = models.TextField(blank=True, null=True, verbose_name='对话上下文')
    selected_reports = models.TextField(blank=True, null=True, verbose_name='选中的报告ID列表（JSON格式）')
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
        """获取默认工作流"""
        workflow = cls.get_setting('default_workflow', 'ocr_llm')
        # 映射前端名称到后端名称
        workflow_mapping = {
            'multimodal': 'vl_model',
            'mineru_vlm': 'vlm_transformers',
            'mineru_pipeline': 'ocr_llm'
        }
        return workflow_mapping.get(workflow, workflow)

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


class Medication(models.Model):
    """药单模型"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='用户')
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
