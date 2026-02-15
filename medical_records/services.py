import requests
import json
import time
import re
import base64
from datetime import datetime
from django.conf import settings
from .models import DocumentProcessing, HealthIndicator, SystemSettings
from .llm_prompts import (
    OCR_EXTRACT_SYSTEM_PROMPT,
    OCR_EXTRACT_USER_PROMPT_TEMPLATE,
    VISION_MODEL_SYSTEM_PROMPT,
    VISION_MODEL_USER_PROMPT_TEMPLATE,
    HEALTH_ADVICE_SYSTEM_PROMPT,
    HEALTH_ADVICE_USER_PROMPT_TEMPLATE,
    DATA_INTEGRATION_SYSTEM_PROMPT,
    DATA_INTEGRATION_USER_PROMPT_TEMPLATE,
    build_ocr_extract_prompt,
    build_vision_model_prompt,
    build_health_advice_prompt,
    build_data_integration_prompt
)

# 个人信息过滤关键词列表
PERSONAL_INFO_KEYWORDS = [
    '姓名', 'name', '患者姓名', '姓名：',
    '性别', 'gender', 'sex', '性别：',
    '年龄', 'age', '年龄：',
    '出生日期', 'birthday', 'birth_date', '生日',
    '体检日期', 'checkup_date', '检查日期', 'date',
    '身份证', 'id_card', 'id_number', '证件号',
    '电话', 'phone', 'mobile', 'telephone', '手机', '联系电话',
    '地址', 'address', '住址',
    '民族', 'ethnicity', '族',
    '婚姻', 'marriage', '已婚', '未婚',
]

def is_personal_info_indicator(indicator_name: str) -> bool:
    """
    检查指标名称是否包含个人信息关键词

    Args:
        indicator_name: 指标名称

    Returns:
        True if it's personal info, False otherwise
    """
    if not indicator_name or not isinstance(indicator_name, str):
        return False

    indicator_name_lower = indicator_name.strip().lower()

    for keyword in PERSONAL_INFO_KEYWORDS:
        if keyword.lower() in indicator_name_lower:
            print(f"[过滤] 检测到个人信息字段: '{indicator_name}' (包含关键词: '{keyword}')")
            return True

    return False


class DocumentProcessingService:
    """文档处理服务类"""

    def __init__(self, document_processing):
        self.document_processing = document_processing
        # 从数据库获取动态配置
        self.mineru_api_url = SystemSettings.get_setting('mineru_api_url', 'http://localhost:8000')
        self.modelscope_api_url = SystemSettings.get_setting('llm_api_url', 'http://172.25.48.1:1234')
        self.modelscope_api_key = SystemSettings.get_setting('llm_api_key', '')
        self.llm_model_name = SystemSettings.get_setting('llm_model_name', 'qwen3-4b-instruct')
        self.llm_timeout = int(SystemSettings.get_setting('llm_timeout', '600'))
        self.ocr_timeout = int(SystemSettings.get_setting('ocr_timeout', '300'))

    def update_progress(self, status, progress, message=None, is_error=False):
        """更新处理进度"""
        self.document_processing.status = status
        self.document_processing.progress = progress
        if message and is_error:
            # 只有在明确标记为错误时才设置error_message
            self.document_processing.error_message = message
        elif message and not is_error:
            # 对于正常的进度消息，清除之前的错误信息
            self.document_processing.error_message = None
        self.document_processing.save()

    def perform_ocr(self, file_path):
        """调用MinerU API进行OCR识别"""
        try:
            self.update_progress('ocr_processing', 20, "开始OCR识别...")

            # 准备文件上传 - MinerU需要files数组
            with open(file_path, 'rb') as f:
                files = {'files': f}
                
                # 根据工作流类型选择backend
                workflow_type = getattr(self.document_processing, 'workflow_type', 'ocr_llm')
                if workflow_type == 'vlm_transformers':
                    backend = 'vlm-transformers'  # 使用VLM-Transformers模式
                else:
                    backend = 'pipeline'  # 传统OCR模式
                    
                data = {
                    'parse_method': 'auto',  # 自动识别类型
                    'lang_list': 'ch',        # 中文识别 (字符串格式)
                    'return_md': True,        # 返回markdown格式
                    'formula_enable': True,   # 启用公式识别
                    'table_enable': True,     # 启用表格识别
                    'backend': backend        # 选择处理backend
                }

                # 确保使用正确的MinerU端点
                api_url = self.mineru_api_url
                if not api_url.endswith('/file_parse'):
                    api_url = f"{api_url.rstrip('/')}/file_parse"

                # 调用MinerU API
                response = requests.post(
                    api_url,
                    files=files,
                    data=data,
                    timeout=self.ocr_timeout  # 使用动态超时设置
                )

            if response.status_code == 200:
                result = response.json()

                # MinerU返回的格式是嵌套的：results -> {filename} -> md_content
                ocr_text = ""

                try:
                    if 'results' in result:
                        results = result['results']
                        # 获取第一个文件的markdown内容
                        first_file_key = list(results.keys())[0]
                        if first_file_key in results:
                            file_result = results[first_file_key]
                            if 'md_content' in file_result:
                                ocr_text = file_result['md_content']

                    # 如果没有找到md_content，尝试其他字段
                    if not ocr_text:
                        # 尝试从不同的字段提取文本
                        if isinstance(result, dict):
                            if 'content' in result:
                                ocr_text = result['content']
                            elif 'text' in result:
                                ocr_text = result['text']
                            elif isinstance(result, list) and len(result) > 0:
                                # 如果返回数组，取第一个元素的文本
                                first_item = result[0]
                                if isinstance(first_item, dict):
                                    ocr_text = first_item.get('content', '') or first_item.get('text', '')
                            else:
                                # 如果没有明确的文本字段，尝试转换整个结果
                                import json
                                ocr_text = json.dumps(result, ensure_ascii=False, indent=2)
                        else:
                            ocr_text = str(result)

                except Exception as parse_error:
                    print(f"解析MinerU结果时出错: {parse_error}")
                    ocr_text = str(result)

                if not ocr_text.strip():
                    raise Exception("OCR识别返回空结果")

                self.document_processing.ocr_result = ocr_text
                self.document_processing.save()

                self.update_progress('ocr_processing', 40, "OCR识别完成")
                return ocr_text
            else:
                raise Exception(f"OCR API调用失败: {response.status_code} - {response.text}")

        except Exception as e:
            self.update_progress('failed', 0, f"OCR识别失败: {str(e)}", is_error=True)
            raise

    def process_with_llm(self, ocr_text):
        """调用LLM进行数据结构化处理"""
        try:
            self.update_progress('ai_processing', 50, "开始AI数据分析...")

            # 只调用ModelScope LLM，不使用规则引擎
            print("开始调用ModelScope LLM...")
            structured_data = self._call_real_llm(ocr_text)

            # 保存LLM原始结果用于调试
            self.document_processing.ai_result = structured_data
            self.document_processing.save()
            print(f"LLM结果已保存，包含 {len(structured_data.get('indicators', []))} 个指标")

            self.update_progress('ai_processing', 70, "AI数据分析完成")
            return structured_data

        except Exception as e:
            # 保存错误信息到数据库
            error_msg = f"LLM处理失败: {str(e)}"
            self.document_processing.error_message = error_msg
            self.document_processing.save()
            print(f"LLM处理失败: {error_msg}")

            self.update_progress('failed', 0, error_msg, is_error=True)
            raise

    def _call_real_llm(self, ocr_text):
        """调用本地LLM服务"""
        print(f"\n{'='*60}")
        print(f"[LLM] [LLM服务] 开始调用大语言模型")
        print(f"[文本] OCR文本长度: {len(ocr_text)} 字符")
        print(f"[文本] OCR文本前200字符: {ocr_text[:200]}...")

        # 构建prompt
        system_prompt, user_prompt = build_ocr_extract_prompt(ocr_text, self._get_existing_indicator_names())
        print(f"[信息] 构建完成Prompt，长度: {len(user_prompt)} 字符")

        # 准备本地LLM API请求
        llm_data = {
            "model": self.llm_model_name,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": 4000
        }

        # 准备请求头
        headers = {
            "Content-Type": "application/json"
        }

        # 只有在有API Key时才添加Authorization头
        if self.modelscope_api_key:
            headers["Authorization"] = f"Bearer {self.modelscope_api_key}"

        try:
            print(f"[API] LLM API配置信息:")
            print(f"   - API URL: {self.modelscope_api_url}")
            print(f"   - 模型名称: {self.llm_model_name}")
            print(f"   - 超时时间: {self.llm_timeout}秒")
            print(f"   - 最大令牌数: 4000")
            print(f"   - API Key: {'已设置' if self.modelscope_api_key else '未设置'}")

            # 根据API URL判断服务类型并使用正确的端点
            # 处理可能已包含完整路径的URL
            base_url = self.modelscope_api_url.rstrip('/')
            if '/chat/completions' not in base_url:
                # 如果URL不包含/chat/completions，添加完整路径
                api_url = f"{base_url}/v1/chat/completions"
            else:
                # 如果URL已包含/chat/completions，直接使用
                api_url = base_url

            if 'siliconflow' in self.modelscope_api_url.lower():
                print(f"[配置] 使用SiliconFlow API: {api_url}")
            else:
                print(f"[配置] 使用通用API: {api_url}")

            print(f"[发送] 请求数据大小: {len(json.dumps(llm_data))} 字符")

            # 记录请求开始时间
            import time
            start_time = time.time()

            print(f"[请求] 正在发送请求到LLM服务...")
            response = requests.post(
                api_url,
                json=llm_data,
                headers=headers,
                timeout=self.llm_timeout  # 使用动态超时设置
            )

            # 计算请求耗时
            end_time = time.time()
            request_duration = end_time - start_time

            print(f"⏱️  请求耗时: {request_duration:.2f} 秒")
            print(f"[响应] API响应状态码: {response.status_code}")
            print(f"[响应] API响应大小: {len(response.text)} 字符")
            print(f"[响应] API响应前500字符: {response.text[:500]}...")
  
            if response.status_code == 200:
                try:
                    result = response.json()
                    if 'choices' not in result or len(result['choices']) == 0:
                        print(f"[失败] API响应格式错误：缺少choices字段")
                        print(f"[数据] 完整响应: {result}")
                        raise Exception("API响应格式错误：缺少choices字段")

                    ai_result = result['choices'][0]['message']['content']
                    print(f"[成功] LLM API调用成功!")
                    print(f"[数据] 返回内容长度: {len(ai_result)} 字符")
                    print(f"[数据] 返回内容前500字符: {ai_result[:500]}...")

                    # 尝试解析JSON结果
                    print(f"API响应长度: {len(ai_result)} 字符")
                    print(f"API响应前500字符: {ai_result[:500]}")

                    # 清理响应，移除可能的代码块标记和thinking标签
                    cleaned_result = ai_result.strip()
                    
                    # 移除markdown代码块标记
                    if cleaned_result.startswith('```json'):
                        cleaned_result = cleaned_result[7:]
                    if cleaned_result.endswith('```'):
                        cleaned_result = cleaned_result[:-3]
                    
                    # 移除thinking标签和思考过程
                    import re
                    thinking_patterns = [
                        (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                        (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                        (r'</think>[\s\S]*?</think>', '', re.IGNORECASE),
                        (r'思考过程[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
                        (r'分析[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
                        (r'让我先分析[\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
                        (r'分析如下[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
                    ]
                    
                    for pattern, replacement, *flags in thinking_patterns:
                        flags = flags[0] if flags else 0
                        old_text = cleaned_result
                        cleaned_result = re.sub(pattern, replacement, cleaned_result, flags=flags)
                        if old_text != cleaned_result:
                            print(f"清理thinking标签/思考过程: 移除了 {len(old_text) - len(cleaned_result)} 个字符")
                    
                    cleaned_result = cleaned_result.strip()

                    print(f"清理后的响应: {cleaned_result[:100]}...")

                    try:
                        structured_data = json.loads(cleaned_result)
                        indicators_count = len(structured_data.get('indicators', []))
                        print(f"[成功] 成功解析JSON，包含 {indicators_count} 个指标")
                        return structured_data
                    except json.JSONDecodeError as e:
                        print(f"[失败] JSON解析失败: {str(e)}")
                        print(f"错误详情: {repr(e)}")

                        # 如果直接解析失败，尝试提取JSON部分
                        import re
                        # 手动寻找匹配的JSON对象
                        json_objects = self._extract_json_objects(cleaned_result)
                        print(f"找到 {len(json_objects)} 个JSON对象")

                        for i, json_str in enumerate(json_objects):
                            try:
                                structured_data = json.loads(json_str)
                                indicators_count = len(structured_data.get('indicators', []))
                                print(f"[成功] 第{i+1}个JSON解析成功，包含 {indicators_count} 个指标")
                                if indicators_count > 0:
                                    return structured_data
                            except json.JSONDecodeError as e2:
                                print(f"第{i+1}个JSON解析失败: {str(e2)}")
                                continue

                        print("所有JSON匹配都无法解析，保存原始响应用于调试")
                        # 保存原始响应到数据库，便于调试
                        self.document_processing.ai_result = {
                            'error': str(e),
                            'raw_response': ai_result[:500] + "..." if len(ai_result) > 500 else ai_result,
                            'cleaned_response': cleaned_result[:500] + "..." if len(cleaned_result) > 500 else cleaned_result
                        }
                        self.document_processing.save()

                        raise Exception(f"JSON解析失败，但已保存原始响应到数据库")

                except json.JSONDecodeError as e:
                    print(f"[失败] API响应JSON解析失败: {str(e)}")
                    raise Exception(f"API响应JSON解析失败: {str(e)}")
            else:
                error_msg = f"API调用失败: {response.status_code} - {response.text}"
                print(f"[失败] {error_msg}")
                raise Exception(error_msg)

        except requests.exceptions.Timeout:
            print(f"[失败] LLM API调用超时 (超过{self.llm_timeout}秒)")
            raise Exception("本地LLM API调用超时")
        except requests.exceptions.RequestException as e:
            print(f"[失败] LLM API网络错误: {str(e)}")
            raise Exception(f"本地LLM API网络错误: {str(e)}")
        except Exception as e:
            print(f"[失败] LLM API调用失败: {str(e)}")
            print(f"{'='*60}\n")
            raise Exception(f"本地LLM API调用失败: {str(e)}")

    def _get_indicator_type_from_name(self, indicator_name):
        """根据指标名称确定指标类型（新的11种分类）"""

        # 体格检查：基础体征、体格测量、视力等
        physical_exam_keywords = [
            '身高', '体重', '体重指数', '腰围', '臀围', '腰围臀围比值', '胸围',
            '血压', '收缩压', '舒张压', '体温', '脉搏', '心率', '呼吸频率',
            '视力', '裸眼视力', '矫正视力', '眼压', '眼底', '听力', '右眼视力', '左眼视力',
            '右眼眼压值', '左眼眼压值'
        ]

        # 血液常规：血常规相关指标
        blood_routine_keywords = [
            '白细胞', '红细胞', '血红蛋白', '血小板', '血细胞',
            '中性粒细胞', '淋巴细胞', '单核细胞', '嗜酸性', '嗜碱性',
            '红细胞比容', '红细胞分布宽度', '平均血红蛋白', '平均红细胞',
            '血小板压积', '血小板分布宽度', '平均血小板', '大血小板',
            '血沉', '血沉方程K值', '红细胞计数', '血红蛋白浓度', '平均红细胞容积',
            '中性粒细胞百分比', '中性粒细胞绝对计数', '淋巴细胞百分比', '淋巴细胞绝对计数',
            '单核细胞百分比', '单核细胞绝对计数', '嗜酸性粒细胞百分比', '嗜酸性粒细胞绝对计数',
            '嗜碱性粒细胞百分比', '嗜碱性粒细胞绝对计数', '血小板计数', '血小板分布宽度',
            '平均血小板容积', '血小板压积', '大血小板计数', '大血小板比例'
        ]

        # 生化检验：生化相关指标
        biochemistry_keywords = [
            '血糖', '葡萄糖', '空腹血糖', '餐后血糖', '糖化血红蛋白',
            '胆固醇', '甘油三酯', '高密度脂蛋白', '低密度脂蛋白',
            '总胆固醇', '高密度脂蛋白胆固醇', '低密度脂蛋白胆固醇',
            '载脂蛋白', '脂蛋白', '尿素', '尿素氮', '肌酐', '尿酸',
            '总胆红素', '直接胆红素', '间接胆红素', '血浆粘度', '维生素C',
            '载脂蛋白A1', '载脂蛋白B'
        ]

        # 肝功能：专门的肝功能指标
        liver_function_keywords = [
            '丙氨酸氨基转移酶', '天门冬氨酸氨基转移酶', 'γ-谷氨酰转移酶'
        ]

        # 肾功能：专门的肾功能指标
        kidney_function_keywords = [
            '尿肌酐', '尿微量白蛋白'
        ]

        # 甲状腺功能：甲状腺相关指标
        thyroid_function_keywords = [
            '甲状腺', 'TSH', 'T3', 'T4', '促甲状腺激素',
            '游离三碘甲状腺原氨酸', '游离甲状腺素', '甲状腺素',
            '三碘甲状腺原氨酸', '血清游离三碘甲状腺原氨酸'
        ]

        # 肿瘤标志物：肿瘤相关指标
        tumor_markers_keywords = [
            '癌胚抗原', '甲胎蛋白', '前列腺特异性抗原', '游离前列腺特异性抗原',
            '糖类抗原19-9', '糖链抗原19-9', '细胞角蛋白19片段抗原', 'CEA', 'AFP', 'CA',
            '肿瘤标志物'
        ]

        # 尿液检查：尿常规相关指标
        urine_exam_keywords = [
            '尿蛋白', '尿糖', '尿比重', '尿酸碱度', '尿潜血', '尿pH值',
            '尿白细胞', '尿红细胞', '尿酮体', '尿胆原', '尿胆红素', '尿胆素',
            '尿常规', '尿检', '尿液', '尿管型', '尿结晶', '上皮细胞', '尿钙'
        ]

        # 血液流变学：血液粘度相关指标
        blood_rheology_keywords = [
            '全血粘度', '全血还原粘度', '血浆粘度',
            '低切', '高切', '相对指数', '刚性指数', '变形指数', '聚集指数'
        ]

        # 眼科检查：眼科相关指标
        eye_exam_keywords = [
            '视力', '裸眼视力', '矫正视力', '眼压', '右眼视力', '左眼视力',
            '右眼眼压值', '左眼眼压值', '眼底', '听力'
        ]

        # 超声检查：超声相关检查指标（移除疾病诊断相关词汇，避免优先级冲突）
        ultrasound_keywords = [
            '超声', 'B超', '彩超', '多普勒', '胆管', '肝脏', '脾脏', '胰腺', '肾脏',
            '乳腺', '子宫', '附件', '卵巢', '膀胱', '前列腺', '精索',
            '心脏超声', '心脏彩超', '超声心动图', '血管超声', '颈动脉', '下肢血管',
            '胎儿', '孕周', '羊水', '胎盘', '脐带', '子宫内膜', '卵泡', '盆腔',
            '腹主动脉', '门静脉', '脾静脉', '肝静脉', '下腔静脉', '肾动脉',
            '胆囊壁', '胆囊结石', '胆结石', '脂肪肝', '肝硬化', '肝囊肿',
            '肾囊肿', '肾积水', '脾大', '脾大', '前列腺增生', '前列腺钙化',
            '乳腺结节', '卵巢囊肿', '盆腔积液',
            '瓣膜', '室壁', '心功能', '射血分数', '心包', '心肌', '冠脉', '冠状动脉'
        ]

        # 影像学检查：X光、CT、MRI、ECT等影像学检查指标
        imaging_keywords = [
            'CT', '计算机断层', '电子计算机断层', '螺旋CT', '多排CT',
            'MRI', '磁共振', '核磁共振', '功能磁共振', '扩散张量', '磁共振血管成像',
            'X光', 'X射线', 'X线', '胸片', '胸透', '腹平片', '骨骼片', '骨折',
            'PET-CT', 'SPECT', 'ECT', '骨扫描', 'PET', '正电子', '单光子',
            'DSA', '血管造影', '脑血管造影', '冠脉造影', '介入',
            '钼靶', '乳腺钼靶', '钡餐', '钡剂', '造影', '增强', '平扫',
            '肺结节', '肺大疱', '肺气肿', '肺炎', '肺纤维化', '肺结核', '肺癌',
            '脑梗死', '脑出血', '脑卒中', '脑萎缩', '脑白质', '脱髓鞘', '脑膜瘤',
            '肝血管瘤', '肝癌', '肝转移瘤', '脂肪肝', '肝硬化', '脾大', '胰腺炎',
            '肾癌', '肾结石', '肾积水', '肾囊肿', '肾血管', '肾动脉狭窄',
            '骨转移', '骨质疏松', '骨质增生', '椎间盘', '椎管狭窄', '脊柱侧弯',
            '冠状动脉', '冠脉狭窄', '心肌缺血', '心肌梗死', '心包积液', '主动脉瘤',
            '淋巴结', '纵隔', '胸腔积液', '腹水', '腹腔积液', '盆腔积液'
        ]

        # 病症诊断：各种疾病诊断
        diagnosis_keywords = [
            # 心血管疾病
            '高血压', '冠心病', '心绞痛', '心肌梗死', '心肌缺血', '心律失常', '心衰', '心力衰竭',
            '风湿性心脏病', '先天性心脏病', '肺心病', '心包炎', '心肌炎', '心内膜炎',
            
            # 脑血管疾病
            '脑梗死', '脑出血', '脑卒中', '中风', '偏头痛', '头痛', '眩晕', '头晕',
            '癫痫', '帕金森病', '阿尔茨海默病', '老年痴呆', '脑炎', '脑膜炎',
            
            # 呼吸系统疾病
            '肺炎', '支气管炎', '哮喘', '慢性阻塞性肺疾病', '肺气肿', '肺结核', '肺癌',
            '肺栓塞', '肺纤维化', '肺心病', '胸膜炎', '气胸', '呼吸道感染',
            
            # 消化系统疾病
            '胃炎', '胃溃疡', '十二指肠溃疡', '结肠炎', '克罗恩病', '溃疡性结肠炎',
            '肝炎', '肝硬化', '脂肪肝', '肝癌', '胆囊炎', '胆结石', '胆囊息肉', '胰腺炎', '胰腺癌',
            '食管炎', '食管癌', '胃癌', '结肠癌', '直肠癌', '肠梗阻', '阑尾炎',
            
            # 泌尿系统疾病
            '肾炎', '肾病综合征', '肾衰竭', '尿毒症', '肾结石', '肾囊肿', '肾癌',
            '膀胱炎', '膀胱癌', '前列腺炎', '前列腺增生', '前列腺癌', '尿路感染',
            
            # 内分泌代谢疾病
            '糖尿病', '甲状腺功能亢进', '甲亢', '甲状腺功能减退', '甲减', '甲状腺结节',
            '肥胖症', '高血脂', '高脂血症', '痛风', '骨质疏松', '代谢综合征',
            
            # 血液系统疾病
            '贫血', '白血病', '淋巴瘤', '血友病', '血小板减少症', '白细胞减少症',
            '再生障碍性贫血', '溶血性贫血', '地中海贫血', '骨髓增生异常综合征',
            
            # 风湿免疫疾病
            '类风湿关节炎', '系统性红斑狼疮', '强直性脊柱炎', '痛风', '骨关节炎',
            '风湿性关节炎', '干燥综合征', '硬皮病', '皮肌炎', '血管炎', '关节炎',
            
            # 神经系统疾病
            '抑郁症', '焦虑症', '失眠症', '神经衰弱', '三叉神经痛', '面神经麻痹',
            '坐骨神经痛', '颈椎病', '腰椎间盘突出', '腰椎管狭窄', '脊髓病变',
            
            # 妇科疾病
            '子宫肌瘤', '卵巢囊肿', '宫颈癌', '子宫内膜癌', '卵巢癌', '乳腺增生',
            '乳腺癌', '宫颈炎', '阴道炎', '盆腔炎', '多囊卵巢综合征', '月经不调',
            
            # 男性疾病
            '前列腺炎', '前列腺增生', '前列腺癌', '睾丸炎', '附睾炎', '阳痿', '早泄',
            
            # 五官科疾病
            '近视', '远视', '散光', '白内障', '青光眼', '结膜炎', '角膜炎', '鼻炎',
            '鼻窦炎', '咽炎', '扁桃体炎', '中耳炎', '耳鸣', '听力下降',
            
            # 皮肤病
            '湿疹', '银屑病', '牛皮癣', '皮炎', '荨麻疹', '痤疮', '带状疱疹',
            '皮肤过敏', '白癜风', '黄褐斑', '皮肤癌', '黑色素瘤',
            
            # 传染病
            '感冒', '流感', '病毒性肝炎', '肺结核', '艾滋病', '梅毒', '淋病', '尖锐湿疣',
            
            # 其他常见疾病
            '发热', '疼痛', '炎症', '感染', '过敏', '中毒', '外伤', '烧伤', '烫伤'
        ]

        # 症状描述：各种症状表现
        symptoms_keywords = [
            # 一般症状
            '发热', '寒战', '盗汗', '乏力', '疲倦', '食欲不振', '恶心', '呕吐', '体重下降',
            '体重增加', '消瘦', '肥胖', '水肿', '脱水', '口干', '口渴',
            
            # 头颈部症状
            '头痛', '头晕', '眩晕', '失眠', '嗜睡', '记忆力减退', '注意力不集中',
            '耳鸣', '听力下降', '耳痛', '耳闷', '鼻塞', '流涕', '鼻出血', '嗅觉减退',
            '咽痛', '咽异物感', '声音嘶哑', '咳嗽', '咳痰', '呼吸困难', '胸痛', '胸闷',
            '心悸', '心慌', '气短', '喘息',
            
            # 腹部症状
            '腹痛', '腹胀', '腹泻', '便秘', '恶心', '呕吐', '反酸', '烧心', '嗳气',
            '食欲减退', '厌食', '吞咽困难', '消化不良', '胃痛', '胃胀', '肝区痛',
            '腰痛', '腰酸', '背痛', '胁痛',
            
            # 泌尿生殖症状
            '尿频', '尿急', '尿痛', '尿不尽', '尿失禁', '血尿', '蛋白尿', '水肿',
            '排尿困难', '夜尿增多', '性欲减退', '阳痿', '早泄', '月经不调', '痛经',
            '白带异常', '阴道出血', '乳房胀痛', '乳房肿块',
            
            # 神经肌肉症状
            '肢体麻木', '肌肉无力', '肌肉萎缩', '肌肉震颤', '抽搐', '痉挛', '疼痛',
            '关节痛', '关节肿', '关节僵硬', '活动受限', '腰痛', '颈痛', '肩痛',
            '肘痛', '腕痛', '髋痛', '膝痛', '踝痛', '足痛',
            
            # 皮肤症状
            '皮疹', '瘙痒', '红斑', '丘疹', '水疱', '脓疱', '溃疡', '结痂',
            '脱屑', '色素沉着', '色素减退', '皮下出血', '紫癜', '黄疸', '苍白',
            '多汗', '无汗', '干燥', '脱发', '指甲改变',
            
            # 眼部症状
            '视力模糊', '视力下降', '眼痛', '眼干', '眼痒', '流泪', '畏光', '复视',
            '眼球突出', '眼睑肿胀', '结膜充血',
            
            # 精神心理症状
            '焦虑', '抑郁', '紧张', '恐惧', '易怒', '情绪低落', '兴趣减退', '睡眠障碍',
            '多梦', '噩梦', '健忘', '思维迟缓', '注意力不集中', '判断力减退',
            
            # 其他症状
            '出血', '淤血', '淤斑', '肿块', '包块', '结节', '增生', '肥大', '萎缩',
            '变形', '畸形', '瘢痕', '瘘管', '窦道'
        ]

        # 检查关键词映射（使用新的类型代码，与模型INDICATOR_TYPES一致）
        type_mapping = {
            'general_exam': physical_exam_keywords,
            'blood_routine': blood_routine_keywords,
            'biochemistry': biochemistry_keywords,
            'liver_function': liver_function_keywords,
            'kidney_function': kidney_function_keywords,
            'thyroid': thyroid_function_keywords,
            'tumor_markers': tumor_markers_keywords,
            'urine': urine_exam_keywords,
            'blood_rheology': blood_rheology_keywords,
            'coagulation': [],  # 凝血功能
            'stool': [],  # 粪便检查
            'pathology': diagnosis_keywords,  # 病症诊断归为病理检查
            'ultrasound': ultrasound_keywords,
            'X_ray': imaging_keywords,
            'CT_MRI': imaging_keywords,
            'endoscopy': [],  # 内镜检查
            'special_organs': eye_exam_keywords,  # 眼科等专科检查
            'other': symptoms_keywords,  # 症状描述归为其他检查
        }

        # 优先检查病症诊断和症状（最高优先级）
        for keyword in diagnosis_keywords:
            if keyword in indicator_name:
                return 'pathology'

        for keyword in symptoms_keywords:
            if keyword in indicator_name:
                return 'other'

        # 特殊处理一些复合词
        if '收缩压/舒张压' in indicator_name or '血压' in indicator_name:
            return 'general_exam'  # 血压归为一般检查
        if '体重指数' in indicator_name or 'BMI' in indicator_name:
            return 'general_exam'

        # 优先处理超声和影像学检查相关的特殊词汇（中等优先级）
        ultrasound_patterns = ['超声', 'B超', '彩超', '多普勒', '超声心动图']
        imaging_patterns = ['CT', 'MRI', 'X光', 'PET', 'SPECT', '造影', '断层', '磁共振']

        for pattern in ultrasound_patterns:
            if pattern in indicator_name:
                return 'ultrasound'

        for pattern in imaging_patterns:
            if pattern in indicator_name:
                # X光单独归类，CT/MRI合并归类
                if 'X光' in indicator_name or 'X线' in indicator_name or '胸片' in indicator_name:
                    return 'X_ray'
                return 'CT_MRI'

        # 处理器官相关的检查（最低优先级，只有在没有任何其他匹配时才使用）
        organ_keywords = [
            '肝脏', '脾脏', '胰腺', '乳腺', '子宫', '卵巢',
            '前列腺', '膀胱', '肾脏', '心脏', '血管', '颈动脉', '下肢血管'
            # 注意：移除了'胆囊'和'甲状腺'，因为它们经常与疾病诊断组合出现
        ]

        # 只有在指标名称中不包含任何疾病诊断、症状、检查方法关键词时，才根据器官名称推断
        is_organ_only = True
        all_high_priority_keywords = (
            diagnosis_keywords + symptoms_keywords + 
            ultrasound_patterns + imaging_patterns +
            physical_exam_keywords + blood_routine_keywords + 
            biochemistry_keywords + liver_function_keywords +
            kidney_function_keywords + thyroid_function_keywords +
            tumor_markers_keywords + urine_exam_keywords +
            blood_rheology_keywords + eye_exam_keywords
        )
        
        for keyword in all_high_priority_keywords:
            if keyword in indicator_name:
                is_organ_only = False
                break
        
        if is_organ_only:
            for organ in organ_keywords:
                if organ in indicator_name:
                    # 如果包含影像学关键词，则归为影像学，否则归为超声
                    for pattern in imaging_patterns:
                        if pattern in indicator_name:
                            # X光单独归类
                            if 'X光' in indicator_name or 'X线' in indicator_name or '胸片' in indicator_name:
                                return 'X_ray'
                            return 'CT_MRI'
                    return 'ultrasound'

        # 模糊匹配其他类型（最低优先级）
        for indicator_type, keywords in type_mapping.items():
            for keyword in keywords:
                if keyword in indicator_name:
                    return indicator_type

        return 'other'  # 默认归为其他检查

    def _extract_unit_from_value(self, measured_value, indicator_name):
        """从测量值中提取单位"""
        import re

        # 常见单位模式
        unit_patterns = {
            r'mmHg': 'mmHg',
            r'次/分|bpm|次': '次/分',
            r'mmol/L': 'mmol/L',
            r'kg': 'kg',
            r'cm': 'cm',
            r'°C': '°C',
            r'g/L': 'g/L',
            r'×10[^/]/L': '×10⁹/L',
            r'fl': 'fL',
            r'pg': 'pg',
            r'%': '%'
        }

        # 先从测量值中提取单位
        for pattern, unit in unit_patterns.items():
            if re.search(pattern, measured_value):
                return unit

        # 根据指标名称推断单位
        if '血压' in indicator_name:
            return 'mmHg'
        elif '心率' in indicator_name:
            return '次/分'
        elif '血糖' in indicator_name or '胆固醇' in indicator_name:
            return 'mmol/L'
        elif '体重' in indicator_name:
            return 'kg'
        elif '身高' in indicator_name:
            return 'cm'
        elif '体温' in indicator_name:
            return '°C'

        return ''

    def _clean_measured_value(self, measured_value, unit):
        """清理测量值，移除单位"""
        if unit:
            # 移除单位部分
            import re
            cleaned = re.sub(r'\s*' + re.escape(unit) + r'\s*$', '', str(measured_value))
            return cleaned.strip()
        return str(measured_value).strip()

    def _extract_json_objects(self, text):
        """从文本中提取完整的JSON对象"""
        import json

        json_objects = []
        start_idx = 0

        while start_idx < len(text):
            # 查找下一个 {
            start_pos = text.find('{', start_idx)
            if start_pos == -1:
                break

            # 寻找匹配的 }
            brace_count = 0
            end_pos = start_pos

            for i in range(start_pos, len(text)):
                if text[i] == '{':
                    brace_count += 1
                elif text[i] == '}':
                    brace_count -= 1

                if brace_count == 0:
                    end_pos = i
                    break

            # 如果找到匹配的括号
            if brace_count == 0:
                json_str = text[start_pos:end_pos + 1]
                # 验证这是否是有效的JSON
                try:
                    parsed = json.loads(json_str)
                    if 'indicators' in parsed:
                        json_objects.append(json_str)
                except json.JSONDecodeError:
                    pass
                start_idx = end_pos + 1
            else:
                start_idx = start_pos + 1

        return json_objects

    def _get_existing_indicator_names(self):
        """获取数据库中现有的标准指标名称"""
        return list(HealthIndicator.objects.values_list('indicator_name', flat=True).distinct().order_by('indicator_name'))

    def _build_llm_prompt(self, ocr_text):
        """构建LLM处理的prompt"""
        # 获取数据库中现有的标准指标名称
        existing_indicators = self._get_existing_indicator_names()
        existing_list = '\n'.join([f'  - {name}' for name in existing_indicators])

        return f"""
从体检报告OCR文本中提取所有健康指标，返回JSON格式。

文本内容：
{ocr_text}

**优先使用标准指标名称：**
{existing_list}

**提取范围：**
- **数值指标：** 
- **诊断结论：**
- **症状描述：** 
- **检查发现：** 
- **体征数据：** 

**特别注意：**
- 不仅要提取表格数据，还要识别段落中的健康信息
- 对于描述性检查，推断并提取结构化指标
- 确保不遗漏任何数值化的医学检查结果

**重要约束：**
1. **不要无中生有：** 只提取OCR文本中明确存在的指标数据或者病症描述
2. **参考值处理：** 如果报告中没有提供参考范围（normal_range），请留空或填null，不要编造
3. **异常判断：** 只有当报告中明确标注了异常（如↑↓箭头、异常字样、超出参考范围）时才标记"是"，否则留空或填null
4. **数据真实性：** 宁可留空，也不要编造报告中不存在的内容

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

请严格按照JSON格式返回，不要添加任何解释。切记不要编造报告中不存在的参考范围和异常状态。
"""

    def save_health_indicators(self, structured_data):
        """保存健康指标到数据库"""
        try:
            self.update_progress('saving_data', 80, "保存健康指标数据...")

            indicators = structured_data.get('indicators', [])
            if not indicators:
                print("[警告]  没有指标数据需要保存")
                return

            saved_count = 0
            skipped_count = 0

            for idx, indicator_data in enumerate(indicators):
                try:
                    # 跳过无效的indicator_data
                    if not isinstance(indicator_data, dict) or not indicator_data:
                        print(f"[警告]  跳过无效的指标数据 (索引{idx}): 不是字典或为空")
                        skipped_count += 1
                        continue

                    # 处理新的LLM响应格式，处理None/null值
                    indicator_name = indicator_data.get('indicator') or indicator_data.get('name') or ''
                    measured_value = indicator_data.get('measured_value') or indicator_data.get('value') or ''
                    normal_range = indicator_data.get('normal_range') or indicator_data.get('reference_range') or ''
                    is_abnormal = indicator_data.get('abnormal')

                    # 跳过没有指标名称的数据
                    if not indicator_name or indicator_name == 'null' or not str(indicator_name).strip():
                        print(f"[跳过] 无效指标 (索引{idx}): 缺少指标名称")
                        skipped_count += 1
                        continue

                    # 过滤个人信息字段
                    if is_personal_info_indicator(indicator_name):
                        print(f"[过滤] 个人信息字段 (索引{idx}): {indicator_name}")
                        filtered_count += 1
                        skipped_count += 1
                        continue

                    # 转换为字符串并清理
                    indicator_name = str(indicator_name).strip()
                    measured_value = str(measured_value).strip() if measured_value else ''
                    normal_range = str(normal_range).strip() if normal_range and normal_range != 'null' else ''

                    # 处理 null 值
                    if not normal_range or normal_range == 'null':
                        normal_range = ''

                    # 转换异常状态
                    if is_abnormal is None or is_abnormal == 'null':
                        # 如果 LLM 没有明确标注异常（报告中没有参考范围），则不判断状态
                        # 由于数据库字段不允许NULL且有default='normal'，这里留空会使用默认值
                        status = None  # 使用模型默认值
                    elif isinstance(is_abnormal, str):
                        if is_abnormal.lower() in ['是', 'yes', '异常', 'true', 'positive', '阳性']:
                            status = 'abnormal'
                        elif is_abnormal.lower() in ['否', 'no', '正常', 'false', 'negative', '阴性']:
                            status = 'normal'
                        else:
                            # 无法识别的字符串，不判断状态
                            status = None  # 使用模型默认值
                    elif isinstance(is_abnormal, bool):
                        status = 'abnormal' if is_abnormal else 'normal'
                    else:
                        status = None  # 使用模型默认值

                    # 确定指标类型
                    indicator_type = self._get_indicator_type_from_name(indicator_name)

                    # 确定单位
                    unit = self._extract_unit_from_value(measured_value, indicator_name)

                    # 清理测量值（移除单位）
                    clean_value = self._clean_measured_value(measured_value, unit)

                    # 创建健康指标
                    indicator = HealthIndicator.objects.create(
                        checkup=self.document_processing.health_checkup,
                        indicator_type=indicator_type,
                        indicator_name=indicator_name,
                        value=clean_value,
                        unit=unit,
                        reference_range=normal_range or '',  # 确保 None 转为空字符串
                        status=status or 'normal'  # 传入状态，如果为None则使用normal
                    )
                    saved_count += 1
                    status_display = status if status else 'normal(默认)'
                    print(f"已保存指标 {saved_count}: {indicator_name} = {clean_value} {unit} (参考范围:{normal_range or '空'}, 状态:{status_display})")

                    # 更新进度
                    progress = 80 + int((saved_count / len(indicators)) * 15)
                    self.update_progress('saving_data', progress, f"已保存 {saved_count}/{len(indicators)} 项指标")

                except Exception as e:
                    # 单个指标保存失败时，继续处理下一个
                    print(f"[错误] 保存指标失败 (索引{idx}): {str(e)}")
                    print(f"   指标数据: {indicator_data}")
                    skipped_count += 1
                    continue

            # 打印保存总结
            total_count = len(indicators)
            print(f"[完成] 成功保存 {saved_count}/{total_count} 个指标，跳过 {skipped_count} 个无效指标")
            if skipped_count > 0:
                print(f"   [提示] 被跳过的指标可能是由于缺少名称、数据格式错误或其他问题")

            self.update_progress('completed', 100, f"处理完成 - 保存了{saved_count}个指标")
            return saved_count

        except Exception as e:
            self.update_progress('failed', 0, f"保存数据失败: {str(e)}", is_error=True)
            raise

    def process_document(self, file_path):
        """执行完整的文档处理流程"""
        start_time = datetime.now()

        try:
            workflow_type = self.document_processing.workflow_type

            if workflow_type == 'vl_model':
                # 多模态大模型工作流
                return self._process_with_vl_workflow(file_path, start_time)
            else:
                # 传统OCR+LLM工作流
                return self._process_with_ocr_llm_workflow(file_path, start_time)

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _process_with_ocr_llm_workflow(self, file_path, start_time):
        """处理OCR+LLM工作流"""
        try:
            # 1. OCR识别
            self.update_progress('uploading', 10, "开始上传文件...")
            ocr_text = self.perform_ocr(file_path)

            # 2. AI处理
            structured_data = self.process_with_llm(ocr_text)

            # 3. 保存数据
            saved_count = self.save_health_indicators(structured_data)

            # 4. 计算处理时间
            end_time = datetime.now()
            processing_time = end_time - start_time
            self.document_processing.processing_time = processing_time
            self.document_processing.save()

            return {
                'success': True,
                'indicators_count': saved_count,
                'processing_time': str(processing_time)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _process_with_vl_workflow(self, file_path, start_time):
        """处理多模态大模型工作流"""
        try:
            # 使用多模态大模型服务
            vl_service = VisionLanguageModelService(self.document_processing)

            # 1. 多模态大模型处理
            self.update_progress('uploading', 10, "准备多模态分析...")
            structured_data = vl_service.process_with_vision_model(file_path)

            # 2. 保存数据
            saved_count = vl_service.save_vision_indicators(structured_data)

            # 3. 计算处理时间
            end_time = datetime.now()
            processing_time = end_time - start_time
            self.document_processing.processing_time = processing_time
            self.document_processing.save()

            return {
                'success': True,
                'indicators_count': saved_count,
                'processing_time': str(processing_time)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


def get_mineru_api_status():
    """检查MinerU API状态

    支持多种检查方式：
    1. 健康检查端点（推荐）
    2. API文档端点（兼容旧版本）
    3. 简单的TCP连接测试（最后手段）
    """
    try:
        # 从数据库获取配置
        mineru_api_url = SystemSettings.get_setting('mineru_api_url', 'http://localhost:8000').rstrip('/')
        timeout = int(SystemSettings.get_setting('ocr_healthcheck_timeout', '10'))

        # 尝试多个端点（按优先级）
        check_endpoints = SystemSettings.get_setting(
            'ocr_healthcheck_endpoints',
            '/health,/api/health,/docs,/'
        ).split(',')

        for endpoint in check_endpoints:
            endpoint = endpoint.strip()
            if not endpoint:
                continue

            check_url = f"{mineru_api_url}{endpoint}"
            print(f"[OCR健康检查] 尝试端点: {check_url}")

            try:
                response = requests.get(check_url, timeout=timeout)
                # 接受200或302（重定向，某些API会重定向到docs）
                if response.status_code in [200, 302]:
                    print(f"[OCR健康检查] ✓ 成功: {check_url} (状态码: {response.status_code})")
                    return True
                else:
                    print(f"[OCR健康检查] ✗ 失败: {check_url} (状态码: {response.status_code})")
            except requests.exceptions.Timeout:
                print(f"[OCR健康检查] ⏱ 超时: {check_url}")
                continue
            except Exception as e:
                print(f"[OCR健康检查] ✗ 错误: {check_url} - {str(e)}")
                continue

        # 所有端点都失败，返回False
        print(f"[OCR健康检查] 所有端点均不可用")
        return False

    except Exception as e:
        print(f"[OCR健康检查] 检查过程出错: {str(e)}")
        return False


def get_llm_api_status():
    """检查LLM API状态"""
    try:
        # 从数据库获取配置
        llm_api_url = SystemSettings.get_setting('llm_api_url', 'http://172.25.48.1:1234')
        llm_api_key = SystemSettings.get_setting('llm_api_key', '')
        timeout = int(SystemSettings.get_setting('llm_healthcheck_timeout', '10'))

        # 状态检查端点（可配置）
        healthcheck_endpoint = SystemSettings.get_setting(
            'llm_healthcheck_endpoint',
            '/v1/models'
        )
        check_url = f"{llm_api_url.rstrip('/')}/{healthcheck_endpoint.lstrip('/')}"

        headers = {}
        if llm_api_key:
            headers['Authorization'] = f"Bearer {llm_api_key}"

        print(f"[LLM健康检查] 检查URL: {check_url}")

        response = requests.get(check_url, headers=headers, timeout=timeout)

        # 可接受的状态码（可配置）
        acceptable_codes_str = SystemSettings.get_setting('llm_healthcheck_codes', '200,401')
        acceptable_codes = [int(code.strip()) for code in acceptable_codes_str.split(',')]

        print(f"[LLM健康检查] 响应状态码: {response.status_code}, 可接受: {acceptable_codes}")

        return response.status_code in acceptable_codes

    except Exception as e:
        print(f"[LLM健康检查] 检查失败: {str(e)}")
        return False


class VisionLanguageModelService:
    """多模态大模型服务类"""

    def __init__(self, document_processing):
        self.document_processing = document_processing
        # 获取多模态模型配置
        config = SystemSettings.get_vl_model_config()
        self.vl_provider = config['provider']
        self.vl_api_url = config['api_url']
        self.vl_api_key = config['api_key']
        self.vl_model_name = config['model_name']
        self.vl_timeout = int(config['timeout'])
        self.vl_max_tokens = int(config['max_tokens'])

    def update_progress(self, status, progress, message=None, is_error=False):
        """更新处理进度"""
        self.document_processing.status = status
        self.document_processing.progress = progress
        if message and is_error:
            self.document_processing.error_message = message
        elif message and not is_error:
            self.document_processing.error_message = None
        self.document_processing.save()

    def process_with_vision_model(self, file_path):
        """使用多模态大模型直接处理文档图片"""
        try:
            print(f"\n{'='*80}")
            print(f"[多模态] [多模态大模型] 开始处理文档")
            print(f"[数据] 文件路径: {file_path}")
            print(f"[时间] 处理开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            self.update_progress('ai_processing', 30, "开始多模态大模型分析...")

            # 判断文件类型
            file_ext = file_path.lower().split('.')[-1] if '.' in file_path.lower() else 'unknown'
            print(f"[信息] 检测到文件类型: {file_ext}")

            if file_path.lower().endswith('.pdf'):
                # PDF文件需要转换为图片
                print(f"[转换] PDF文件需要转换为图片...")
                try:
                    images = self._convert_pdf_to_images(file_path)
                    print(f"[成功] PDF转换成功，共{len(images)}页")
                    self.update_progress('ai_processing', 40, f"PDF转换成功，共{len(images)}页")
                except Exception as pdf_error:
                    # 如果PDF转换失败，建议用户使用其他工作流
                    print(f"[失败] PDF转换失败: {str(pdf_error)}")
                    error_msg = f"PDF文件处理失败：{str(pdf_error)}\n\n建议：\n1. 对于PDF文件，建议使用'MinerU Pipeline'或'MinerU VLM-Transformers'工作流\n2. 或者将PDF转换为图片后使用多模态工作流\n3. 或者安装poppler依赖以支持PDF转换"
                    self.update_progress('failed', 0, error_msg, is_error=True)
                    raise Exception(error_msg)
            else:
                # 图片文件直接处理
                images = [file_path]
                print(f"[图片]  检测到图片文件，直接处理")
                self.update_progress('ai_processing', 40, "检测到图片文件，直接处理")

            all_indicators = []
            total_images = len(images)
            print(f"[统计] 总共需要处理 {total_images} 页/张图片")

            for i, image_path in enumerate(images):
                progress = 40 + int((i / total_images) * 30)
                self.update_progress('ai_processing', progress, f"分析第 {i+1}/{total_images} 页...")

                # 处理单页图片
                indicators = self._process_single_image(image_path, i+1, total_images)
                all_indicators.extend(indicators)
                print(f"[进度] 第 {i+1} 页处理完成，提取到 {len(indicators)} 个指标")

            print(f"[信息] 所有页面处理完成，原始指标总数: {len(all_indicators)}")

            # 合并和去重指标
            print(f"[转换] 开始合并和去重指标...")
            unique_indicators = self._merge_indicators(all_indicators)
            print(f"[统计] 去重后指标总数: {len(unique_indicators)}")

            # 保存处理结果
            processing_result = {
                'indicators': unique_indicators,
                'total_pages': total_images,
                'file_type': 'PDF' if file_path.lower().endswith('.pdf') else 'Image',
                'processing_time': datetime.now().isoformat()
            }

            self.document_processing.vl_model_result = processing_result
            self.document_processing.save()

            print(f"[保存] 处理结果已保存到数据库")
            print(f"[时间] 处理完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"[完成] 多模态大模型处理完成!")
            print(f"{'='*80}\n")

            self.update_progress('ai_processing', 70, "多模态大模型分析完成")
            return {
                'indicators': unique_indicators,
                'total_pages': total_images
            }

        except Exception as e:
            print(f"[失败] 多模态大模型处理失败: {str(e)}")
            print(f"[时间] 失败时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*80}\n")
            self.update_progress('failed', 0, f"多模态大模型处理失败: {str(e)}", is_error=True)
            raise

    def _convert_pdf_to_images(self, pdf_path):
        """将PDF转换为图片"""
        try:
            from pdf2image import convert_from_path
            import tempfile
            import os
            
            # 尝试使用poppler路径（Windows常见路径）
            poppler_path = None
            if os.name == 'nt':  # Windows系统
                # 常见的poppler安装路径
                possible_paths = [
                    r"C:\Program Files\poppler-23\bin",
                    r"C:\Program Files\poppler-22\bin", 
                    r"C:\Program Files\poppler\bin",
                    r"C:\Program Files (x86)\poppler-23\bin",
                    r"C:\Program Files (x86)\poppler-22\bin",
                    r"C:\Program Files (x86)\poppler\bin",
                    r"C:\poppler\bin",
                    r"C:\tools\poppler\bin",
                ]
                
                for path in possible_paths:
                    if os.path.exists(path):
                        poppler_path = path
                        break
                
                # 如果没找到，尝试从环境变量获取
                if not poppler_path:
                    poppler_path = os.environ.get('POPPLER_BIN_PATH')
            
            # 转换PDF为图片
            try:
                if poppler_path:
                    images = convert_from_path(pdf_path, dpi=200, fmt='jpeg', poppler_path=poppler_path)
                else:
                    images = convert_from_path(pdf_path, dpi=200, fmt='jpeg')
            except Exception as e:
                if "poppler" in str(e).lower() or "Unable to get page count" in str(e):
                    # 如果是poppler相关错误，提供备选方案
                    raise Exception(f"PDF转图片失败：系统缺少poppler依赖。请安装poppler或使用其他工作流。\n详细错误: {str(e)}\n\n建议解决方案：\n1. 下载并安装poppler for Windows\n2. 设置POPPLER_BIN_PATH环境变量指向poppler/bin目录\n3. 或者使用'MinerU Pipeline'或'MinerU VLM-Transformers'工作流处理PDF文件")
                else:
                    raise e

            # 创建临时目录保存图片
            temp_dir = tempfile.mkdtemp()
            temp_image_paths = []
            
            for i, image in enumerate(images):
                temp_path = os.path.join(temp_dir, f"pdf_page_{i}.jpg")
                image.save(temp_path, 'JPEG')
                temp_image_paths.append(temp_path)

            return temp_image_paths
            
        except ImportError:
            raise Exception("需要安装pdf2image库: pip install pdf2image")
        except Exception as e:
            if "poppler" in str(e).lower():
                raise Exception(f"PDF转图片失败：系统缺少poppler依赖。请安装poppler或使用其他工作流处理PDF文件。\n详细错误: {str(e)}\n\n建议解决方案：\n1. 下载并安装poppler for Windows\n2. 设置POPPLER_BIN_PATH环境变量指向poppler/bin目录\n3. 或者使用'MinerU Pipeline'或'MinerU VLM-Transformers'工作流处理PDF文件")
            else:
                raise Exception(f"PDF转图片失败: {str(e)}")

    def _process_single_image(self, image_path, page_num, total_pages):
        """处理单页图片"""
        try:
            print(f"\n{'='*60}")
            print(f"[解析] [多模态大模型] 开始处理第 {page_num}/{total_pages} 页图片")
            print(f"[文件] 图片路径: {image_path}")

            # 构建针对医疗报告的prompt
            prompt = build_vision_model_prompt(page_num, total_pages)
            print(f"[文本] Prompt长度: {len(prompt)} 字符")
            print(f"[文本] Prompt前200字符: {prompt[:200]}...")

            # 根据提供商选择不同的API调用方式
            if self.vl_provider == 'gemini':
                # 使用 Gemini Vision API
                return self._call_gemini_vision_api(image_path, prompt)
            else:
                # 使用 OpenAI 兼容格式
                return self._call_openai_vision_api(image_path, prompt)

        except Exception as e:
            print(f"[失败] 处理第{page_num}页图片失败: {str(e)}")
            print(f"{'='*60}\n")
            return []

    def _call_gemini_vision_api(self, image_path, prompt):
        """调用 Gemini Vision API"""
        try:
            # 检查 Gemini API Key
            gemini_api_key = SystemSettings.get_setting('gemini_api_key')
            if not gemini_api_key:
                raise Exception("未配置Gemini API密钥，请在系统设置中配置")

            # 使用 Gemini 模型名称或配置的多模态模型名称
            model_name = SystemSettings.get_setting('gemini_model_name', self.vl_model_name)

            # 读取并编码图片
            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # 构建请求数据
            request_data = {
                "contents": [{
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_data
                            }
                        },
                        {
                            "text": prompt
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": self.vl_max_tokens
                }
            }

            # 构建API URL
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_api_key}"

            print(f"[API] Gemini API配置信息:")
            print(f"   - API URL: {api_url}")
            print(f"   - 模型名称: {model_name}")
            print(f"   - 超时时间: {self.vl_timeout}秒")
            print(f"[发送] 请求数据大小: {len(json.dumps(request_data))} 字符")

            # 记录请求开始时间
            import time
            start_time = time.time()

            print(f"[请求] 正在发送请求到 Gemini...")
            response = requests.post(
                api_url,
                json=request_data,
                headers={"Content-Type": "application/json"},
                timeout=self.vl_timeout
            )

            # 计算请求耗时
            end_time = time.time()
            request_duration = end_time - start_time
            print(f"⏱️  请求耗时: {request_duration:.2f} 秒")
            print(f"[响应] 响应状态码: {response.status_code}")
            print(f"[响应] 响应大小: {len(response.text)} 字符")
            print(f"[响应] 响应前500字符: {response.text[:500]}...")

            if response.status_code == 200:
                result = response.json()
                content = result['candidates'][0]['content']['parts'][0]['text']

                # 清理thinking标签和思考过程
                import re
                cleaned_content = content.strip()
                
                thinking_patterns = [
                    (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                    (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                    (r'</think>[\s\S]*?</think>', '', re.IGNORECASE),
                    (r'思考过程[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'让我先分析[\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析如下[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                ]
                
                for pattern, replacement, *flags in thinking_patterns:
                    flags = flags[0] if flags else 0
                    old_text = cleaned_content
                    cleaned_content = re.sub(pattern, replacement, cleaned_content, flags=flags)

                print(f"[成功] Gemini API调用成功!")
                print(f"[数据] 返回内容长度: {len(cleaned_content)} 字符")
                print(f"[数据] 返回内容前300字符: {cleaned_content[:300]}...")

                # 解析返回的JSON结果
                print(f"[配置] 开始解析JSON响应...")
                indicators = self._parse_vision_response(cleaned_content)

                print(f"[统计] 解析完成，提取到 {len(indicators)} 个指标")
                for i, indicator in enumerate(indicators):
                    print(f"   指标 {i+1}: {indicator.get('indicator', 'N/A')} = {indicator.get('measured_value', 'N/A')} ({indicator.get('abnormal', 'N/A')})")

                print(f"{'='*60}\n")
                return indicators
            else:
                print(f"[失败] Gemini API调用失败!")
                print(f"[失败] 错误详情: {response.text}")
                raise Exception(f"Gemini API调用失败: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"[失败] Gemini Vision API调用失败: {str(e)}")
            raise

    def _call_openai_vision_api(self, image_path, prompt):
        """调用 OpenAI 兼容格式的 Vision API"""
        try:
            # 准备请求数据
            request_data = {
                "model": self.vl_model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": VISION_MODEL_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": self._encode_image_to_base64(image_path),
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.1,
                "max_tokens": self.vl_max_tokens
            }

            # 准备请求头
            headers = {
                "Content-Type": "application/json"
            }

            if self.vl_api_key:
                headers["Authorization"] = f"Bearer {self.vl_api_key}"

            # API调用 - 处理可能已包含完整路径的URL
            base_url = self.vl_api_url.rstrip('/')
            if '/chat/completions' not in base_url:
                # 如果URL不包含/chat/completions，添加完整路径
                api_url = f"{base_url}/v1/chat/completions"
            else:
                # 如果URL已包含/chat/completions，直接使用
                api_url = base_url

            print(f"[API] OpenAI Vision API配置信息:")
            print(f"   - API URL: {api_url}")
            print(f"   - 模型名称: {self.vl_model_name}")
            print(f"   - 超时时间: {self.vl_timeout}秒")
            print(f"   - 最大令牌数: {self.vl_max_tokens}")
            print(f"   - API Key: {'已设置' if self.vl_api_key else '未设置'}")
            print(f"[发送] 请求数据大小: {len(json.dumps(request_data))} 字符")

            # 记录请求开始时间
            import time
            start_time = time.time()

            print(f"[请求] 正在发送请求到多模态大模型...")
            response = requests.post(
                api_url,
                json=request_data,
                headers=headers,
                timeout=self.vl_timeout
            )

            # 计算请求耗时
            end_time = time.time()
            request_duration = end_time - start_time
            print(f"⏱️  请求耗时: {request_duration:.2f} 秒")
            print(f"[响应] 响应状态码: {response.status_code}")
            print(f"[响应] 响应大小: {len(response.text)} 字符")
            print(f"[响应] 响应前500字符: {response.text[:500]}...")

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']

                # 清理thinking标签和思考过程
                import re
                cleaned_content = content.strip()
                
                thinking_patterns = [
                    (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                    (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                    (r'</think>[\s\S]*?</think>', '', re.IGNORECASE),
                    (r'思考过程[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'让我先分析[\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析如下[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                ]
                
                for pattern, replacement, *flags in thinking_patterns:
                    flags = flags[0] if flags else 0
                    old_text = cleaned_content
                    cleaned_content = re.sub(pattern, replacement, cleaned_content, flags=flags)

                print(f"[成功] API调用成功!")
                print(f"[数据] 返回内容长度: {len(cleaned_content)} 字符")
                print(f"[数据] 返回内容前300字符: {cleaned_content[:300]}...")

                # 解析返回的JSON结果
                print(f"[配置] 开始解析JSON响应...")
                indicators = self._parse_vision_response(cleaned_content)

                print(f"[统计] 解析完成，提取到 {len(indicators)} 个指标")
                for i, indicator in enumerate(indicators):
                    print(f"   指标 {i+1}: {indicator.get('indicator', 'N/A')} = {indicator.get('measured_value', 'N/A')} ({indicator.get('abnormal', 'N/A')})")

                print(f"{'='*60}\n")
                return indicators
            else:
                print(f"[失败] API调用失败!")
                print(f"[失败] 错误详情: {response.text}")
                raise Exception(f"多模态模型API调用失败: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"[失败] OpenAI Vision API调用失败: {str(e)}")
            raise

    def _encode_image_to_base64(self, image_path):
        """将图片编码为base64"""
        import base64

        # 读取图片并调整大小（如果太大）
        from PIL import Image
        import io

        with Image.open(image_path) as img:
            # 限制最大尺寸为1024x1024
            max_size = 1024
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            # 转换为RGB模式（如果不是）
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # 保存到内存
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)

            # 编码为base64
            image_data = buffer.read()
            base64_data = base64.b64encode(image_data).decode('utf-8')

        return f"data:image/jpeg;base64,{base64_data}"

    def _build_vision_prompt(self, page_num, total_pages):
        """构建视觉模型的prompt"""
        return f"""
分析第{page_num}/{total_pages}页医疗图片，提取所有健康相关信息。

**任务要求：**
1. **体检报告：** 识别并提取所有医学检查结果、指标数据、诊断结论
2. **症状照片：** 详细描述可见的症状表现、体征特征

**提取重点：**
- **数值指标：
- **诊断结论：
- **症状描述：
- **检查发现：
- **体征数据：

**重要约束：**
1. **不要无中生有：** 只提取图片中明确可见或明确写明的指标数据或者病症描述
2. **参考值处理：** 如果图片中没有提供参考范围（normal_range），请留空或填null，不要编造
3. **异常判断：** 只有当图片中明确标注了异常（如↑↓箭头、异常字样、超出参考范围、阳性）时才标记"是"，否则留空或填null
4. **数据真实性：** 宁可留空，也不要编造图片中不存在的内容
5. **清晰度要求：** 如果文字模糊不清无法准确识别，可以在指标名添加备注，如xx指标(不清)

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
- 诊断"高血压2级" → {{"indicator": "高血压", "measured_value": "2级", "normal_range": null, "abnormal": "是"}}
- 症状"皮肤红疹" → {{"indicator": "皮肤皮疹", "measured_value": "红色丘疹", "normal_range": null, "abnormal": "是"}}
- 红细胞计数"4.5" → {{"indicator": "红细胞计数", "measured_value": "4.5", "normal_range": null, "abnormal": null}}

请严格按照JSON格式返回，不要添加任何解释文字。切记不要编造图片中不存在的参考范围和异常状态。
"""

    def _extract_json_from_text(self, text):
        """智能提取和清理JSON内容"""
        print(f"[配置] 开始智能JSON提取和清理...")
        print(f"[数据] 原始文本长度: {len(text)} 字符")
        print(f"[数据] 原始文本前300字符: {text[:300]}...")

        # 方法1: 尝试直接解析（如果文本本身就是纯净的JSON）
        try:
            result = json.loads(text.strip())
            print(f"[成功] 方法1成功: 直接解析JSON")
            return result
        except json.JSONDecodeError:
            print(f"[失败] 方法1失败: 无法直接解析JSON")

        # 方法2: 清理常见的代码块标记和thinking标签
        cleaned_patterns = [
            # 移除thinking标签和思考过程
            (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
            (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
            (r'</think>[\s\S]*?</think>', '', re.IGNORECASE),
            (r'思考过程[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
            (r'分析[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
            (r'让我先分析[\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
            (r'分析如下[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
            # 移除代码块标记
            (r'```json\s*', ''),
            (r'```\s*', ''),
            # 移除可能的前导文字说明
            (r'^.*?(?=\s*\{)', '', re.DOTALL),
            # 移除可能的尾部文字说明
            (r'\}[^}]*$', '}'),
            # 移除常见的前缀文字
            (r'^(?:以下是|Here is|The result is|输出|返回|Result)[:：\s]*', '', re.IGNORECASE),
        ]

        cleaned_text = text
        for pattern, replacement, *flags in cleaned_patterns:
            flags = flags[0] if flags else 0
            old_text = cleaned_text
            cleaned_text = re.sub(pattern, replacement, cleaned_text, flags=flags)
            if old_text != cleaned_text:
                print(f"[清理] 清理模式应用: 移除了 {len(old_text) - len(cleaned_text)} 个字符")

        cleaned_text = cleaned_text.strip()
        print(f"[清理] 基础清理后长度: {len(cleaned_text)} 字符")

        # 尝试解析清理后的文本
        try:
            result = json.loads(cleaned_text)
            print(f"[成功] 方法2成功: 基础清理后解析成功")
            return result
        except json.JSONDecodeError as e:
            print(f"[失败] 方法2失败: {str(e)}")

        # 方法3: 使用正则表达式提取JSON对象
        print(f"[解析] 方法3: 使用正则表达式提取JSON对象...")

        # 多种JSON提取模式
        json_patterns = [
            # 标准JSON对象（支持嵌套）
            (r'\{(?:[^{}]|(?R))*\}', re.DOTALL),
            # 更宽松的JSON匹配
            (r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', re.DOTALL),
            # 简化匹配（寻找包含"indicators"的对象）
            (r'\{[^}]*"indicators"[^}]*\}', re.DOTALL),
        ]

        for i, (pattern, flags) in enumerate(json_patterns, 1):
            try:
                # 使用更强大的递归正则表达式
                matches = self._extract_json_objects_recursive(text)
                print(f"[解析] 模式{i}: 找到 {len(matches)} 个潜在JSON对象")

                for j, json_str in enumerate(matches):
                    print(f"   尝试对象 {j+1}: 长度 {len(json_str)} 字符")
                    try:
                        result = json.loads(json_str)
                        if 'indicators' in result:
                            print(f"[成功] 方法3.{i}.{j+1}成功: 找到包含indicators的JSON对象")
                            return result
                    except json.JSONDecodeError as e:
                        print(f"   对象 {j+1} 解析失败: {str(e)[:100]}...")
                        continue

            except Exception as e:
                print(f"[失败] 方法3.{i}失败: {str(e)}")
                continue

        # 方法4: 括号匹配法
        print(f"[解析] 方法4: 括号匹配法...")
        json_candidates = self._extract_by_bracket_matching(text)
        for i, candidate in enumerate(json_candidates):
            try:
                result = json.loads(candidate)
                if 'indicators' in result:
                    print(f"[成功] 方法4.{i+1}成功: 括号匹配找到有效JSON")
                    return result
            except json.JSONDecodeError:
                continue

        # 方法5: 最后尝试 - 修复常见的JSON错误
        print(f"[配置] 方法5: 尝试修复常见JSON错误...")
        try:
            repaired_json = self._repair_json_syntax(cleaned_text)
            if repaired_json:
                result = json.loads(repaired_json)
                print(f"[成功] 方法5成功: JSON修复后解析成功")
                return result
        except Exception as e:
            print(f"[失败] 方法5失败: {str(e)}")

        print(f"[失败] 所有JSON提取方法都失败了")
        return None

    def _extract_json_objects_recursive(self, text):
        """递归提取所有JSON对象"""
        json_objects = []
        start_idx = 0
        bracket_count = 0
        in_string = False
        escape_char = False
        start_pos = -1

        for i, char in enumerate(text):
            if escape_char:
                escape_char = False
                continue

            if char == '\\':
                escape_char = True
                continue

            if char == '"' and not escape_char:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                if bracket_count == 0:
                    start_pos = i
                bracket_count += 1
            elif char == '}':
                bracket_count -= 1
                if bracket_count == 0 and start_pos != -1:
                    json_str = text[start_pos:i+1]
                    json_objects.append(json_str)
                    start_pos = -1

        return json_objects

    def _extract_by_bracket_matching(self, text):
        """使用括号匹配提取JSON对象"""
        candidates = []
        for i, char in enumerate(text):
            if char == '{':
                bracket_count = 0
                in_string = False
                escape_char = False

                for j in range(i, len(text)):
                    char_j = text[j]

                    if escape_char:
                        escape_char = False
                        continue

                    if char_j == '\\':
                        escape_char = True
                        continue

                    if char_j == '"' and not escape_char:
                        in_string = not in_string
                        continue

                    if in_string:
                        continue

                    if char_j == '{':
                        bracket_count += 1
                    elif char_j == '}':
                        bracket_count -= 1
                        if bracket_count == 0:
                            candidates.append(text[i:j+1])
                            break

        return candidates

    def _repair_json_syntax(self, text):
        """尝试修复常见的JSON语法错误"""
        if not text:
            return None

        # 基础清理
        repaired = text.strip()

        # 移除多余的逗号
        repaired = re.sub(r',(\s*[}\]])', r'\1', repaired)

        # 确保字符串被正确引用
        repaired = re.sub(r'(\w+):', r'"\1":', repaired)

        # 修复常见的引号问题
        repaired = re.sub(r"'([^']*)'", r'"\1"', repaired)

        return repaired if repaired != text else None

    def _parse_vision_response(self, content):
        """解析视觉模型的响应"""
        try:
            print(f"[配置] 开始解析视觉模型响应...")

            # 使用智能JSON提取功能
            result = self._extract_json_from_text(content)

            if not result:
                print(f"[失败] 无法从响应中提取有效的JSON")
                print(f"[数据] 原始响应内容: {content}")
                return []

            indicators = result.get('indicators', [])

            if not indicators:
                print(f"[警告]  JSON解析成功但未找到indicators字段")
                print(f"[数据] JSON内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
                return []

            # 验证和清理指标数据
            cleaned_indicators = []
            filtered_count = 0

            for indicator in indicators:
                try:
                    # 跳过非字典或None的indicator
                    if not isinstance(indicator, dict) or not indicator:
                        continue

                    # 提取indicator字段，处理None/null
                    indicator_name = indicator.get('indicator') or indicator.get('name')
                    if not indicator_name or indicator_name == 'null':
                        # 跳过没有指标名称的数据
                        continue

                    # 过滤个人信息字段
                    if is_personal_info_indicator(indicator_name):
                        filtered_count += 1
                        continue

                    # 安全提取其他字段，将None/null转换为空字符串
                    measured_value = indicator.get('measured_value') or indicator.get('value') or ''
                    normal_range = indicator.get('normal_range') or indicator.get('reference_range') or ''
                    abnormal = indicator.get('abnormal') or '否'

                    # 清理字符串'null'
                    if measured_value == 'null':
                        measured_value = ''
                    if normal_range == 'null':
                        normal_range = ''
                    if abnormal == 'null':
                        abnormal = '否'

                    # 确保所有值都是字符串
                    cleaned_indicators.append({
                        'indicator': str(indicator_name).strip() if indicator_name else '',
                        'measured_value': str(measured_value).strip() if measured_value else '',
                        'normal_range': str(normal_range).strip() if normal_range else '',
                        'abnormal': str(abnormal).strip() if abnormal else '否'
                    })
                except Exception as e:
                    # 跳过有问题的单个指标，继续处理其他指标
                    print(f"[警告]  跳过无效指标数据: {indicator}, 错误: {str(e)}")
                    continue

            if filtered_count > 0:
                print(f"[过滤] 已过滤 {filtered_count} 个个人信息字段（姓名、性别、年龄等）")

            print(f"[成功] 视觉响应解析成功，提取到 {len(cleaned_indicators)} 个有效指标")
            return cleaned_indicators

        except Exception as e:
            print(f"[失败] 视觉模型响应解析失败: {str(e)}")
            print(f"[数据] 原始响应前500字符: {content[:500]}...")
            return []

    def _merge_indicators(self, all_indicators):
        """合并和去重指标"""
        # 使用指标名称作为键进行去重
        indicator_map = {}

        for indicator in all_indicators:
            name = indicator.get('indicator', '').strip()
            if name:
                if name in indicator_map:
                    # 如果指标已存在，选择更完整的版本
                    existing = indicator_map[name]
                    # 优先选择有测量值的版本
                    if indicator.get('measured_value') and not existing.get('measured_value'):
                        indicator_map[name] = indicator
                    # 如果都有测量值，优先选择异常的版本
                    elif indicator.get('abnormal') == '是' and existing.get('abnormal') != '是':
                        indicator_map[name] = indicator
                else:
                    indicator_map[name] = indicator

        # 返回去重后的指标列表
        return list(indicator_map.values())

    def save_vision_indicators(self, structured_data):
        """保存多模态模型提取的健康指标到数据库"""
        try:
            self.update_progress('saving_data', 80, "保存健康指标数据...")

            indicators = structured_data.get('indicators', [])
            if not indicators:
                print("[警告]  没有指标数据需要保存")
                return

            saved_count = 0
            skipped_count = 0

            for idx, indicator_data in enumerate(indicators):
                try:
                    # 跳过无效的indicator_data
                    if not isinstance(indicator_data, dict) or not indicator_data:
                        print(f"[警告]  跳过无效的指标数据 (索引{idx}): 不是字典或为空")
                        skipped_count += 1
                        continue

                    # 处理新的LLM响应格式，处理None/null值
                    indicator_name = indicator_data.get('indicator') or indicator_data.get('name') or ''
                    measured_value = indicator_data.get('measured_value') or indicator_data.get('value') or ''
                    normal_range = indicator_data.get('normal_range') or indicator_data.get('reference_range') or ''
                    is_abnormal = indicator_data.get('abnormal')

                    # 跳过没有指标名称的数据
                    if not indicator_name or indicator_name == 'null' or not str(indicator_name).strip():
                        print(f"[警告]  跳过无效指标 (索引{idx}): 缺少指标名称")
                        skipped_count += 1
                        continue

                    # 转换为字符串并清理
                    indicator_name = str(indicator_name).strip()
                    measured_value = str(measured_value).strip() if measured_value else ''
                    normal_range = str(normal_range).strip() if normal_range and normal_range != 'null' else ''

                    # 处理 null 值
                    if not normal_range or normal_range == 'null':
                        normal_range = ''

                    # 转换异常状态
                    if is_abnormal is None or is_abnormal == 'null':
                        # 如果 LLM 没有明确标注异常（报告中没有参考范围），则不判断状态
                        # 由于数据库字段不允许NULL且有default='normal'，这里留空会使用默认值
                        status = None  # 使用模型默认值
                    elif isinstance(is_abnormal, str):
                        if is_abnormal.lower() in ['是', 'yes', '异常', 'true', 'positive', '阳性']:
                            status = 'abnormal'
                        elif is_abnormal.lower() in ['否', 'no', '正常', 'false', 'negative', '阴性']:
                            status = 'normal'
                        else:
                            # 无法识别的字符串，不判断状态
                            status = None  # 使用模型默认值
                    elif isinstance(is_abnormal, bool):
                        status = 'abnormal' if is_abnormal else 'normal'
                    else:
                        status = None  # 使用模型默认值

                    # 确定指标类型
                    service = DocumentProcessingService(self.document_processing)
                    indicator_type = service._get_indicator_type_from_name(indicator_name)

                    # 确定单位
                    unit = service._extract_unit_from_value(measured_value, indicator_name)

                    # 清理测量值
                    clean_value = service._clean_measured_value(measured_value, unit)

                    # 创建健康指标
                    indicator = HealthIndicator.objects.create(
                        checkup=self.document_processing.health_checkup,
                        indicator_type=indicator_type,
                        indicator_name=indicator_name,
                        value=clean_value,
                        unit=unit,
                        reference_range=normal_range or '',  # 确保 None 转为空字符串
                        status=status or 'normal'  # 传入状态，如果为None则使用normal
                    )
                    saved_count += 1
                    status_display = status if status else 'normal(默认)'
                    print(f"已保存指标 {saved_count}: {indicator_name} = {clean_value} {unit} (参考范围:{normal_range or '空'}, 状态:{status_display})")

                    # 更新进度
                    progress = 80 + int((saved_count / len(indicators)) * 15)
                    self.update_progress('saving_data', progress, f"已保存 {saved_count}/{len(indicators)} 项指标")

                except Exception as e:
                    # 单个指标保存失败时，继续处理下一个
                    print(f"[错误] 保存指标失败 (索引{idx}): {str(e)}")
                    print(f"   指标数据: {indicator_data}")
                    skipped_count += 1
                    continue

            # 打印保存总结
            total_count = len(indicators)
            print(f"[完成] 成功保存 {saved_count}/{total_count} 个指标，跳过 {skipped_count} 个无效指标")
            if skipped_count > 0:
                print(f"   [提示] 被跳过的指标可能是由于缺少名称、数据格式错误或其他问题")

            self.update_progress('completed', 100, f"处理完成 - 保存了{saved_count}个指标")
            return saved_count

        except Exception as e:
            self.update_progress('failed', 0, f"保存数据失败: {str(e)}", is_error=True)
            raise


def get_vision_model_api_status():
    """检查多模态大模型API状态"""
    try:
        config = SystemSettings.get_vl_model_config()
        if not config['api_url']:
            return False

        timeout = int(SystemSettings.get_setting('vl_model_healthcheck_timeout', '10'))

        # 状态检查端点（可配置）
        healthcheck_endpoint = SystemSettings.get_setting(
            'vl_model_healthcheck_endpoint',
            '/v1/models'
        )
        check_url = f"{config['api_url'].rstrip('/')}/{healthcheck_endpoint.lstrip('/')}"

        headers = {}
        if config.get('api_key'):
            headers['Authorization'] = f"Bearer {config['api_key']}"

        print(f"[VLM健康检查] 检查URL: {check_url}")

        response = requests.get(check_url, headers=headers, timeout=timeout)

        # 可接受的状态码（可配置）
        acceptable_codes_str = SystemSettings.get_setting('vl_model_healthcheck_codes', '200,401')
        acceptable_codes = [int(code.strip()) for code in acceptable_codes_str.split(',')]

        print(f"[VLM健康检查] 响应状态码: {response.status_code}, 可接受: {acceptable_codes}")

        return response.status_code in acceptable_codes

    except Exception as e:
        print(f"[VLM健康检查] 检查失败: {str(e)}")
        return False


class AIService:
    """AI服务类，用于生成健康建议"""

    def __init__(self):
        # 获取LLM配置
        self.llm_api_url = SystemSettings.get_setting('llm_api_url', 'http://172.25.48.1:1234')
        self.llm_api_key = SystemSettings.get_setting('llm_api_key', '')
        self.llm_model_name = SystemSettings.get_setting('llm_model_name', 'qwen3-4b-instruct')
        self.llm_timeout = int(SystemSettings.get_setting('llm_timeout', '600'))

    def get_health_advice(self, indicators):
        """根据健康指标生成AI建议"""
        try:
            # 格式化指标数据
            indicators_text = ""
            abnormal_indicators = []

            for indicator in indicators:
                status = "异常" if indicator.status == 'abnormal' else "正常"
                indicators_text += f"- {indicator.indicator_name}: {indicator.value} {indicator.unit} (参考范围: {indicator.reference_range}) - {status}\n"

                if indicator.status == 'abnormal':
                    abnormal_indicators.append(indicator.indicator_name)

            # 根据异常指标调整建议重点
            if abnormal_indicators:
                focus_text = f"特别关注以下异常指标: {', '.join(abnormal_indicators)}"
            else:
                focus_text = "所有指标都在正常范围内"

            # 构建prompt
            system_prompt, user_prompt = build_health_advice_prompt(indicators_text, focus_text)

            # 准备请求数据
            llm_data = {
                "model": self.llm_model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            }

            # 准备请求头
            headers = {
                "Content-Type": "application/json"
            }

            if self.llm_api_key:
                headers["Authorization"] = f"Bearer {self.llm_api_key}"

            # API调用 - 处理可能已包含完整路径的URL
            base_url = self.llm_api_url.rstrip('/')
            if '/chat/completions' not in base_url:
                # 如果URL不包含/chat/completions，添加完整路径
                api_url = f"{base_url}/v1/chat/completions"
            else:
                # 如果URL已包含/chat/completions，直接使用
                api_url = base_url
            response = requests.post(
                api_url,
                json=llm_data,
                headers=headers,
                timeout=self.llm_timeout
            )

            if response.status_code == 200:
                result = response.json()
                advice = result['choices'][0]['message']['content']
                
                # 清理thinking标签和思考过程
                import re
                cleaned_advice = advice.strip()
                
                thinking_patterns = [
                    (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                    (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                    (r'</think>[\s\S]*?</think>', '', re.IGNORECASE),
                    (r'思考过程[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'让我先分析[\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析如下[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                ]
                
                for pattern, replacement, *flags in thinking_patterns:
                    flags = flags[0] if flags else 0
                    old_text = cleaned_advice
                    cleaned_advice = re.sub(pattern, replacement, cleaned_advice, flags=flags)
                
                return cleaned_advice.strip()
            else:
                raise Exception(f"AI建议生成失败: {response.status_code} - {response.text}")

        except Exception as e:
            return f"很抱歉，AI建议生成失败: {str(e)}"


def call_llm_for_integration(system_prompt, user_prompt, timeout=120):
    """
    调用LLM API进行数据整合分析

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        timeout: 超时时间（秒）

    Returns:
        str: LLM的响应文本
    """
    import requests
    import json
    from .models import SystemSettings

    # 获取LLM配置
    llm_api_url = SystemSettings.get_setting('llm_api_url', 'http://172.25.48.1:1234')
    llm_api_key = SystemSettings.get_setting('llm_api_key', '')
    llm_model_name = SystemSettings.get_setting('llm_model_name', 'MiniMaxAI/MiniMax-M2')

    print(f"\n{'='*80}")
    print(f"[数据整合 LLM调用] 开始")
    print(f"[数据整合 LLM调用] API URL: {llm_api_url}")
    print(f"[数据整合 LLM调用] 模型: {llm_model_name}")
    print(f"[数据整合 LLM调用] API Key: {'已设置' if llm_api_key else '未设置'}")
    print(f"[数据整合 LLM调用] 超时: {timeout}秒")

    # 构建请求数据
    llm_data = {
        "model": llm_model_name,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": 8000
    }

    # 准备请求头
    headers = {
        "Content-Type": "application/json"
    }

    # 只有在有API Key时才添加Authorization头
    if llm_api_key:
        headers["Authorization"] = f"Bearer {llm_api_key}"

    try:
        # 根据API URL判断服务类型并使用正确的端点
        # 处理可能已包含完整路径的URL
        base_url = llm_api_url.rstrip('/')
        if '/chat/completions' not in base_url:
            # 如果URL不包含/chat/completions，添加完整路径
            api_url = f"{base_url}/v1/chat/completions"
        else:
            # 如果URL已包含/chat/completions，直接使用
            api_url = base_url

        print(f"[数据整合 LLM调用] 完整API地址: {api_url}")
        print(f"[数据整合 LLM调用] User Prompt长度: {len(user_prompt)} 字符")
        print(f"[数据整合 LLM调用] 请求体大小: {len(json.dumps(llm_data))} 字符")
        print(f"[数据整合 LLM调用] 正在发送请求...")

        # 发送请求
        import time
        start_time = time.time()

        response = requests.post(
            api_url,
            json=llm_data,
            headers=headers,
            timeout=timeout
        )

        end_time = time.time()
        duration = end_time - start_time

        print(f"[数据整合 LLM调用] 请求完成")
        print(f"[数据整合 LLM调用] 状态码: {response.status_code}")
        print(f"[数据整合 LLM调用] 响应时间: {duration:.2f}秒")
        print(f"[数据整合 LLM调用] 响应大小: {len(response.text)} 字符")

        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # 清理thinking标签和思考过程
            import re
            cleaned_content = content.strip()
            
            thinking_patterns = [
                (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                (r'</think>[\s\S]*?</think>', '', re.IGNORECASE),
                (r'思考过程[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                (r'分析[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                (r'让我先分析[\s\S]*?(?=\n)', '', re.IGNORECASE),
                (r'分析如下[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
            ]
            
            for pattern, replacement, *flags in thinking_patterns:
                flags = flags[0] if flags else 0
                old_text = cleaned_content
                cleaned_content = re.sub(pattern, replacement, cleaned_content, flags=flags)
            
            print(f"[数据整合 LLM调用] [OK] 成功获取响应")
            print(f"[数据整合 LLM调用] 响应内容前500字符:")
            print(f"{cleaned_content[:500]}")
            print(f"[数据整合 LLM调用] 响应内容后500字符:")
            print(f"{cleaned_content[-500:]}")
            return cleaned_content
        else:
            print(f"[数据整合 LLM调用] [FAIL] API返回错误")
            print(f"[数据整合 LLM调用] 错误详情: {response.text}")
            raise Exception(f"LLM API返回错误: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        print(f"[数据整合 LLM调用] [FAIL] 请求超时（{timeout}秒）")
        raise Exception(f"LLM API请求超时（{timeout}秒）")
    except Exception as e:
        print(f"[数据整合 LLM调用] [FAIL] 调用失败: {str(e)}")
        raise Exception(f"调用LLM API失败: {str(e)}")


def call_gemini_api(prompt, system_message=None, timeout=300):
    """
    调用 Google Gemini API

    Args:
        prompt: 发送给Gemini的提示词
        system_message: 系统消息（可选）
        timeout: 超时时间（秒）

    Returns:
        str: Gemini的响应文本
    """
    import requests
    import json
    from .models import SystemSettings

    # 获取Gemini配置
    gemini_config = SystemSettings.get_gemini_config()
    api_key = gemini_config['api_key']
    model_name = gemini_config['model_name']

    if not api_key:
        raise Exception("Gemini API密钥未配置，请在系统设置中配置")

    print(f"\n{'='*80}")
    print(f"[Gemini API调用] 开始")
    print(f"[Gemini API调用] 模型: {model_name}")
    print(f"[Gemini API调用] API Key: {'已设置' if api_key else '未设置'}")
    print(f"[Gemini API调用] 超时: {timeout}秒")

    # 构建请求内容
    parts = []

    # 添加系统消息（如果有）
    if system_message:
        parts.append({"text": system_message})

    # 添加用户提示
    parts.append({"text": prompt})

    # Gemini API 请求格式
    gemini_data = {
        "contents": [{
            "parts": parts
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192
        }
    }

    # 构建API URL
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    print(f"[Gemini API调用] 请求URL: {api_url}")
    print(f"[Gemini API调用] Prompt长度: {len(prompt)} 字符")

    try:
        import time
        start_time = time.time()

        response = requests.post(
            api_url,
            json=gemini_data,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )

        end_time = time.time()
        duration = end_time - start_time

        print(f"[Gemini API调用] 请求完成")
        print(f"[Gemini API调用] 状态码: {response.status_code}")
        print(f"[Gemini API调用] 响应时间: {duration:.2f}秒")

        if response.status_code == 200:
            result = response.json()

            # 检查是否有候选结果
            if 'candidates' in result and len(result['candidates']) > 0:
                content = result['candidates'][0]['content']['parts'][0]['text']
                
                # 清理thinking标签和思考过程
                import re
                cleaned_content = content.strip()
                
                thinking_patterns = [
                    (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                    (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                    (r'</think>[\s\S]*?</think>', '', re.IGNORECASE),
                    (r'思考过程[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'让我先分析[\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析如下[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                ]
                
                for pattern, replacement, *flags in thinking_patterns:
                    flags = flags[0] if flags else 0
                    old_text = cleaned_content
                    cleaned_content = re.sub(pattern, replacement, cleaned_content, flags=flags)
                
                print(f"[Gemini API调用] [OK] 成功获取响应")
                print(f"[Gemini API调用] 响应长度: {len(cleaned_content)} 字符")
                return cleaned_content
            else:
                print(f"[Gemini API调用] [FAIL] 响应中没有候选结果")
                print(f"[Gemini API调用] 响应内容: {result}")
                raise Exception("Gemini API返回了空响应")
        else:
            print(f"[Gemini API调用] [FAIL] API返回错误")
            print(f"[Gemini API调用] 错误详情: {response.text}")
            raise Exception(f"Gemini API返回错误: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        print(f"[Gemini API调用] [FAIL] 请求超时（{timeout}秒）")
        raise Exception(f"Gemini API请求超时（{timeout}秒）")
    except Exception as e:
        print(f"[Gemini API调用] [FAIL] 调用失败: {str(e)}")
        raise Exception(f"调用Gemini API失败: {str(e)}")


def call_gemini_vision_api(image_base64, prompt, timeout=300):
    """
    调用 Google Gemini Vision API 进行多模态理解

    Args:
        image_base64: 图片的base64编码
        prompt: 文本提示
        timeout: 超时时间（秒）

    Returns:
        str: Gemini的响应文本
    """
    import requests
    import json
    from .models import SystemSettings

    # 获取Gemini配置
    gemini_config = SystemSettings.get_gemini_config()
    api_key = gemini_config['api_key']
    model_name = gemini_config['model_name']

    if not api_key:
        raise Exception("Gemini API密钥未配置，请在系统设置中配置")

    print(f"\n{'='*80}")
    print(f"[Gemini Vision API调用] 开始")
    print(f"[Gemini Vision API调用] 模型: {model_name}")
    print(f"[Gemini Vision API调用] 超时: {timeout}秒")

    # 构建请求内容
    gemini_data = {
        "contents": [{
            "parts": [
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                },
                {
                    "text": prompt
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192
        }
    }

    # 构建API URL
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    print(f"[Gemini Vision API调用] 请求URL: {api_url}")

    try:
        import time
        start_time = time.time()

        response = requests.post(
            api_url,
            json=gemini_data,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )

        end_time = time.time()
        duration = end_time - start_time

        print(f"[Gemini Vision API调用] 状态码: {response.status_code}")
        print(f"[Gemini Vision API调用] 响应时间: {duration:.2f}秒")

        if response.status_code == 200:
            result = response.json()

            if 'candidates' in result and len(result['candidates']) > 0:
                content = result['candidates'][0]['content']['parts'][0]['text']
                
                # 清理thinking标签和思考过程
                import re
                cleaned_content = content.strip()
                
                thinking_patterns = [
                    (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                    (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                    (r'</think>[\s\S]*?</think>', '', re.IGNORECASE),
                    (r'思考过程[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'让我先分析[\s\S]*?(?=\n)', '', re.IGNORECASE),
                    (r'分析如下[:：][\s\S]*?(?=\n)', '', re.IGNORECASE),
                ]
                
                for pattern, replacement, *flags in thinking_patterns:
                    flags = flags[0] if flags else 0
                    old_text = cleaned_content
                    cleaned_content = re.sub(pattern, replacement, cleaned_content, flags=flags)
                
                print(f"[Gemini Vision API调用] [OK] 成功获取响应")
                return cleaned_content
            else:
                raise Exception("Gemini Vision API返回了空响应")
        else:
            raise Exception(f"Gemini Vision API返回错误: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        raise Exception(f"Gemini Vision API请求超时（{timeout}秒）")
    except Exception as e:
        raise Exception(f"调用Gemini Vision API失败: {str(e)}")


MEDICATION_RECOGNITION_PROMPT = """你是一个专业的医药助手，请分析这张药单/处方图片，提取所有药物信息。

**任务要求：**
1. 识别图片中的所有药物名称
2. 提取每种药物的服用方式/剂量
3. 识别服药周期（开始日期、结束日期）
4. 提取任何备注信息（如饭前/饭后服用、注意事项等）
5. 对药单内容进行总结

**重要约束：**
1. 只提取图片中明确可见的信息，不要编造
2. 如果某些信息不清晰或不存在，请填null
3. 药名使用图片中显示的原始名称
4. 日期格式统一为 YYYY-MM-DD

**JSON格式要求：**
{
    "medications": [
        {
            "medicine_name": "药物名称",
            "dosage": "服用方式/剂量",
            "start_date": "开始日期或null",
            "end_date": "结束日期或null",
            "notes": "备注信息或null"
        }
    ],
    "summary": "对整个药单的总结说明"
}

请严格按照JSON格式返回，不要添加任何解释文字。
"""


class MedicationRecognitionService:
    """药单图片识别服务"""

    def __init__(self):
        config = SystemSettings.get_vl_model_config()
        self.vl_provider = config['provider']
        self.vl_api_url = config['api_url']
        self.vl_api_key = config['api_key']
        self.vl_model_name = config['model_name']
        self.vl_timeout = int(config['timeout'])
        self.vl_max_tokens = int(config['max_tokens'])

    def _validate_config(self):
        """验证配置是否完整"""
        if self.vl_provider == 'gemini':
            gemini_config = SystemSettings.get_gemini_config()
            if not gemini_config.get('api_key'):
                raise Exception("Gemini API密钥未配置，请在系统设置中配置 Gemini API Key")
        else:
            if not self.vl_api_url:
                raise Exception("多模态模型 API URL 未配置，请在系统设置中配置 VL Model API URL")
            if not self.vl_api_key:
                raise Exception("多模态模型 API Key 未配置，请在系统设置中配置 VL Model API Key")
            if not self.vl_model_name:
                raise Exception("多模态模型名称未配置，请在系统设置中配置 VL Model Name")

    def recognize_medication_image(self, image_path):
        """识别药单图片"""
        try:
            self._validate_config()
            
            print(f"\n{'='*80}")
            print(f"[药单识别] 开始处理药单图片")
            print(f"[药单识别] 文件路径: {image_path}")
            print(f"[药单识别] 处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            if self.vl_provider == 'gemini':
                result = self._call_gemini_for_medication(image_path)
            else:
                result = self._call_openai_for_medication(image_path)

            print(f"[药单识别] 识别完成")
            print(f"{'='*80}\n")
            return result

        except Exception as e:
            print(f"[药单识别] 识别失败: {str(e)}")
            raise

    def _call_gemini_for_medication(self, image_path):
        """使用 Gemini Vision API 识别药单"""
        try:
            gemini_config = SystemSettings.get_gemini_config()
            api_key = gemini_config['api_key']
            model_name = gemini_config.get('model_name', self.vl_model_name)

            if not api_key:
                raise Exception("Gemini API密钥未配置")

            with open(image_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            request_data = {
                "contents": [{
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": image_data
                            }
                        },
                        {
                            "text": MEDICATION_RECOGNITION_PROMPT
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": self.vl_max_tokens
                }
            }

            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

            print(f"[药单识别] 调用 Gemini API: {model_name}")

            import time
            start_time = time.time()

            response = requests.post(
                api_url,
                json=request_data,
                headers={"Content-Type": "application/json"},
                timeout=self.vl_timeout
            )

            duration = time.time() - start_time
            print(f"[药单识别] 响应时间: {duration:.2f}秒")

            if response.status_code == 200:
                result = response.json()
                content = result['candidates'][0]['content']['parts'][0]['text']
                
                cleaned_content = self._clean_thinking_tags(content)
                return self._parse_medication_response(cleaned_content)
            else:
                raise Exception(f"Gemini API调用失败: {response.status_code}")

        except Exception as e:
            print(f"[药单识别] Gemini调用失败: {str(e)}")
            raise

    def _call_openai_for_medication(self, image_path):
        """使用 OpenAI 兼容 API 识别药单"""
        try:
            image_base64 = self._encode_image_to_base64(image_path)

            request_data = {
                "model": self.vl_model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": MEDICATION_RECOGNITION_PROMPT
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_base64,
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                "temperature": 0.1,
                "max_tokens": self.vl_max_tokens
            }

            headers = {
                "Content-Type": "application/json"
            }

            if self.vl_api_key:
                headers["Authorization"] = f"Bearer {self.vl_api_key}"

            base_url = self.vl_api_url.rstrip('/')
            if not base_url:
                raise Exception("多模态模型 API URL 未配置，请在系统设置中配置 VL Model API URL")
            
            if '/chat/completions' not in base_url:
                api_url = f"{base_url}/v1/chat/completions"
            else:
                api_url = base_url

            if not api_url.startswith('http://') and not api_url.startswith('https://'):
                raise Exception(f"多模态模型 API URL 格式错误，应以 http:// 或 https:// 开头: {api_url}")

            print(f"[药单识别] 调用 OpenAI 兼容 API: {self.vl_model_name}")

            import time
            start_time = time.time()

            response = requests.post(
                api_url,
                json=request_data,
                headers=headers,
                timeout=self.vl_timeout
            )

            duration = time.time() - start_time
            print(f"[药单识别] 响应时间: {duration:.2f}秒")

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                cleaned_content = self._clean_thinking_tags(content)
                return self._parse_medication_response(cleaned_content)
            else:
                raise Exception(f"API调用失败: {response.status_code}")

        except Exception as e:
            print(f"[药单识别] OpenAI调用失败: {str(e)}")
            raise

    def _encode_image_to_base64(self, image_path):
        """将图片编码为base64"""
        from PIL import Image
        import io

        with Image.open(image_path) as img:
            max_size = 1024
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            if img.mode != 'RGB':
                img = img.convert('RGB')

            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=85)
            buffer.seek(0)

            image_data = buffer.read()
            base64_data = base64.b64encode(image_data).decode('utf-8')

        return f"data:image/jpeg;base64,{base64_data}"

    def _clean_thinking_tags(self, content):
        """清理思考标签"""
        cleaned_content = content.strip()
        
        thinking_patterns = [
            (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
            (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
            (r'```json\s*', ''),
            (r'```\s*', ''),
        ]
        
        for pattern, replacement, *flags in thinking_patterns:
            flags = flags[0] if flags else 0
            cleaned_content = re.sub(pattern, replacement, cleaned_content, flags=flags)
        
        return cleaned_content.strip()

    def _parse_medication_response(self, content):
        """解析药单识别响应"""
        try:
            result = json.loads(content)
            if 'medications' in result:
                return result
            else:
                raise Exception("响应格式不正确：缺少 medications 字段")
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    if 'medications' in result:
                        return result
                except:
                    pass
            raise Exception("无法解析API响应为JSON格式")
