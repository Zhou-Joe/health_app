"""
LLM提示词统一配置模块
整合了非流式和流式响应的所有提示词
"""

# ============================================================================
# 1. OCR提取模块提示词
# ============================================================================

OCR_EXTRACT_SYSTEM_PROMPT = """你是一个专业的医疗数据分析助手，请从体检报告OCR文本中提取健康指标数据，并严格按照指定的JSON格式返回。"""

OCR_EXTRACT_USER_PROMPT_TEMPLATE = """从体检报告OCR文本中提取所有健康指标，返回JSON格式。

文本内容：
{ocr_text}

**优先使用标准指标名称：**
{existing_indicators}

**提取范围：**
- **数值指标
- **诊断结论
- **症状描述
- **检查发现
- **体征数据

**特别注意：**
- 不仅要提取表格数据，还要识别段落中的健康信息
- 对于描述性检查，推断并提取结构化指标
- 确保不遗漏任何数值化或者有明确病症描述的医学检查结果
- 严禁提取个人信息 - 最高优先级规则: 绝对禁止提取以下字段，遇到后必须完全忽略如姓名、性别、年龄、出生日期、身份证号、地址、联系方式等任何个人识别信息

**重要约束：**
1. **不要无中生有：** 只提取OCR文本中明确存在的指标数据以及病症描述
2. **参考值处理：** 如果报告中没有提供参考范围（normal_range），请留空或填null，不要编造
3. **异常判断：** 只有当报告中明确标注了异常（如↑↓箭头、异常字样、超出参考范围）时才标记"是"，否则留空或填null
4. **数据真实性：** 宁可在field留空，也不要编造报告中不存在的内容

**JSON格式：**
{{
    "indicators": [
        {{
            "indicator": "标准医学术语",
            "measured_value": "检测值或描述",
            "normal_range": "正常参考范围（如果报告中没有则填null）",
            "abnormal": "是/否/null（如果报告中没有明确异常标注则填null）"
        }}
    ]
}}

**示例：**
- "血压：120/80mmHg（正常90-139/60-89）" → {{"indicator": "血压", "measured_value": "120/80", "normal_range": "90-139/60-89", "abnormal": "否"}}
- "诊断：2级高血压" → {{"indicator": "高血压", "measured_value": "2级", "normal_range": null, "abnormal": "是"}}
- "脾脏厚度4.5cm" → {{"indicator": "脾脏厚度", "measured_value": "4.5cm", "normal_range": null, "abnormal": null}}
- "红细胞计数 4.5" → {{"indicator": "红细胞计数", "measured_value": "4.5", "normal_range": null, "abnormal": null}}

请严格按照JSON格式返回，不要添加任何解释。切记不要编造报告中不存在的参考范围和异常状态。"""


# ============================================================================
# 2. 视觉模型模块提示词
# ============================================================================

VISION_MODEL_SYSTEM_PROMPT = """你是一个专业的医疗数据分析助手，专门从体检报告图片中提取健康指标数据。"""

VISION_MODEL_USER_PROMPT_TEMPLATE = """分析第{page_num}/{total_pages}页医疗图片，提取所有健康相关信息。

**任务要求：**
1. **体检报告：** 识别并提取所有医学检查结果、指标数据、诊断结论
2. **症状照片：** 详细描述可见的症状表现、体征特征
3. 严禁提取个人信息 - 最高优先级规则: 绝对禁止提取以下字段，遇到后必须完全忽略如姓名、性别、年龄、出生日期、身份证号、地址、联系方式等任何个人识别信息

**提取重点：**
- **数值指标
- **诊断结论
- **症状描述
- **检查发现
- **体征数据

**重要约束：**
1. **不要无中生有：** 只提取图片中明确可见或明确写明的指标数据或者症状描述
2. **参考值处理：** 如果图片中没有提供参考范围（normal_range），请留空或填null，不要编造
3. **异常判断：** 只有当图片中明确标注了异常（如↑↓箭头、异常字样、超出参考范围、阳性）时才标记"是"，否则留空或填null
4. **数据真实性：** 宁可少提取，也不要编造图片中不存在的内容
5. **清晰度要求：** 如果文字模糊不清无法准确识别，建议在指标名称后添加"（模糊）"
6. **纯图片症状照片：** 如果症状描述仅包含图片中的症状特征，不包含文字描述，建议在指标名称后添加"（图片）"




**JSON格式要求：**
{{
    "indicators": [
        {{
            "indicator": "标准医学术语名称",
            "measured_value": "检测值或症状描述",
            "normal_range": "正常参考范围（如果图片中没有则填null）",
            "abnormal": "是/否/null（如果图片中没有明确异常标注则填null）"
        }}
    ]
}}

**示例：**
- 血压"120/80" → {{"indicator": "血压", "measured_value": "120/80", "normal_range": "90-140/60-90", "abnormal": "否"}}
- 红细胞计数"4.5" → {{"indicator": "红细胞计数", "measured_value": "4.5", "normal_range": null, "abnormal": null}}

请严格按照JSON格式返回，不要添加任何解释文字。切记不要编造图片中不存在的参考范围和异常状态。"""


# ============================================================================
# 3. 健康建议模块提示词
# ============================================================================

HEALTH_ADVICE_SYSTEM_PROMPT = """你是一个专业的健康顾问医生，请根据用户的体检指标数据提供健康建议。"""

HEALTH_ADVICE_USER_PROMPT_TEMPLATE = """请根据以下体检指标数据，为用户提供专业的健康建议和生活方式指导。

体检指标数据:
{indicators_text}

{focus_text}

请提供以下方面的建议：
1. **指标解读**: 简要解释各项指标的含义
2. **异常分析**: 针对异常指标提供可能的原因和建议
3. **饮食建议**: 基于体检结果提供饮食调整建议
4. **运动建议**: 推荐适合的运动方式和频率
5. **生活习惯**: 提供作息、戒烟限酒等生活方式建议
6. **定期复查**: 建议需要重点关注和定期复查的指标

请用通俗易懂、专业而不生硬的语言，避免过度医学术语，给出实用的建议。建议要具体可行，避免过于笼统。

注意：
- 如果所有指标正常，重点给出预防保健建议
- 如果有异常指标，重点关注相关风险因素
- 建议用户定期体检，遵医嘱进行复查
- 强调本建议仅供参考，具体诊疗请咨询专业医生"""


# ============================================================================
# 4. 数据整合模块提示词
# ============================================================================

DATA_INTEGRATION_SYSTEM_PROMPT = """你是一个专业的医疗数据标准化专家。你必须严格按照JSON格式返回结果，不要添加任何额外的文字说明。"""

DATA_INTEGRATION_USER_PROMPT_TEMPLATE = """分析{indicator_count}组健康指标，判断哪些指标需要更正：

【首要任务：对齐指标名的命名】
命名统一是最重要的任务！必须仔细检查相同指标是否有不同名称，将所有变体名称对齐到其中一个已有名称，不要创造新名称。
示例：
- "血红蛋白"和"HGB"同时存在 → 统一为"血红蛋白"（选其中一个已有的）
- "空腹血糖"和"血糖"同时存在 → 统一为其中任意一个

【其他需要更正的情况】
1.单位缺失或不统一（如"kg"和"公斤"）→统一标准单位
2.状态错误：只更新value以及参考范围有明显差别的指标
   - 如果value是描述性文字（如"未见异常"、"正常"、"阳性"等）→ status应设为对应状态
   - 如果value明显超出参考范围 → status应为"abnormal"
   - 如果value在参考范围内 → status应为"normal"
   - 如果有参考范围但status标记错误 → 必须更正
3.分类错误或不统一：统一为最准确的分类

【可选的指标分类（indicator_type）】
必须从以下分类中选择，优先选择最具体的分类，最后才使用other：
1. 一般检查
   - general_exam: 一般检查（身高、体重、BMI、血压、心率、体温等）

2. 血液检验
   - blood_routine: 血常规（白细胞、红细胞、血红蛋白、血小板等）
   - biochemistry: 生化检验（血糖、血脂、电解质等）
   - liver_function: 肝功能（ALT、AST、胆红素、白蛋白等）
   - kidney_function: 肾功能（肌酐、尿素氮、尿酸等）
   - thyroid: 甲状腺（T3、T4、TSH等）
   - cardiac: 心脏标志物（肌钙蛋白、BNP、CK-MB等）
   - tumor_markers: 肿瘤标志物（CEA、AFP、CA125、CA199、PSA等）
   - infection: 感染炎症（C反应蛋白CRP、血沉ESR等）
   - blood_rheology: 血液流变（全血粘度、血浆粘度）
   - coagulation: 凝血功能（PT、APTT、纤维蛋白原等）

3. 体液检验
   - urine: 尿液检查（尿常规、尿蛋白、尿糖等）
   - stool: 粪便检查（大便常规、隐血等）
   - pathology: 病理检查（活检病理、细胞学检查、免疫组化）

4. 影像学检查
   - ultrasound: 超声检查（B超、彩超检查发现的胆囊息肉、肝囊肿等）
   - X_ray: X线检查（胸片、骨骼X光等）
   - CT_MRI: CT和MRI检查
   - endoscopy: 内镜检查（胃镜、肠镜、支气管镜等）

5. 专科检查
   - special_organs: 专科检查（眼科视力/眼压、耳鼻喉听力检查、口腔牙齿等）

6. 兜底分类
   - other: 其他检查（仅当无法归入以上任何类别时使用）

【分类判断优先级】
1. 如果是病理活检/细胞学检查 → pathology
2. 如果是超声/B超/彩超 → ultrasound
3. 如果是X线检查 → X_ray
4. 如果是CT或MRI → CT_MRI
5. 如果是内镜（胃镜肠镜） → endoscopy
6. 如果是专科检查（眼耳鼻喉口腔等） → special_organs
7. 如果是血液检验，按具体项目选择最细分的类别（优先级：cardiac/tumor_markers/infection/coagulation > liver/kidney/thyroid > blood_routine > biochemistry）
8. 如果是体液检验，按样本类型（urine/stool）
9. 如果实在无法判断 → other（但这是最后的选择）

【不需要更正的情况】
- 名称已经一致（没有不同变体）
- 单位已经是标准单位
- 状态判断正确
- 分类已经准确

【禁止修改的字段】
- 参考范围（reference_range）：不要返回此字段，保持原值不变

【重要：添加修改理由】
每个变更都必须包含"reason"字段，用简洁的中文说明修改的理由（10个字以内）。

数据：
{indicators_data}

返回格式（只包含需要更正的指标和字段）：
{{
    "changes": [
        {{
            "indicator_id": 123,
            "indicator_name": "统一后的名称",
            "reason": "将'身长'统一为'身高'，保持命名一致性"
        }},
        {{
            "indicator_id": 456,
            "value": "修正后的值",
            "unit": "标准单位",
            "reason": "单位从非标准的'公斤'统一为'kg'"
        }},
        {{
            "indicator_id": 101,
            "indicator_type": "blood_routine",
            "reason": "白细胞计数属于血液常规检查，分类应更正为blood_routine"
        }}
    ]
}}

【关键要求】
1.只返回真正需要更正的指标
2.已经正确的指标不要出现在changes中
3.每个对象必须包含indicator_id、需要修改的字段（只限indicator_name、value、unit、status、indicator_type）和reason
4.reason字段必须用简洁的中文说明修改理由（10个字以内）
5.绝对不要返回reference_range字段
6.纯JSON格式，无markdown{user_prompt_section}
7.如某个indicator_id包含多个修改项，则需要包含在同一个item里"""


# ============================================================================
# 5. AI医生模块提示词
# ============================================================================

AI_DOCTOR_SYSTEM_PROMPT = """你是一位专业的全科医生，请基于用户的健康数据和问题提供专业建议。"""

AI_DOCTOR_USER_PROMPT_TEMPLATE_WITH_DATA = """当前问题：{question}

个人信息：
{personal_info}

对话历史：
{conversation_history}

用户健康数据：
{health_data}

【重要原则】
1. **专注用户问题**：回答的核心必须紧扣用户当前的问题，不要泛泛而谈
2. **精准引用指标**：只分析与问题相关的指标，不要罗列所有数据
   - ⚠️ 绝对不要逐一分析或列举用户提供的所有指标
   - 体检数据仅作为参考素材，只提及相关指标
   - 正常指标不提及，除非与问题直接相关
3. **简洁专业**：回答要直击要点，避免冗长

请基于以上信息：
1. **精准定位问题**：结合对话历史，理解用户真正关心的核心问题
2. **相关数据分析**：只分析与问题相关的健康指标及其趋势变化
3. **针对性建议**：给出具体可行的解决方案和医疗建议
4. **必要时就医**：如有需要，明确建议何时就医或做哪些检查

请用中文回答，语气专业但平易近人。这仅供参考，不能替代面诊。"""

AI_DOCTOR_USER_PROMPT_TEMPLATE_WITHOUT_DATA = """当前问题：{question}

个人信息：
{personal_info}

对话历史：
{conversation_history}

注意：用户选择不提供任何体检报告数据，请仅基于问题提供一般性健康建议。

【重要原则】
1. **专注用户问题**：回答的核心必须紧扣用户当前的问题，不要泛泛而谈
2. **简洁精准**：避免冗长的健康知识科普，直接回应用户的疑问
3. **实用可行**：给出的建议要具体、可操作，避免空泛的理论

请基于以上问题：
1. **精准定位问题**：结合对话历史，理解用户真正关心的核心问题
2. **针对性解答**：直接回答用户疑问，提供相关知识背景
3. **实用建议**：给出具体可行的解决方案或预防措施
4. **就医指引**：明确建议何时需要就医或做哪些检查

请用中文回答，语气专业但平易近人。记住：专注于用户问题，给出精准实用的建议。这仅供参考，不能替代面诊。"""


# ============================================================================
# 6. 用户自定义提示词扩展
# ============================================================================

def add_user_custom_prompt(base_prompt: str, user_prompt: str) -> str:
    """
    添加用户自定义提示词到基础提示词中
    
    Args:
        base_prompt: 基础提示词
        user_prompt: 用户自定义提示词
    
    Returns:
        组合后的提示词
    """
    if not user_prompt or not user_prompt.strip():
        return base_prompt
    
    return f"""{base_prompt}

【用户特别要求】
{user_prompt}

请严格按照上述用户要求进行数据处理。"""


# ============================================================================
# 7. 提示词构建辅助函数
# ============================================================================

def build_ocr_extract_prompt(ocr_text: str, existing_indicators: list) -> tuple:
    """
    构建OCR提取提示词
    
    Args:
        ocr_text: OCR识别的文本
        existing_indicators: 现有标准指标名称列表
    
    Returns:
        (system_prompt, user_prompt)
    """
    existing_list = '\n'.join([f'  - {name}' for name in existing_indicators])
    user_prompt = OCR_EXTRACT_USER_PROMPT_TEMPLATE.format(
        ocr_text=ocr_text,
        existing_indicators=existing_list
    )
    return OCR_EXTRACT_SYSTEM_PROMPT, user_prompt


def build_vision_model_prompt(page_num: int, total_pages: int) -> str:
    """
    构建视觉模型提示词
    
    Args:
        page_num: 当前页码
        total_pages: 总页数
    
    Returns:
        user_prompt
    """
    return VISION_MODEL_USER_PROMPT_TEMPLATE.format(
        page_num=page_num,
        total_pages=total_pages
    )


def build_health_advice_prompt(indicators_text: str, focus_text: str) -> tuple:
    """
    构建健康建议提示词
    
    Args:
        indicators_text: 指标数据文本
        focus_text: 关注重点文本
    
    Returns:
        (system_prompt, user_prompt)
    """
    user_prompt = HEALTH_ADVICE_USER_PROMPT_TEMPLATE.format(
        indicators_text=indicators_text,
        focus_text=focus_text
    )
    return HEALTH_ADVICE_SYSTEM_PROMPT, user_prompt


def build_data_integration_prompt(indicators_data: str, user_prompt: str = None) -> tuple:
    """
    构建数据整合提示词
    
    Args:
        indicators_data: 指标数据JSON字符串
        user_prompt: 用户自定义提示词（可选）
    
    Returns:
        (system_prompt, user_prompt)
    """
    user_prompt_section = ""
    if user_prompt and user_prompt.strip():
        user_prompt_section = f"""

【用户特别要求】
{user_prompt}

请严格按照上述用户要求进行数据整合。"""
    
    # 计算指标数量
    import json
    indicators_json = json.loads(indicators_data)
    indicator_count = len(indicators_json) if isinstance(indicators_json, list) else len(indicators_json.get('indicators', []))
    
    user_prompt = DATA_INTEGRATION_USER_PROMPT_TEMPLATE.format(
        indicator_count=indicator_count,
        indicators_data=indicators_data,
        user_prompt_section=user_prompt_section
    )
    return DATA_INTEGRATION_SYSTEM_PROMPT, user_prompt


def build_ai_doctor_prompt(question: str, personal_info: str, conversation_history: str,
                           health_data: str = None, has_health_data: bool = True) -> str:
    """
    构建AI医生提示词
    
    Args:
        question: 用户问题
        personal_info: 个人信息
        conversation_history: 对话历史
        health_data: 健康数据（可选）
        has_health_data: 是否有健康数据
    
    Returns:
        user_prompt (LangChain流式使用，包含角色定义)
    """
    if has_health_data and health_data:
        template = AI_DOCTOR_USER_PROMPT_TEMPLATE_WITH_DATA
        user_prompt = template.format(
            question=question,
            personal_info=personal_info,
            conversation_history=conversation_history,
            health_data=health_data
        )
    else:
        template = AI_DOCTOR_USER_PROMPT_TEMPLATE_WITHOUT_DATA
        user_prompt = template.format(
            question=question,
            personal_info=personal_info,
            conversation_history=conversation_history
        )
    
    # 对于LangChain流式响应，将system prompt也包含在user message中
    return f"""{AI_DOCTOR_SYSTEM_PROMPT}

{user_prompt}"""
