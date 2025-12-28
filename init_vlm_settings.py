import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_report.settings')
django.setup()
from medical_records.models import SystemSettings

# 配置vlm-transformer模式设置
settings_config = [
    {
        'key': 'mineru_api_url',
        'name': 'MinerU API地址',
        'value': 'http://localhost:8000',
        'description': 'MinerU API服务地址，用于OCR识别和多模态处理'
    },
    {
        'key': 'vl_model_api_url',
        'name': '多模态模型API地址',
        'value': 'http://localhost:8000',
        'description': '多模态大模型API服务地址，用于vlm-transformer模式'
    },
    {
        'key': 'vl_model_name',
        'name': '多模态模型名称',
        'value': 'vlm-transformers',
        'description': '使用的多模态大模型名称，vlm-transformer模式专用'
    },
    {
        'key': 'ai_model_timeout',
        'name': 'AI模型统一超时时间',
        'value': '300',
        'description': '所有AI模型（LLM、OCR、多模态等）API请求的统一超时时间（秒）'
    },
    {
        'key': 'vl_model_max_tokens',
        'name': '多模态模型最大Token数',
        'value': '4096',
        'description': '多模态模型生成的最大Token数量'
    },
    {
        'key': 'default_workflow',
        'name': '默认处理工作流',
        'value': 'multimodal',
        'description': '默认的文档处理工作流：ocr_llm（传统OCR+LLM）或multimodal（多模态大模型）'
    }
]

print("正在配置vlm-transformer模式设置...")

for setting_data in settings_config:
    setting, created = SystemSettings.objects.update_or_create(
        key=setting_data['key'],
        defaults={
            'name': setting_data['name'],
            'value': setting_data['value'],
            'description': setting_data['description'],
            'is_active': True
        }
    )
    
    if created:
        print(f"✅ 创建新设置: {setting.name}")
    else:
        print(f"✅ 更新设置: {setting.name} -> {setting.value}")

print("\n🎉 vlm-transformer模式配置完成！")
print("\n配置摘要:")
print("- MinerU API地址: http://localhost:8000")
print("- 多模态模型: qwen-vl-transformer")
print("- 默认工作流: multimodal (多模态大模型)")
print("- AI模型统一超时: 300秒")
print("- 最大Token: 4096")

print("\n使用说明:")
print("1. 确保mineru-api在8000端口运行")
print("2. 上传体检报告时将自动使用vlm-transformer模式")
print("3. 系统会直接分析图片，无需先进行OCR识别")
print("4. 可在系统设置中切换回ocr_llm模式")
