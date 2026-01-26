"""
测试真正的LangChain Agent
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_report.settings')
django.setup()

from django.contrib.auth import get_user_model
from medical_records.ai_doctor_agent_v2 import create_real_ai_doctor_agent

User = get_user_model()

user = User.objects.first()
print(f"✓ 用户: {user.username if user else 'None'}")

if user:
    # 创建真正的Agent
    agent = create_real_ai_doctor_agent(user)

    if agent.agent:
        print("✓ 真正的LangChain Agent创建成功")
        print("\n测试问题: 我最近有点疲劳，有什么建议吗？")

        result = agent.ask_question("我最近有点疲劳，有什么建议吗？")

        if result.get('success'):
            print(f"\n✓ 回答成功!")
            print(f"\n前500字符:\n{result['answer'][:500]}")
        else:
            print(f"\n✗ 失败: {result.get('error')}")
    else:
        print("✗ Agent创建失败")
else:
    print("✗ 没有用户数据")
