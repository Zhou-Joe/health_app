from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import (
    HealthCheckup,
    HealthIndicator,
    HealthAdvice,
    SystemSettings,
    UserProfile,
    SymptomEntry,
    VitalEntry,
    CarePlan,
    CareGoal,
    CareAction,
    CaregiverAccess,
    Medication,
)


class CustomUserCreationForm(forms.ModelForm):
    """用户注册表单 - 包含用户名、密码和个人信息"""

    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '请输入密码',
            'autocomplete': 'new-password'
        })
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': '请确认密码',
            'autocomplete': 'new-password'
        })
    )

    # 添加个人信息字段
    birth_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label='出生日期'
    )

    gender = forms.ChoiceField(
        choices=[
            ('male', '男'),
            ('female', '女'),
        ],
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        }),
        label='性别'
    )

    class Meta:
        model = User
        fields = ('username',)
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '请输入用户名',
                'autocomplete': 'username'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自定义字段标签
        self.fields['username'].label = '用户名'
        self.fields['password1'].label = '密码'
        self.fields['password2'].label = '确认密码'

        # 简化帮助文本
        self.fields['username'].help_text = '任意长度'

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username.strip():
            raise ValidationError('用户名不能为空')
        if User.objects.filter(username=username).exists():
            raise ValidationError('该用户名已被注册，请使用其他用户名')
        return username

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError('两次输入的密码不一致')
        return password2

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get('birth_date')
        if birth_date:
            from datetime import date
            if birth_date > date.today():
                raise ValidationError('出生日期不能晚于今天')
            # 检查年龄是否合理（不超过120岁）
            age = date.today().year - birth_date.year - ((date.today().month, date.today().day) < (birth_date.month, birth_date.day))
            if age > 120:
                raise ValidationError('请输入有效的出生日期')
        return birth_date

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
            # 保存用户个人信息
            birth_date = self.cleaned_data.get('birth_date')
            gender = self.cleaned_data.get('gender')
            if birth_date or gender:
                profile = UserProfile.objects.get(user=user)
                if birth_date:
                    profile.birth_date = birth_date
                if gender:
                    profile.gender = gender
                profile.save()
        return user


class HealthCheckupForm(forms.ModelForm):
    """体检报告表单"""

    class Meta:
        model = HealthCheckup
        fields = ['checkup_date', 'hospital', 'report_file', 'notes']
        widgets = {
            'checkup_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hospital': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '请输入体检机构名称'}),
            'report_file': forms.FileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': '请输入备注信息'}),
        }


class HealthIndicatorForm(forms.ModelForm):
    """健康指标表单"""

    class Meta:
        model = HealthIndicator
        fields = ['indicator_type', 'indicator_name', 'value', 'unit', 'reference_range', 'status']
        widgets = {
            'indicator_type': forms.Select(attrs={'class': 'form-control'}),
            'indicator_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '请输入指标名称'}),
            'value': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '请输入检测值'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '请输入单位'}),
            'reference_range': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '请输入参考范围'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }


class ManualIndicatorForm(forms.ModelForm):
    """手动输入健康指标表单"""

    class Meta:
        model = HealthIndicator
        fields = ['indicator_type', 'indicator_name', 'value', 'unit', 'reference_range', 'status']
        widgets = {
            'indicator_type': forms.Select(attrs={'class': 'form-control'}),
            'indicator_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：血红蛋白浓度'}),
            'value': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：120'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：g/L'}),
            'reference_range': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：110-150'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['indicator_type'].label = '指标分类'
        self.fields['indicator_name'].label = '指标名称 *'
        self.fields['value'].label = '检测值 *'
        self.fields['unit'].label = '单位'
        self.fields['reference_range'].label = '参考范围'
        self.fields['status'].label = '状态'

        # 设置字段帮助文本
        self.fields['indicator_name'].help_text = '请输入准确的指标名称，例如：血红蛋白浓度、空腹血糖等'
        self.fields['value'].help_text = '请输入检测到的数值'
        self.fields['unit'].help_text = '可选，例如：mmol/L、g/L、U/L等'
        self.fields['reference_range'].help_text = '可选，正常值的参考范围'
        self.fields['status'].help_text = '根据检测值判断是否正常'


class HealthAdviceForm(forms.ModelForm):
    """健康建议表单"""

    selected_reports = forms.ModelMultipleChoiceField(
        queryset=HealthCheckup.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label='选择相关体检报告',
        help_text='选择与您问题相关的体检报告，AI医生将基于这些报告给出更精准的建议'
    )

    class Meta:
        model = HealthAdvice
        fields = ['question']
        widgets = {
            'question': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': '请描述您的健康问题或需要咨询的内容...'
            }),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 为用户过滤其自己的体检报告
        self.fields['selected_reports'].queryset = HealthCheckup.objects.filter(
            user=user
        ).order_by('-checkup_date')


HealthIndicatorFormSet = forms.inlineformset_factory(
    HealthCheckup,
    HealthIndicator,
    form=HealthIndicatorForm,
    extra=1,
    can_delete=True
)


class SymptomEntryForm(forms.ModelForm):
    """症状日志表单"""

    class Meta:
        model = SymptomEntry
        fields = ['entry_date', 'symptom', 'severity', 'notes', 'related_checkup', 'related_medication']
        widgets = {
            'entry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'symptom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：头痛、咳嗽、乏力'}),
            'severity': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': '可选备注'}),
            'related_checkup': forms.Select(attrs={'class': 'form-control'}),
            'related_medication': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['related_checkup'].queryset = HealthCheckup.objects.filter(user=user).order_by('-checkup_date')
        self.fields['related_medication'].queryset = Medication.objects.filter(user=user, is_active=True).order_by('-start_date')
        self.fields['related_checkup'].required = False
        self.fields['related_medication'].required = False


class VitalEntryForm(forms.ModelForm):
    """体征日志表单"""

    class Meta:
        model = VitalEntry
        fields = ['entry_date', 'vital_type', 'value', 'unit', 'notes', 'related_checkup', 'related_medication']
        widgets = {
            'entry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'vital_type': forms.Select(attrs={'class': 'form-control'}),
            'value': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：120/80 或 36.6'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '单位'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': '可选备注'}),
            'related_checkup': forms.Select(attrs={'class': 'form-control'}),
            'related_medication': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['related_checkup'].queryset = HealthCheckup.objects.filter(user=user).order_by('-checkup_date')
        self.fields['related_medication'].queryset = Medication.objects.filter(user=user, is_active=True).order_by('-start_date')
        self.fields['related_checkup'].required = False
        self.fields['related_medication'].required = False


class CarePlanForm(forms.ModelForm):
    """健康管理计划表单"""

    class Meta:
        model = CarePlan
        fields = ['title', 'description', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：降压管理计划'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': '计划说明'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class CareGoalForm(forms.ModelForm):
    """健康目标表单"""

    class Meta:
        model = CareGoal
        fields = ['title', 'target_value', 'unit', 'due_date', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：将血压控制在120/80'}),
            'target_value': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '目标值'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '单位'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }


class CareActionForm(forms.ModelForm):
    """健康行动表单"""

    class Meta:
        model = CareAction
        fields = ['title', 'frequency', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：每天散步30分钟'}),
            'frequency': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '频率，如每日/每周'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }


class CaregiverAccessForm(forms.Form):
    """照护者授权表单"""
    caregiver_username = forms.CharField(
        label='照护者用户名',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '请输入对方用户名'})
    )
    relationship = forms.CharField(
        label='关系',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '例如：家属/朋友/医生'})
    )
    can_view_records = forms.BooleanField(label='体检报告', required=False, initial=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    can_view_medications = forms.BooleanField(label='药单', required=False, initial=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    can_view_events = forms.BooleanField(label='事件', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    can_view_diary = forms.BooleanField(label='日志', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    can_manage_medications = forms.BooleanField(label='管理药单', required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    def clean_caregiver_username(self):
        username = self.cleaned_data.get('caregiver_username', '').strip()
        if not username:
            raise ValidationError('请输入照护者用户名')
        if not User.objects.filter(username=username).exists():
            raise ValidationError('用户不存在')
        return username


class SystemSettingsForm(forms.Form):
    """系统设置表单"""

    mineru_api_url = forms.URLField(
        label='MinerU API地址',
        max_length=200,
        help_text='MinerU OCR服务的API地址，例如：http://localhost:8000 或 http://your-mineru-domain.com/api'
    )

    document_max_tokens = forms.IntegerField(
        label='文档处理最大输出Token数',
        min_value=1000,
        max_value=32000,
        initial=8000,
        help_text='OCR+LLM提取数据时的最大输出Token数，默认8000。建议6000-16000，根据报告复杂度调整。Gemini建议至少8000'
    )

    llm_api_url = forms.URLField(
        label='LLM API地址',
        max_length=200,
        initial='https://api.siliconflow.cn/v1/chat/completions',
        help_text='LLM服务的完整API地址，例如：http://172.25.48.1:1234/v1/chat/completions 或 http://api.openai.com/v1/chat/completions'
    )

    llm_api_key = forms.CharField(
        label='LLM API密钥',
        max_length=200,
        required=False,
        initial='sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa',
        help_text='LLM服务的API密钥（如果不需要则留空）'
    )

    llm_model_name = forms.CharField(
        label='LLM模型名称',
        max_length=100,
        initial='deepseek-ai/DeepSeek-V3.2',
        help_text='使用的LLM模型名称，例如：qwen3-4b-instruct'
    )

    ai_model_timeout = forms.IntegerField(
        label='AI模型统一超时时间（秒）',
        min_value=30,
        max_value=3600,
        initial=300,
        help_text='所有AI模型（LLM、OCR、AI医生、Gemini、多模态）API请求的统一超时时间，默认300秒'
    )

    llm_max_tokens = forms.IntegerField(
        label='LLM最大输出Token数',
        min_value=1000,
        max_value=128000,
        initial=16000,
        help_text='数据整合时LLM的最大输出Token数，默认16000。如果数据量大或JSON被截断，可以增加此值'
    )

    llm_provider = forms.ChoiceField(
        label='数据整合LLM提供商',
        choices=[
            ('openai', 'OpenAI兼容格式（如OpenAI、SiliconFlow、DeepSeek等）'),
            ('gemini', 'Google Gemini'),
        ],
        initial='openai',
        help_text='选择数据整合LLM使用的API格式类型'
    )

    llm_enable_thinking = forms.BooleanField(
        label='传入思考模式参数',
        required=False,
        initial=False,
        help_text='是否向模型传入 enable_thinking 参数。适用于支持混合思考的模型（如 Qwen3.5、Qwen3、Qwen3-Omni-Flash、Qwen3-VL）。'
    )

    llm_thinking_mode = forms.ChoiceField(
        label='思考模式',
        choices=[
            ('true', '开启 - 启用深度思考'),
            ('false', '关闭 - 直接回复'),
        ],
        initial='true',
        required=False,
        help_text='选择思考模式的具体设置。仅在"传入思考模式参数"勾选时生效。'
    )

    ai_doctor_api_url = forms.URLField(
        label='AI医生API地址',
        max_length=200,
        required=False,
        initial='https://api.siliconflow.cn/v1/chat/completions',
        help_text='AI医生服务的完整API地址，例如：http://api.openai.com/v1/chat/completions 或 http://localhost:8001/v1/chat/completions'
    )

    ai_doctor_api_key = forms.CharField(
        label='AI医生API密钥',
        max_length=200,
        required=False,
        initial='sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa',
        help_text='AI医生服务的API密钥（如果不需要则留空）'
    )

    ai_doctor_model_name = forms.CharField(
        label='AI医生模型名称',
        max_length=100,
        required=False,
        initial='deepseek-ai/DeepSeek-V3.2',
        help_text='AI医生使用的模型名称，例如：gpt-4、claude-3'
    )

    ai_doctor_max_tokens = forms.IntegerField(
        label='AI医生最大输出Token数',
        min_value=500,
        max_value=32000,
        initial=4000,
        help_text='AI医生对话时的最大输出Token数，默认4000。建议2000-8000，可以根据需要调整'
    )

    ai_doctor_provider = forms.ChoiceField(
        label='AI医生服务提供商',
        choices=[
            ('openai', 'OpenAI兼容格式（如OpenAI、SiliconFlow、DeepSeek等）'),
            ('gemini', 'Google Gemini'),
        ],
        initial='openai',
        help_text='选择AI医生使用的API格式类型'
    )

    ai_doctor_enable_thinking = forms.BooleanField(
        label='传入思考模式参数',
        required=False,
        initial=False,
        help_text='是否向模型传入 enable_thinking 参数。适用于支持混合思考的模型（如 Qwen3.5、Qwen3、Qwen3-Omni-Flash、Qwen3-VL）。'
    )

    ai_doctor_thinking_mode = forms.ChoiceField(
        label='思考模式',
        choices=[
            ('true', '开启 - 启用深度思考'),
            ('false', '关闭 - 直接回复'),
        ],
        initial='true',
        required=False,
        help_text='选择思考模式的具体设置。仅在"传入思考模式参数"勾选时生效。'
    )

    ai_doctor_enable_thinking = forms.BooleanField(
        label='启用深度思考模式',
        required=False,
        initial=True,
        help_text='仅适用于阿里云 Qwen 系列模型（Qwen3.5、Qwen3、Qwen3-Omni-Flash、Qwen3-VL）。开启后模型会在回复前进行思考，思考内容可通过 reasoning_content 字段查看。'
    )

    # Google Gemini设置
    gemini_api_key = forms.CharField(
        label='Gemini API密钥',
        max_length=200,
        required=False,
        help_text='Google Gemini API密钥，从 https://makersuite.google.com/app/apikey 获取'
    )

    gemini_model_name = forms.CharField(
        label='Gemini模型名称',
        max_length=100,
        initial='gemini-3.0-flash',
        required=False,
        help_text='使用的Gemini模型名称，例如：gemini-3.0-flash、gemini-2.0-flash-exp、gemini-1.5-pro'
    )

    # 多模态模型配置
    vl_model_provider = forms.ChoiceField(
        label='多模态模型提供商',
        choices=[
            ('openai', 'OpenAI兼容格式（如OpenAI、SiliconFlow等）'),
            ('gemini', 'Google Gemini'),
        ],
        initial='openai',
        required=False,
        help_text='选择多模态模型使用的API格式类型'
    )

    vl_model_api_url = forms.URLField(
        label='多模态模型API地址',
        max_length=200,
        required=False,
        initial='https://api.siliconflow.cn/v1/chat/completions',
        help_text='多模态大模型的完整API地址，例如：http://api.openai.com/v1/chat/completions 或 https://api.siliconflow.cn/v1/chat/completions'
    )

    vl_model_api_key = forms.CharField(
        label='多模态模型API密钥',
        max_length=200,
        required=False,
        initial='sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa',
        help_text='多模态大模型的API密钥'
    )

    vl_model_name = forms.CharField(
        label='多模态模型名称',
        max_length=100,
        initial='zai-org/GLM-4.6V',
        required=False,
        help_text='使用的多模态模型名称，例如：gpt-4-vision-preview 或 gemini-2.0-flash-exp'
    )

    vl_model_max_tokens = forms.IntegerField(
        label='多模态模型最大输出令牌数',
        min_value=1000,
        max_value=128000,
        initial=8000,
        required=False,
        help_text='多模态模型最大输出token数量，建议8000-20000，根据模型支持的最大上下文设置'
    )

    vl_enable_thinking = forms.BooleanField(
        label='传入思考模式参数',
        required=False,
        initial=False,
        help_text='是否向模型传入 enable_thinking 参数。适用于支持混合思考的模型（如 Qwen3.5、Qwen3、Qwen3-Omni-Flash、Qwen3-VL）。'
    )

    vl_thinking_mode = forms.ChoiceField(
        label='思考模式',
        choices=[
            ('true', '开启 - 启用深度思考'),
            ('false', '关闭 - 直接回复'),
        ],
        initial='true',
        required=False,
        help_text='选择思考模式的具体设置。仅在"传入思考模式参数"勾选时生效。'
    )

    # 系统配置
    is_mac_system = forms.BooleanField(
        label='Mac系统',
        required=False,
        initial=False,
        help_text='如果MinerU服务运行在Mac系统上，请勾选此项。VLM模式将使用vlm-mlx-engine后端'
    )

    pdf_ocr_workflow = forms.ChoiceField(
        label='PDF文件OCR工作流',
        choices=[
            ('ocr_llm', 'MinerU Pipeline 模式 (OCR + LLM)'),
            ('vlm_transformers', 'MinerU VLM 模式 (OCR + LLM)'),
        ],
        initial='ocr_llm',
        help_text='PDF文件自动使用的OCR工作流'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 从数据库加载现有设置
        self.fields['mineru_api_url'].initial = SystemSettings.get_setting('mineru_api_url', 'http://localhost:8000')
        self.fields['document_max_tokens'].initial = int(SystemSettings.get_setting('document_max_tokens', '8000'))
        self.fields['llm_api_url'].initial = SystemSettings.get_setting('llm_api_url', 'https://api.siliconflow.cn/v1/chat/completions')
        self.fields['llm_api_key'].initial = SystemSettings.get_setting('llm_api_key', 'sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa')
        self.fields['llm_model_name'].initial = SystemSettings.get_setting('llm_model_name', 'deepseek-ai/DeepSeek-V3.2')
        # 加载统一的AI模型超时配置
        self.fields['ai_model_timeout'].initial = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        self.fields['llm_max_tokens'].initial = int(SystemSettings.get_setting('llm_max_tokens', '16000'))
        self.fields['llm_provider'].initial = SystemSettings.get_setting('llm_provider', 'openai')
        self.fields['llm_enable_thinking'].initial = SystemSettings.get_setting('llm_enable_thinking', 'false').lower() == 'true'
        self.fields['llm_thinking_mode'].initial = SystemSettings.get_setting('llm_thinking_mode', 'true')
        self.fields['ai_doctor_api_url'].initial = SystemSettings.get_setting('ai_doctor_api_url', 'https://api.siliconflow.cn/v1/chat/completions')
        self.fields['ai_doctor_api_key'].initial = SystemSettings.get_setting('ai_doctor_api_key', 'sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa')
        self.fields['ai_doctor_model_name'].initial = SystemSettings.get_setting('ai_doctor_model_name', 'deepseek-ai/DeepSeek-V3.2')
        self.fields['ai_doctor_max_tokens'].initial = int(SystemSettings.get_setting('ai_doctor_max_tokens', '4000'))
        self.fields['ai_doctor_provider'].initial = SystemSettings.get_setting('ai_doctor_provider', 'openai')
        self.fields['ai_doctor_enable_thinking'].initial = SystemSettings.get_setting('ai_doctor_enable_thinking', 'false').lower() == 'true'
        self.fields['ai_doctor_thinking_mode'].initial = SystemSettings.get_setting('ai_doctor_thinking_mode', 'true')

        # 加载Gemini设置
        self.fields['gemini_api_key'].initial = SystemSettings.get_setting('gemini_api_key', '')
        self.fields['gemini_model_name'].initial = SystemSettings.get_setting('gemini_model_name', 'gemini-3.0-flash')

        # 加载多模态模型设置
        self.fields['vl_model_provider'].initial = SystemSettings.get_setting('vl_model_provider', 'openai')
        self.fields['vl_model_api_url'].initial = SystemSettings.get_setting('vl_model_api_url', 'https://api.siliconflow.cn/v1/chat/completions')
        self.fields['vl_model_api_key'].initial = SystemSettings.get_setting('vl_model_api_key', 'sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa')
        self.fields['vl_model_name'].initial = SystemSettings.get_setting('vl_model_name', 'zai-org/GLM-4.6V')
        self.fields['vl_model_max_tokens'].initial = int(SystemSettings.get_setting('vl_model_max_tokens', '4000'))
        self.fields['vl_enable_thinking'].initial = SystemSettings.get_setting('vl_enable_thinking', 'false').lower() == 'true'
        self.fields['vl_thinking_mode'].initial = SystemSettings.get_setting('vl_thinking_mode', 'true')

        # 加载系统配置
        self.fields['is_mac_system'].initial = SystemSettings.get_setting('is_mac_system', 'false').lower() == 'true'

        # 加载工作流设置
        self.fields['pdf_ocr_workflow'].initial = SystemSettings.get_setting('pdf_ocr_workflow', 'ocr_llm')

    def save(self):
        """保存设置到数据库"""
        SystemSettings.set_setting('mineru_api_url', self.cleaned_data['mineru_api_url'], 'MinerU API地址')
        SystemSettings.set_setting('document_max_tokens', str(self.cleaned_data['document_max_tokens']), '文档处理最大输出Token数')
        SystemSettings.set_setting('llm_api_url', self.cleaned_data['llm_api_url'], 'LLM API地址')
        SystemSettings.set_setting('llm_api_key', self.cleaned_data['llm_api_key'], 'LLM API密钥')
        SystemSettings.set_setting('llm_model_name', self.cleaned_data['llm_model_name'], 'LLM模型名称')
        # 保存统一的AI模型超时配置
        SystemSettings.set_setting('ai_model_timeout', str(self.cleaned_data['ai_model_timeout']), 'AI模型统一超时时间')
        SystemSettings.set_setting('llm_max_tokens', str(self.cleaned_data['llm_max_tokens']), 'LLM最大输出Token数')
        SystemSettings.set_setting('llm_provider', self.cleaned_data['llm_provider'], '数据整合LLM提供商')
        SystemSettings.set_setting('llm_enable_thinking', 'true' if self.cleaned_data['llm_enable_thinking'] else 'false', '数据整合LLM传入思考模式参数')
        SystemSettings.set_setting('llm_thinking_mode', self.cleaned_data['llm_thinking_mode'], '数据整合LLM思考模式')
        SystemSettings.set_setting('ai_doctor_api_url', self.cleaned_data['ai_doctor_api_url'], 'AI医生API地址')
        SystemSettings.set_setting('ai_doctor_api_key', self.cleaned_data['ai_doctor_api_key'], 'AI医生API密钥')
        SystemSettings.set_setting('ai_doctor_model_name', self.cleaned_data['ai_doctor_model_name'], 'AI医生模型名称')
        SystemSettings.set_setting('ai_doctor_max_tokens', str(self.cleaned_data['ai_doctor_max_tokens']), 'AI医生最大输出Token数')
        SystemSettings.set_setting('ai_doctor_provider', self.cleaned_data['ai_doctor_provider'], 'AI医生服务提供商')
        SystemSettings.set_setting('ai_doctor_enable_thinking', 'true' if self.cleaned_data['ai_doctor_enable_thinking'] else 'false', 'AI医生启用思考模式')
        SystemSettings.set_setting('ai_doctor_thinking_mode', self.cleaned_data['ai_doctor_thinking_mode'], 'AI医生思考模式')

        # 保存Gemini设置
        SystemSettings.set_setting('gemini_api_key', self.cleaned_data['gemini_api_key'], 'Gemini API密钥')
        SystemSettings.set_setting('gemini_model_name', self.cleaned_data['gemini_model_name'], 'Gemini模型名称')

        # 保存多模态模型设置
        SystemSettings.set_setting('vl_model_provider', self.cleaned_data['vl_model_provider'], '多模态模型提供商')
        SystemSettings.set_setting('vl_model_api_url', self.cleaned_data['vl_model_api_url'], '多模态模型API地址')
        SystemSettings.set_setting('vl_model_api_key', self.cleaned_data['vl_model_api_key'], '多模态模型API密钥')
        SystemSettings.set_setting('vl_model_name', self.cleaned_data['vl_model_name'], '多模态模型名称')
        SystemSettings.set_setting('vl_model_max_tokens', str(self.cleaned_data['vl_model_max_tokens']), '多模态模型最大输出令牌数')
        SystemSettings.set_setting('vl_enable_thinking', 'true' if self.cleaned_data['vl_enable_thinking'] else 'false', '多模态模型传入思考模式参数')
        SystemSettings.set_setting('vl_thinking_mode', self.cleaned_data['vl_thinking_mode'], '多模态模型思考模式')

        # 保存系统配置
        SystemSettings.set_setting('is_mac_system', 'true' if self.cleaned_data['is_mac_system'] else 'false', 'Mac系统')

        # 保存工作流设置
        SystemSettings.set_setting('pdf_ocr_workflow', self.cleaned_data['pdf_ocr_workflow'], 'PDF文件OCR工作流')


class UserProfileForm(forms.ModelForm):
    """用户信息表单"""

    class Meta:
        model = UserProfile
        fields = ['birth_date', 'gender']
        widgets = {
            'birth_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
            'gender': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'birth_date': '出生日期',
            'gender': '性别',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 确保日期字段正确显示值
        if self.instance and self.instance.pk:
            if self.instance.birth_date:
                self.fields['birth_date'].widget.attrs['value'] = self.instance.birth_date.strftime('%Y-%m-%d')

    def clean_birth_date(self):
        birth_date = self.cleaned_data.get('birth_date')
        if birth_date:
            from datetime import date
            if birth_date > date.today():
                raise ValidationError('出生日期不能晚于今天')
            # 检查年龄是否合理（不超过120岁）
            age = date.today().year - birth_date.year - ((date.today().month, date.today().day) < (birth_date.month, birth_date.day))
            if age > 120:
                raise ValidationError('请输入有效的出生日期')
        return birth_date
