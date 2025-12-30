import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_report.settings')
django.setup()

from medical_records.models import SystemSettings

config = SystemSettings.get_vl_model_config()
print('多模态模型配置:')
print(f'  提供商: {config["provider"]}')
print(f'  API URL: {config["api_url"]}')
print(f'  模型名称: {config["model_name"]}')
print(f'  API Key: {"已设置" if config["api_key"] else "未设置"}')
print(f'  超时时间: {config["timeout"]}秒')
print(f'  最大令牌数: {config["max_tokens"]}')
