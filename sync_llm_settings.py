#!/usr/bin/env python
"""
同步LLM设置脚本：将.env文件中的SiliconFlow配置同步到数据库
"""

import os
import sys
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_report.settings')
django.setup()

from medical_records.models import SystemSettings


def sync_llm_settings():
    """同步LLM设置"""
    print("🔄 同步LLM设置...")

    # 从环境变量读取配置
    llm_api_url = os.getenv('LLM_API_URL', 'https://api.siliconflow.cn')
    llm_api_key = os.getenv('LLM_API_KEY', '')
    llm_model_name = os.getenv('LLM_MODEL_NAME', 'deepseek-ai/DeepSeek-V3.2-Exp')
    # 使用统一的AI模型超时配置
    ai_model_timeout = os.getenv('AI_MODEL_TIMEOUT', '300')

    # 更新数据库设置
    SystemSettings.set_setting('llm_api_url', llm_api_url, 'LLM API地址', '大语言模型API地址')
    SystemSettings.set_setting('llm_api_key', llm_api_key, 'LLM API密钥', '大语言模型API密钥')
    SystemSettings.set_setting('llm_model_name', llm_model_name, 'LLM模型名称', '使用的大语言模型名称')
    SystemSettings.set_setting('ai_model_timeout', ai_model_timeout, 'AI模型统一超时时间', '所有AI模型API请求的统一超时时间（秒）')

    print(f"✅ LLM API地址: {llm_api_url}")
    print(f"✅ LLM模型名称: {llm_model_name}")
    print(f"✅ AI模型统一超时时间: {ai_model_timeout}秒")
    if llm_api_key:
        print(f"✅ LLM API密钥: 已设置")
    else:
        print(f"⚠️  LLM API密钥: 未设置，可能影响API调用")

    print("\n🎉 LLM设置同步完成！")


def test_llm_config():
    """测试LLM配置"""
    print("\n🧪 测试LLM配置...")

    from medical_records.services import get_llm_api_status

    # 检查API状态
    status = get_llm_api_status()
    print(f"LLM API状态: {'✅ 正常' if status else '❌ 不可用'}")

    # 显示当前配置
    llm_api_url = SystemSettings.get_setting('llm_api_url')
    llm_model_name = SystemSettings.get_setting('llm_model_name')
    ai_model_timeout = SystemSettings.get_setting('ai_model_timeout')

    print(f"当前配置:")
    print(f"  - API地址: {llm_api_url}")
    print(f"  - 模型名称: {llm_model_name}")
    print(f"  - AI模型统一超时时间: {ai_model_timeout}秒")


if __name__ == '__main__':
    sync_llm_settings()
    test_llm_config()
