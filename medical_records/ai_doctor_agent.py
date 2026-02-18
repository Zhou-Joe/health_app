"""
AI Doctor Agent - 基于LangChain的智能健康咨询Agent

该Agent能够：
1. 主动调用工具询问用户的健康相关问题
2. 获取用户的健康数据（体检报告、用药记录等）
3. 汇总所有信息后给出全面的健康建议
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


# ==================== 辅助函数 ====================

def format_health_data_for_prompt(health_data):
    """将健康数据格式化为简洁的文本格式，节省token"""
    if not health_data or not health_data.get('checkups'):
        return "暂无健康数据"

    formatted_data = []

    for checkup in health_data['checkups']:
        date = checkup.get('date', '未知日期')
        hospital = checkup.get('hospital', '未知医院')

        formatted_data.append(f"\n体检报告 - {date} ({hospital}):")

        indicators = checkup.get('indicators', {})
        for indicator_type, indicator_list in indicators.items():
            if indicator_list:
                formatted_data.append(f"  {indicator_type}:")
                for indicator in indicator_list:
                    name = indicator.get('name', '')
                    value = indicator.get('value', '')
                    unit = indicator.get('unit', '')

                    # 基础格式：指标名称：数值 单位
                    line = f"    {name}：{value}"
                    if unit:
                        line += f" {unit}"

                    # 添加异常标记
                    if indicator.get('abnormal'):
                        line += " ⚠️异常"

                    formatted_data.append(line)

    return '\n'.join(formatted_data)


def format_conversation_history(conversation_context):
    """将对话历史格式化为简单文本格式，节省token"""
    if not conversation_context:
        return "无"

    formatted_lines = []

    for item in conversation_context:
        timestamp = item.get('created_at', '')
        question = item.get('question', '')
        answer = item.get('answer', '')

        # 格式：时间，问，答 换行
        formatted_lines.append(f"时间：{timestamp}")
        formatted_lines.append(f"问：{question}")
        formatted_lines.append(f"答：{answer}")
        formatted_lines.append("")  # 空行分隔

    return "\n".join(formatted_lines)


# ==================== Agent 工具定义 ====================

@tool
def get_user_profile() -> str:
    """
    获取用户的个人基本信息（年龄、性别等）

    Returns:
        str: 用户个人信息的文本描述
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # 从Agent的context中获取当前用户
    # 这将在Agent运行时通过middleware注入
    return "需要通过context获取当前用户信息"


@tool
def get_recent_checkups(limit: int = 3) -> str:
    """
    获取用户最近的体检报告摘要信息

    Args:
        limit: 最多获取几份报告，默认3份

    Returns:
        str: 体检报告摘要信息，包含日期、医院、异常指标等
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    return "需要通过context获取当前用户的体检报告"


@tool
def get_medication_info() -> str:
    """
    获取用户当前正在服用的药物信息

    Returns:
        str: 用药信息的文本描述，包括药名、剂量、服用周期等
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    return "需要通过context获取当前用户的用药信息"


@tool
def get_health_indicators(checkup_ids: List[int]) -> str:
    """
    获取指定体检报告的详细健康指标数据

    Args:
        checkup_ids: 体检报告ID列表

    Returns:
        str: 详细健康指标的文本描述
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    return f"需要获取体检报告 {checkup_ids} 的详细指标数据"


@tool
def get_conversation_history(conversation_id: Optional[int] = None, limit: int = 10) -> str:
    """
    获取用户的对话历史记录

    Args:
        conversation_id: 对话ID，如果为None则获取所有对话
        limit: 最多获取几条历史对话

    Returns:
        str: 对话历史的文本描述
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()

    return "需要通过context获取当前用户的对话历史"


@tool
def search_similar_cases(symptoms: str, limit: int = 5) -> str:
    """
    根据症状描述搜索相似的健康案例（仅用于参考，不做诊断）

    Args:
        symptoms: 症状描述
        limit: 返回案例数量限制

    Returns:
        str: 相似案例的参考信息
    """
    return f"根据症状 '{symptoms}' 搜索到的参考案例信息（此为模拟功能）"


@tool
def check_health_knowledge(keyword: str) -> str:
    """
    查询健康知识库中的相关信息

    Args:
        keyword: 要查询的关键词，如"高血压"、"糖尿病"等

    Returns:
        str: 健康知识的文本描述
    """
    return f"关于 '{keyword}' 的健康知识信息（此为模拟功能）"


# ==================== Agent 服务类 ====================

class AIDoctorAgentService:
    """AI医生Agent服务类"""

    def __init__(self, user, conversation=None):
        """
        初始化Agent服务

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

        # 工具列表
        self.tools = [
            get_user_profile,
            get_recent_checkups,
            get_medication_info,
            get_health_indicators,
            get_conversation_history,
            search_similar_cases,
            check_health_knowledge,
        ]

    def _get_llm(self):
        """获取配置的LLM实例"""
        if self.provider == 'openai' or not self.api_url:
            # 使用OpenAI兼容格式
            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                base_url=self.api_url,
                temperature=0.7,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
        elif self.provider == 'anthropic':
            # 使用Anthropic格式
            return ChatAnthropic(
                model=self.model_name,
                api_key=self.api_key,
                temperature=0.7,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
        else:
            # 默认使用OpenAI兼容格式
            return ChatOpenAI(
                model=self.model_name,
                api_key=self.api_key,
                base_url=self.api_url,
                temperature=0.7,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )

    def _create_user_context_middleware(self):
        """创建用户上下文中间件，用于注入用户信息到工具调用"""
        from langchain.agents import createMiddleware

        def inject_user_context(request, handler):
            """在工具调用前注入用户上下文"""
            # 将用户信息添加到请求的context中
            request.runtime.context['user'] = self.user
            request.runtime.context['conversation'] = self.conversation

            # 执行工具调用
            return handler(request)

        return createMiddleware({
            'name': 'InjectUserContext',
            'wrapModelCall': inject_user_context
        })

    def _execute_tool_with_context(self, tool_name: str, **kwargs) -> str:
        """
        在用户上下文中执行工具

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            str: 工具执行结果
        """
        user = self.user
        conversation = self.conversation

        try:
            if tool_name == 'get_user_profile':
                return self._get_user_profile_impl(user)

            elif tool_name == 'get_recent_checkups':
                limit = kwargs.get('limit', 3)
                return self._get_recent_checkups_impl(user, limit)

            elif tool_name == 'get_medication_info':
                return self._get_medication_info_impl(user)

            elif tool_name == 'get_health_indicators':
                checkup_ids = kwargs.get('checkup_ids', [])
                return self._get_health_indicators_impl(user, checkup_ids)

            elif tool_name == 'get_conversation_history':
                conv_id = kwargs.get('conversation_id')
                limit = kwargs.get('limit', 10)
                return self._get_conversation_history_impl(user, conv_id, limit)

            elif tool_name == 'search_similar_cases':
                symptoms = kwargs.get('symptoms', '')
                return self._search_similar_cases_impl(symptoms)

            elif tool_name == 'check_health_knowledge':
                keyword = kwargs.get('keyword', '')
                return self._check_health_knowledge_impl(keyword)

            else:
                return f"未知的工具: {tool_name}"

        except Exception as e:
            return f"工具执行失败 ({tool_name}): {str(e)}"

    # ==================== 工具实现 ====================

    def _get_user_profile_impl(self, user) -> str:
        """获取用户个人信息"""
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

    def _get_recent_checkups_impl(self, user, limit: int) -> str:
        """获取最近的体检报告"""
        checkups = HealthCheckup.objects.filter(
            user=user
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

    def _get_medication_info_impl(self, user) -> str:
        """获取用药信息"""
        from datetime import date

        medications = Medication.objects.filter(
            user=user,
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

    def _get_health_indicators_impl(self, user, checkup_ids: List[int]) -> str:
        """获取详细健康指标"""
        checkups = HealthCheckup.objects.filter(
            id__in=checkup_ids,
            user=user
        ).order_by('-checkup_date')

        if not checkups:
            return f"未找到指定的体检报告: {checkup_ids}"

        # 构建健康数据
        health_data = {
            'checkups': []
        }

        for checkup in checkups:
            indicators = HealthIndicator.objects.filter(checkup=checkup)
            checkup_data = {
                'date': checkup.checkup_date.strftime('%Y-%m-%d'),
                'hospital': checkup.hospital,
                'indicators': {}
            }

            # 按类型分组指标
            for indicator in indicators:
                indicator_type = indicator.indicator_type
                if indicator_type not in checkup_data['indicators']:
                    checkup_data['indicators'][indicator_type] = []

                indicator_data = {
                    'name': indicator.indicator_name,
                    'value': indicator.value,
                    'unit': indicator.unit
                }

                # 异常指标添加参考范围和异常标记
                if indicator.status == 'abnormal':
                    indicator_data['reference'] = indicator.reference_range
                    indicator_data['abnormal'] = True

                checkup_data['indicators'][indicator_type].append(indicator_data)

            health_data['checkups'].append(checkup_data)

        # 格式化为文本
        return format_health_data_for_prompt(health_data)

    def _get_conversation_history_impl(self, user, conversation_id: Optional[int], limit: int) -> str:
        """获取对话历史"""
        if conversation_id:
            # 获取特定对话的历史
            try:
                conversation = Conversation.objects.get(id=conversation_id, user=user)
                messages = HealthAdvice.get_conversation_messages(conversation.id)
            except Conversation.DoesNotExist:
                return f"对话ID {conversation_id} 不存在"
        else:
            # 获取最近的所有对话
            from django.db.models import Max
            recent_conversations = Conversation.objects.filter(
                user=user
            ).order_by('-updated_at')[:limit]

            messages = []
            for conv in recent_conversations:
                conv_messages = HealthAdvice.get_conversation_messages(conv.id)
                messages.extend(conv_messages)

        if not messages:
            return "暂无对话历史"

        # 格式化对话历史
        context = []
        for msg in messages[:limit]:
            if msg.question and msg.answer:
                context.append({
                    'question': msg.question,
                    'answer': msg.answer[:200] + "..." if len(msg.answer) > 200 else msg.answer,
                    'time': msg.created_at.strftime('%m-%d %H:%M')
                })

        return format_conversation_history(context)

    def _search_similar_cases_impl(self, symptoms: str) -> str:
        """搜索相似案例（模拟功能）"""
        # 这里可以接入真实的医学知识库或案例数据库
        return f"""
根据症状 "{symptoms}" 的参考信息：

【注意事项】
以下信息仅供参考，不能替代专业医生诊断。如身体不适，请及时就医。

【一般性建议】
1. 如症状持续或加重，建议及时就医
2. 注意休息，保持良好的作息习惯
3. 避免自行用药，应遵医嘱

【紧急情况】
如出现以下情况，请立即就医：
- 呼吸困难
- 剧烈胸痛
- 意识模糊
- 严重出血

此为模拟功能，实际应用中可接入医学知识库API
"""

    def _check_health_knowledge_impl(self, keyword: str) -> str:
        """查询健康知识（模拟功能）"""
        # 这里可以接入真实的健康知识库API
        return f"""
关于 "{keyword}" 的健康知识：

【温馨提示】
以下内容仅供参考，具体诊疗请遵医嘱。

此为模拟功能，实际应用中可接入健康知识库API，如：
- 权威医学数据库
- 健康科普内容库
- 医学指南和专家共识
"""

    # ==================== Agent执行 ====================

    def ask_question(self, user_question: str, selected_reports=None, selected_medications=None) -> Dict:
        """
        使用Agent处理用户问题

        Args:
            user_question: 用户问题
            selected_reports: 用户选择的体检报告
            selected_medications: 用户选择的药单

        Returns:
            dict: 包含answer, prompt, conversation_context等
        """
        from .llm_prompts import AI_DOCTOR_SYSTEM_PROMPT

        try:
            print(f"\n{'='*80}")
            print(f"[AI Doctor Agent] 开始处理用户问题")
            print(f"[问题] {user_question}")
            print(f"[用户] {self.user.username}")
            print(f"[对话ID] {self.conversation.id if self.conversation else '新建对话'}")

            # 构建系统提示词
            system_prompt = AI_DOCTOR_SYSTEM_PROMPT + """

【重要说明】
你现在拥有多个工具可以主动询问用户更多信息。在回答用户问题之前，你应该：

1. **分析用户问题**：理解用户的核心需求
2. **判断信息完整性**：是否需要更多信息才能给出全面建议
3. **主动调用工具**：
   - 如果需要了解用户基本信息，调用 get_user_profile
   - 如果需要了解体检情况，调用 get_recent_checkups 或 get_health_indicators
   - 如果需要了解用药情况，调用 get_medication_info
   - 如果需要了解历史对话，调用 get_conversation_history
   - 如果需要查询健康知识，调用 check_health_knowledge
4. **汇总分析**：综合所有信息给出全面的健康建议
5. **明确建议**：给出具体、可操作的健康指导

【注意事项】
- 工具调用要精准，只调用必要的工具
- 避免重复获取相同信息
- 始终基于实际数据给出建议，不要编造信息
- 如信息不足，主动询问用户更多信息
- 回复要简洁直接，不要客套话和过渡词
"""

            # 获取对话上下文
            conversation_context = None
            if self.conversation:
                messages = HealthAdvice.get_conversation_messages(self.conversation.id)
                conversation_context = []
                for msg in messages:
                    if msg.question and msg.answer:
                        conversation_context.append({
                            'question': msg.question,
                            'answer': msg.answer[:200] + "..." if len(msg.answer) > 200 else msg.answer,
                            'time': msg.created_at.strftime('%m-%d %H:%M')
                        })

            # 构建初始消息
            initial_message = f"用户问题: {user_question}\n\n"

            # 添加个人信息
            try:
                user_profile = self.user.userprofile
                if user_profile.birth_date or user_profile.gender:
                    initial_message += "用户基本信息:\n"
                    initial_message += f"- 性别: {user_profile.get_gender_display()}\n"
                    if user_profile.age:
                        initial_message += f"- 年龄: {user_profile.age}岁\n"
            except UserProfile.DoesNotExist:
                pass

            # 添加用户选择的报告信息（如果有）
            if selected_reports:
                initial_message += f"\n用户已选择 {len(selected_reports)} 份体检报告用于分析\n"
                report_ids = [r.id for r in selected_reports]
                initial_message += f"报告ID: {report_ids}\n"

            # 添加用药信息（如果有）
            if selected_medications:
                initial_message += f"\n用户已选择 {len(selected_medications)} 个药单用于分析\n"

            # 添加对话历史（如果有）
            if conversation_context:
                initial_message += f"\n已有 {len(conversation_context)} 条历史对话记录\n"

            print(f"[初始消息] {initial_message[:200]}...")

            # 创建LLM
            llm = self._get_llm()
            print(f"[LLM配置] Provider: {self.provider}, Model: {self.model_name}")

            # 创建Agent（不使用工具，直接让LLM分析）
            # 注意：这里我们简化实现，直接调用LLM，而不是使用Agent工具调用
            # 在实际应用中，可以让LLM主动调用工具获取信息

            # 构建消息列表
            messages = [
                {"role": "system", "content": system_prompt},
            ]

            # 添加对话历史
            if conversation_context:
                for ctx in conversation_context[-5:]:  # 最近5条对话
                    messages.append({"role": "user", "content": ctx['question']})
                    messages.append({"role": "assistant", "content": ctx['answer']})

            # 添加当前问题
            messages.append({"role": "user", "content": initial_message})

            # 准备API请求
            import requests
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

            # 构建请求数据
            data = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": 0.7
            }

            print(f"[API调用] 准备调用LLM API...")

            # 调用API
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json()
                answer = result['choices'][0]['message']['content']

                # 清理thinking标签
                import re
                cleaned_answer = answer.strip()

                thinking_patterns = [
                    (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                    (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                    (r'⠀[\s\S]*?⠀', '', re.IGNORECASE),
                ]

                for pattern, replacement, *flags in thinking_patterns:
                    flags = flags[0] if flags else 0
                    cleaned_answer = re.sub(pattern, replacement, cleaned_answer, flags=flags)

                print(f"[成功] Agent回答生成成功")
                print(f"[回答长度] {len(cleaned_answer)} 字符")

                # 构建用于显示的prompt
                prompt_sent = initial_message
                if selected_reports:
                    prompt_sent += "\n\n用户选择的体检报告数据将另外提供"

                return {
                    'answer': cleaned_answer,
                    'prompt': prompt_sent,
                    'conversation_context': conversation_context,
                    'success': True
                }
            else:
                error_msg = f"API调用失败: {response.status_code} - {response.text}"
                print(f"[失败] {error_msg}")
                return {
                    'answer': None,
                    'error': error_msg,
                    'success': False
                }

        except Exception as e:
            error_msg = f"Agent处理失败: {str(e)}"
            print(f"[失败] {error_msg}")
            import traceback
            traceback.print_exc()

            return {
                'answer': None,
                'error': error_msg,
                'success': False
            }


# ==================== 便捷函数 ====================

def create_ai_doctor_agent(user, conversation=None):
    """
    创建AI医生Agent实例

    Args:
        user: Django用户对象
        conversation: 对话对象（可选）

    Returns:
        AIDoctorAgentService: Agent服务实例
    """
    return AIDoctorAgentService(user, conversation)
