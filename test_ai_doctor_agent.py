"""
测试AI Doctor Agent功能

使用方法：
python manage.py shell < test_ai_doctor_agent.py
或者在Django shell中直接运行此脚本
"""

import os
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'health_report.settings')
django.setup()

from django.contrib.auth import get_user_model
from medical_records.ai_doctor_agent import create_ai_doctor_agent
from medical_records.models import HealthCheckup, Conversation

User = get_user_model()

def test_agent():
    """测试Agent基本功能"""
    print("\n" + "="*80)
    print("开始测试 AI Doctor Agent")
    print("="*80)

    # 获取一个测试用户
    try:
        user = User.objects.first()
        if not user:
            print("❌ 错误：数据库中没有用户，请先创建用户")
            return

        print(f"✓ 找到测试用户: {user.username}")
    except Exception as e:
        print(f"❌ 获取用户失败: {e}")
        return

    # 创建Agent实例
    try:
        agent = create_ai_doctor_agent(user)
        print("✓ Agent创建成功")
    except Exception as e:
        print(f"❌ Agent创建失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 测试1：简单问题
    print("\n" + "-"*80)
    print("测试1: 简单健康咨询问题")
    print("-"*80)

    test_question_1 = "我最近感觉有点疲劳，有什么建议吗？"

    print(f"用户问题: {test_question_1}")

    try:
        result = agent.ask_question(test_question_1)

        if result.get('success'):
            print(f"\n✓ Agent回答成功!")
            print(f"\n回答内容:\n{'-'*40}")
            print(result['answer'][:500])  # 只显示前500字符
            print(f"\n{'-'*40}")
            print(f"完整回答长度: {len(result['answer'])} 字符")
        else:
            print(f"\n❌ Agent回答失败: {result.get('error')}")
    except Exception as e:
        print(f"❌ 测试1执行失败: {e}")
        import traceback
        traceback.print_exc()

    # 测试2：带体检报告的问题
    print("\n" + "-"*80)
    print("测试2: 带体检报告的健康咨询")
    print("-"*80)

    # 获取用户的体检报告
    checkups = HealthCheckup.objects.filter(user=user)[:3]

    if checkups:
        print(f"✓ 找到 {len(checkups)} 份体检报告")

        test_question_2 = "帮我分析一下我的体检报告，有什么需要注意的吗？"

        print(f"用户问题: {test_question_2}")
        print(f"使用报告: {[c.hospital for c in checkups]}")

        try:
            result = agent.ask_question(test_question_2, selected_reports=checkups)

            if result.get('success'):
                print(f"\n✓ Agent回答成功!")
                print(f"\n回答内容:\n{'-'*40}")
                print(result['answer'][:500])
                print(f"\n{'-'*40}")
                print(f"完整回答长度: {len(result['answer'])} 字符")
            else:
                print(f"\n❌ Agent回答失败: {result.get('error')}")
        except Exception as e:
            print(f"❌ 测试2执行失败: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("⚠️  用户没有体检报告，跳过测试2")

    # 测试3：继续对话
    print("\n" + "-"*80)
    print("测试3: 继续对话")
    print("-"*80)

    try:
        # 获取一个现有对话或创建新对话
        conversation = Conversation.objects.filter(user=user, is_active=True).first()

        if conversation:
            print(f"✓ 使用现有对话: {conversation.title}")
        else:
            print("⚠️  没有现有对话，创建新对话...")
            conversation = Conversation.create_new_conversation(user, "测试对话")

        test_question_3 = "我想了解更多关于高血压的预防知识"

        print(f"用户问题: {test_question_3}")

        agent_with_conv = create_ai_doctor_agent(user, conversation)
        result = agent_with_conv.ask_question(test_question_3)

        if result.get('success'):
            print(f"\n✓ Agent回答成功!")
            print(f"\n回答内容:\n{'-'*40}")
            print(result['answer'][:500])
            print(f"\n{'-'*40}")
            print(f"完整回答长度: {len(result['answer'])} 字符")
        else:
            print(f"\n❌ Agent回答失败: {result.get('error')}")

    except Exception as e:
        print(f"❌ 测试3执行失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)
    print("测试完成!")
    print("="*80)


if __name__ == "__main__":
    test_agent()
