"""
AI Doctor Agent - 真正的LangChain Agent实现

这个版本使用真正的LangChain Agent，能够自主调用工具
"""

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from typing import List, Dict, Optional
from .models import (
    HealthCheckup, HealthIndicator, HealthAdvice,
    Conversation, Medication, MedicationRecord, UserProfile
)
import json


# ==================== Agent 工具实现 ====================
# 这些工具会被Agent真正调用

@tool
def get_user_profile(user_id: int) -> str:
    """
    获取用户的个人基本信息（年龄、性别等）

    Args:
        user_id: 用户ID

    Returns:
        str: 用户个人信息的文本描述
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()

        user = User.objects.get(id=user_id)

        try:
            profile = user.userprofile
            info = []

            if profile.gender:
                info.append(f"性别: {profile.get_gender_display()}")

            if profile.age:
                info.append(f"年龄: {profile.age}岁")

            if profile.birth_date:
                info.append(f"出生日期: {profile.birth_date.strftime('%Y-%m-%d')}")

            if profile.phone:
                info.append(f"联系电话: {profile.phone}")

            if profile.address:
                info.append(f"地址: {profile.address}")

            return " | ".join(info) if info else "用户暂无详细个人信息"

        except UserProfile.DoesNotExist:
            return "用户暂无个人信息记录"

    except Exception as e:
        return f"获取用户信息失败: {str(e)}"


@tool
def get_recent_checkups(user_id: int, limit: int = 3) -> str:
    """
    获取用户最近的体检报告摘要信息

    Args:
        user_id: 用户ID
        limit: 最多获取几份报告，默认3份

    Returns:
        str: 体检报告摘要信息，包含日期、医院、异常指标等
    """
    try:
        checkups = HealthCheckup.objects.filter(
            user_id=user_id
        ).order_by('-checkup_date')[:limit]

        if not checkups:
            return "用户暂无体检报告记录"

        result = []
        for checkup in checkups:
            # 获取异常指标数量
            abnormal_count = HealthIndicator.objects.filter(
                checkup=checkup,
                status='abnormal'
            ).count()

            attention_count = HealthIndicator.objects.filter(
                checkup=checkup,
                status='attention'
            ).count()

            info = f"报告{checkup.id}: {checkup.checkup_date.strftime('%Y-%m-%d')} @ {checkup.hospital}"

            if abnormal_count > 0 or attention_count > 0:
                info += f" (异常: {abnormal_count}, 关注: {attention_count})"

            result.append(info)

        return "\n".join(result)

    except Exception as e:
        return f"获取体检报告失败: {str(e)}"


@tool
def get_medication_info(user_id: int) -> str:
    """
    获取用户当前正在服用的药物信息

    Args:
        user_id: 用户ID

    Returns:
        str: 用药信息的文本描述，包括药名、剂量、服用周期等
    """
    try:
        from datetime import date

        medications = Medication.objects.filter(
            user_id=user_id,
            is_active=True,
            start_date__lte=date.today(),
            end_date__gte=date.today()
        ).order_by('-created_at')

        if not medications:
            return "用户当前无正在服用的药物"

        result = []
        for med in medications:
            info = f"- {med.medicine_name}"
            info += f" | 剂量: {med.dosage}"
            info += f" | 周期: {med.start_date} 至 {med.end_date}"

            # 获取最近服药记录
            records = MedicationRecord.objects.filter(
                medication=med
            ).order_by('-record_date')[:5]

            if records:
                record_info = ", ".join([r.record_date.strftime('%m-%d') for r in records])
                info += f" | 最近服药: {record_info}"

            if med.notes:
                info += f" | 备注: {med.notes}"

            result.append(info)

        return "\n".join(result)

    except Exception as e:
        return f"获取用药信息失败: {str(e)}"


@tool
def get_health_indicators_detail(user_id: int, checkup_ids: List[int]) -> str:
    """
    获取指定体检报告的详细健康指标数据

    Args:
        user_id: 用户ID
        checkup_ids: 体检报告ID列表

    Returns:
        str: 详细健康指标的文本描述
    """
    try:
        checkups = HealthCheckup.objects.filter(
            id__in=checkup_ids,
            user_id=user_id
        ).order_by('-checkup_date')

        if not checkups:
            return f"未找到指定的体检报告: {checkup_ids}"

        result = []

        for checkup in checkups:
            result.append(f"\n=== 体检报告 {checkup.id} ===")
            result.append(f"日期: {checkup.checkup_date.strftime('%Y-%m-%d')}")
            result.append(f"医院: {checkup.hospital}")

            indicators = HealthIndicator.objects.filter(checkup=checkup)

            # 按类型分组
            by_type = {}
            for ind in indicators:
                if ind.indicator_type not in by_type:
                    by_type[ind.indicator_type] = []
                by_type[ind.indicator_type].append(ind)

            for ind_type, inds in by_type.items():
                result.append(f"\n{ind_type}:")
                for ind in inds:
                    line = f"  {ind.indicator_name}: {ind.value}"
                    if ind.unit:
                        line += f" {ind.unit}"
                    if ind.status == 'abnormal':
                        line += f" [异常] 参考值: {ind.reference_range}"
                    result.append(line)

        return "\n".join(result)

    except Exception as e:
        return f"获取详细指标失败: {str(e)}"


@tool
def check_health_knowledge(keyword: str) -> str:
    """
    查询健康知识库中的相关信息

    Args:
        keyword: 要查询的关键词，如"高血压"、"糖尿病"等

    Returns:
        str: 健康知识的文本描述
    """
    return f"""
关于 '{keyword}' 的健康知识：

【温馨提示】
以下内容仅供参考，具体诊疗请遵医嘱。

【建议】
- 如有相关症状，建议及时就医咨询专业医生
- 定期体检，监测相关健康指标
- 保持健康生活方式

此功能可接入医学知识库API获取更详细的信息
"""


# ==================== Agent服务类 ====================

class RealAIDoctorAgent:
    """真正的AI医生Agent - 使用LangChain create_agent"""

    def __init__(self, user, conversation=None):
        """
        初始化Agent

        Args:
            user: Django用户对象
            conversation: 对话对象（可选）
        """
        self.user = user
        self.conversation = conversation

        # 获取AI医生配置
        from .models import SystemSettings
        self.provider = SystemSettings.get_setting('ai_doctor_provider', 'openai')
        self.api_url = SystemSettings.get_setting('ai_doctor_api_url')
        self.api_key = SystemSettings.get_setting('ai_doctor_api_key')
        self.model_name = SystemSettings.get_setting('ai_doctor_model_name')
        self.timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        self.max_tokens = int(SystemSettings.get_setting('ai_doctor_max_tokens', '4000'))

        # 创建工具列表（这些是真正可调用的工具）
        self.tools = [
            get_user_profile,
            get_recent_checkups,
            get_medication_info,
            get_health_indicators_detail,
            check_health_knowledge,
        ]

        # 创建LLM
        self.llm = self._get_llm()

        # 创建Agent（真正的LangChain Agent）
        try:
            system_prompt = """
你是一个专业的AI健康咨询助手。你会：

1. 主动使用工具获取用户的健康信息（个人资料、体检报告、用药记录等）
2. 分析所有信息后给出全面的健康建议
3. 如果信息不足，主动调用工具获取更多信息
4. 给出具体、可操作的健康指导

注意事项：
- 工具调用要精准，只调用必要的工具
- 姿态基于实际数据给出建议，不要编造信息
- 始终提醒用户，建议仅供参考，具体诊疗请遵医嘱
"""

            self.agent = create_agent(
                model=self.llm,
                tools=self.tools,
                system_prompt=system_prompt
            )
            print(f"[Real Agent] ✓ 真正的LangChain Agent创建成功!")
        except Exception as e:
            print(f"[Real Agent] ✗ Agent创建失败: {e}")
            import traceback
            traceback.print_exc()
            self.agent = None

    def _get_llm(self):
        """获取配置的LLM实例"""
        # 修复API URL - 移除末尾的 /chat/completions（如果存在）
        # LangChain会自动添加
        base_url = self.api_url
        if base_url:
            # 如果URL已包含 /chat/completions，需要移除
            if '/chat/completions' in base_url:
                base_url = base_url.split('/chat/completions')[0]
            # 移除末尾斜杠
            base_url = base_url.rstrip('/')

        if self.provider == 'openai' or not self.api_url:
            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                base_url=base_url,
                temperature=0.7,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
        elif self.provider == 'anthropic':
            return ChatAnthropic(
                model=self.model_name,
                api_key=self.api_key,
                temperature=0.7,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
        else:
            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                base_url=base_url,
                temperature=0.7,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

    def ask_question(self, user_question: str, selected_reports=None, selected_medications=None) -> Dict:
        """
        使用真正的Agent处理用户问题

        Args:
            user_question: 用户问题
            selected_reports: 用户选择的体检报告
            selected_medications: 用户选择的药单

        Returns:
            dict: 包含answer, prompt等
        """
        if not self.agent:
            return {
                'answer': None,
                'error': 'Agent未初始化成功',
                'success': False
            }

        try:
            print(f"\n{'='*80}")
            print(f"[Real Agent] 开始处理问题")
            print(f"[问题] {user_question}")
            print(f"[用户ID] {self.user.id}")
            print(f"[对话ID] {self.conversation.id if self.conversation else '新对话'}")

            # 检测是否为继续对话
            is_continuation = self.conversation is not None

            # 获取对话历史（如果是继续对话）
            conversation_history = []
            if is_continuation:
                from .models import HealthAdvice
                recent_advices = HealthAdvice.get_conversation_messages(self.conversation.id)

                # 获取最近3轮对话作为上下文
                for advice in recent_advices[-3:]:
                    if advice.question and advice.answer:
                        conversation_history.append({
                            'question': advice.question,
                            'answer': advice.answer[:500]  # 限制历史回答长度
                        })

                print(f"[继续对话] 检测到继续对话，历史轮次: {len(conversation_history)}")

            # 构建初始消息
            if is_continuation and conversation_history:
                # 继续对话的专用prompt
                history_text = "\n\n".join([
                    f"第{i+1}轮对话:\n用户: {ctx['question']}\nAI: {ctx['answer']}"
                    for i, ctx in enumerate(conversation_history)
                ])

                initial_message = f"""用户ID: {self.user.id}

【重要提示】这是一次继续对话，用户正在基于之前的对话提出后续问题。

【对话历史】
{history_text}

【当前问题】
用户现在提出新的问题: {user_question}

【你的任务】
1. 这是同一对话的延续，请结合之前的对话历史来理解用户的关注点
2. 重点关注用户的新问题，不要重复之前的建议
3. 如果用户的问题与之前的讨论相关，请参考历史回答并进一步深入
4. 如果用户提出了新的健康担忧，请同时考虑历史背景
5. 保持对话的连贯性和一致性

请使用工具获取用户的健康信息，然后给出全面的建议。
"""
            else:
                # 新对话的prompt
                initial_message = f"""用户ID: {self.user.id}
用户问题: {user_question}

请使用工具获取用户的健康信息，然后给出全面的建议。
"""

            if selected_reports:
                initial_message += f"\n用户已选择 {len(selected_reports)} 份体检报告 (ID: {[r.id for r in selected_reports]})"

            if selected_medications:
                initial_message += f"\n用户已选择 {len(selected_medications)} 个药单"

            # 使用LangChain的invoke方法
            # Agent会自主决定调用哪些工具
            response = self.agent.invoke({
                "messages": [{"role": "user", "content": initial_message}]
            })

            # 提取最终回答
            if hasattr(response, 'messages'):
                # 获取最后一条消息
                final_message = response.messages[-1]
                answer = final_message.content
            else:
                answer = str(response)

            print(f"[Real Agent] ✓ 回答生成成功，长度: {len(answer)} 字符")

            return {
                'answer': answer,
                'prompt': initial_message,
                'success': True,
                'is_continuation': is_continuation,
                'conversation_history_count': len(conversation_history) if is_continuation else 0
            }

        except Exception as e:
            error_msg = f"Agent执行失败: {str(e)}"
            print(f"[Real Agent] ✗ {error_msg}")
            import traceback
            traceback.print_exc()

            return {
                'answer': None,
                'error': error_msg,
                'success': False
            }


# ==================== 便捷函数 ====================

def create_real_ai_doctor_agent(user, conversation=None):
    """
    创建真正的AI医生Agent

    Args:
        user: Django用户对象
        conversation: 对话对象（可选）

    Returns:
        RealAIDoctorAgent: 真正的Agent实例
    """
    return RealAIDoctorAgent(user, conversation)
