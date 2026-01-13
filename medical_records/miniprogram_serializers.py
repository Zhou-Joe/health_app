from rest_framework import serializers
from .models import HealthCheckup, HealthIndicator, HealthAdvice, SystemSettings, DocumentProcessing, UserProfile
from django.contrib.auth.models import User

class UserSerializer(serializers.ModelSerializer):
    """用户序列化器，包含UserProfile信息"""
    birth_date = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    age = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'date_joined', 'birth_date', 'gender', 'age']

    def get_birth_date(self, obj):
        """获取出生日期"""
        try:
            profile = obj.userprofile
            return profile.birth_date.isoformat() if profile.birth_date else None
        except UserProfile.DoesNotExist:
            return None

    def get_gender(self, obj):
        """获取性别"""
        try:
            profile = obj.userprofile
            return profile.gender if profile.gender else None
        except UserProfile.DoesNotExist:
            return None

    def get_age(self, obj):
        """获取年龄"""
        try:
            profile = obj.userprofile
            return profile.age if profile.birth_date else None
        except UserProfile.DoesNotExist:
            return None


class HealthIndicatorSerializer(serializers.ModelSerializer):
    """健康指标序列化器"""
    checkup_date = serializers.SerializerMethodField()
    value_display = serializers.SerializerMethodField()

    class Meta:
        model = HealthIndicator
        fields = [
            'id', 'indicator_name', 'indicator_type', 'value',
            'unit', 'reference_range', 'status', 'checkup',
            'checkup_date', 'value_display'
        ]

    def get_checkup_date(self, obj):
        """获取体检日期"""
        return obj.checkup.checkup_date if obj.checkup else None

    def get_value_display(self, obj):
        """获取值显示"""
        return f"{obj.value} {obj.unit}" if obj.unit else str(obj.value)

class HealthCheckupSerializer(serializers.ModelSerializer):
    """体检记录序列化器"""
    indicators = HealthIndicatorSerializer(many=True, read_only=True)

    class Meta:
        model = HealthCheckup
        fields = [
            'id', 'user', 'checkup_date', 'hospital', 'report_file',
            'notes', 'created_at', 'indicators'
        ]
        read_only_fields = ['user']

class HealthAdviceSerializer(serializers.ModelSerializer):
    """健康建议序列化器"""
    class Meta:
        model = HealthAdvice
        fields = [
            'id', 'user', 'checkup', 'advice_type', 'advice_content',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user']

class DocumentProcessingSerializer(serializers.ModelSerializer):
    """文档处理状态序列化器"""

    class Meta:
        model = DocumentProcessing
        fields = [
            'id', 'status', 'progress', 'error_message', 'workflow_type',
            'ocr_result', 'ai_result', 'vl_model_result',
            'created_at', 'updated_at'
        ]

class MiniProgramCheckupListSerializer(serializers.ModelSerializer):
    """小程序体检记录列表序列化器"""
    indicators_count = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = HealthCheckup
        fields = [
            'id', 'checkup_date', 'hospital', 'report_file',
            'created_at', 'indicators_count', 'status', 'notes'
        ]
        read_only_fields = ['user']

    def get_indicators_count(self, obj):
        return obj.indicators.count()

    def get_status(self, obj):
        """从DocumentProcessing获取处理状态"""
        try:
            processing = obj.documentprocessing
            return processing.status
        except DocumentProcessing.DoesNotExist:
            # 如果没有处理记录，默认为completed
            return 'completed'

class SystemSettingsSerializer(serializers.ModelSerializer):
    """系统设置序列化器"""

    class Meta:
        model = SystemSettings
        fields = ['key', 'value']