"""
详细测试真正的Agent，看完整输出
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_report.settings')
django.setup()

from django.contrib.auth import get_user_model
from medical_records.ai_doctor_agent_v2 import create_real_ai_doctor_agent

User = get_user_model()

user = User.objects.first()

if user:
    agent = create_real_ai_doctor_agent(user)

    if agent.agent:
        print("=== 测试真正的LangChain Agent ===\n")

        result = agent.ask_question("我最近有点疲劳，有什么建议吗？")

        if result.get('success'):
            answer = result['answer']

            # 提取实际的文本内容
            if hasattr(answer, 'messages'):
                # 从最后的消息中提取
                for msg in reversed(answer.messages):
                    if hasattr(msg, 'content'):
                        content = msg.content
                        if isinstance(content, str) and len(content) > 100:
                            print(f"\n✓ Agent完整回答:\n{'='*60}")
                            print(content)
                            print('='*60)
                            break
            else:
                print(f"\n✓ Agent回答:\n{answer}")
        else:
            print(f"✗ 失败: {result.get('error')}")
