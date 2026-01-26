"""
简单的Agent测试
"""
import os
import sys
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_report.settings')
django.setup()

from django.contrib.auth import get_user_model
from medical_records.ai_doctor_agent import create_ai_doctor_agent

User = get_user_model()

# 获取用户
user = User.objects.first()
print(f"✓ 用户: {user.username if user else 'None'}")

if user:
    # 创建Agent
    agent = create_ai_doctor_agent(user)
    print("✓ Agent创建成功")

    # 测试简单问题
    print("\n测试问题: 我最近有点疲劳，有什么建议吗？")
    result = agent.ask_question("我最近有点疲劳，有什么建议吗？")

    if result.get('success'):
        print(f"\n✓ 回答成功! 长度: {len(result['answer'])} 字符")
        print(f"\n前300字符:\n{result['answer'][:300]}")
    else:
        print(f"\n✗ 失败: {result.get('error')}")
else:
    print("✗ 没有用户数据")
