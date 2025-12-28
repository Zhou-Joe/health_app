import requests
import json
import time
import re
import base64
from datetime import datetime
from django.conf import settings
from .models import DocumentProcessing, HealthIndicator, SystemSettings


class DocumentProcessingService:
    """文档处理服务类"""

    def __init__(self, document_processing):
        self.document_processing = document_processing
        # 从数据库获取动态配置
        self.mineru_api_url = SystemSettings.get_setting('mineru_api_url', 'http://localhost:8000')
        # 读取数据整合LLM的配置
        self.llm_provider = SystemSettings.get_setting('llm_provider', 'openai')
        self.llm_api_url = SystemSettings.get_setting('llm_api_url', 'http://172.25.48.1:1234')
        self.llm_api_key = SystemSettings.get_setting('llm_api_key', '')
        self.llm_model_name = SystemSettings.get_setting('llm_model_name', 'qwen3-4b-instruct')
        # 使用统一的AI模型超时配置
        self.ai_timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        # 使用文档处理的max_tokens配置
        self.document_max_tokens = int(SystemSettings.get_setting('document_max_tokens', '8000'))

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
                    timeout=self.ai_timeout  # 使用统一的超时设置
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
        """调用LLM服务进行文档分析"""
        print(f"\n{'='*60}")
        print(f"🧠 [LLM服务] 开始调用大语言模型")
        print(f"📝 OCR文本长度: {len(ocr_text)} 字符")
        print(f"📝 OCR文本前200字符: {ocr_text[:200]}...")
        print(f"🔧 LLM提供商: {self.llm_provider}")

        # 构建prompt
        prompt = self._build_llm_prompt(ocr_text)
        print(f"📋 构建完成Prompt，长度: {len(prompt)} 字符")

        # 根据provider类型调用不同的API
        if self.llm_provider == 'gemini':
            return self._call_gemini_api(ocr_text, prompt)
        else:
            return self._call_openai_compatible_api(ocr_text, prompt)

    def _call_gemini_api(self, ocr_text, prompt):
        """调用Gemini API"""
        from .models import SystemSettings

        # 获取Gemini配置
        gemini_config = SystemSettings.get_gemini_config()
        api_key = gemini_config['api_key']
        model_name = gemini_config['model_name']

        if not api_key:
            raise Exception("Gemini API密钥未配置，请在系统设置中配置")

        # 构建Gemini API请求
        gemini_data = {
            "contents": [{
                "parts": [
                    {
                        "text": "你是一个专业的医疗数据分析助手，请从体检报告OCR文本中提取健康指标数据，并严格按照指定的JSON格式返回。"
                    },
                    {
                        "text": prompt
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": self.document_max_tokens
            }
        }

        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        print(f"🌐 Gemini API配置信息:")
        print(f"   - API URL: {api_url[:100]}...")
        print(f"   - 模型名称: {model_name}")
        print(f"   - 超时时间: {self.ai_timeout}秒")
        print(f"   - 最大令牌数: {self.document_max_tokens}")

        try:
            import time
            start_time = time.time()

            response = requests.post(
                api_url,
                json=gemini_data,
                timeout=self.ai_timeout
            )

            end_time = time.time()
            print(f"⏱️  请求耗时: {end_time - start_time:.2f} 秒")
            print(f"📥 API响应状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                # 提取Gemini的响应文本
                if 'candidates' in result and len(result['candidates']) > 0:
                    llm_response_text = result['candidates'][0]['content']['parts'][0]['text']
                    print(f"✅ Gemini API调用成功，响应长度: {len(llm_response_text)} 字符")
                    print(f"📄 响应内容前200字符: {llm_response_text[:200]}...")

                    # 清理响应，移除可能的markdown代码块标记
                    cleaned_response = llm_response_text.strip()
                    if cleaned_response.startswith('```json'):
                        cleaned_response = cleaned_response[7:]
                    elif cleaned_response.startswith('```'):
                        cleaned_response = cleaned_response[3:]
                    if cleaned_response.endswith('```'):
                        cleaned_response = cleaned_response[:-3]
                    cleaned_response = cleaned_response.strip()

                    print(f"🧹 清理后的响应前200字符: {cleaned_response[:200]}...")

                    # 解析JSON响应
                    try:
                        structured_data = json.loads(cleaned_response)
                        indicators_count = len(structured_data.get('indicators', []))
                        print(f"✅ JSON解析成功，包含 {indicators_count} 个指标")
                        return structured_data
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON解析失败: {str(e)}")
                        print(f"📄 完整响应内容:\n{llm_response_text}")
                        raise Exception(f"Gemini返回的不是有效的JSON格式: {str(e)}")
                else:
                    raise Exception("Gemini API返回格式错误：没有candidates")
            else:
                raise Exception(f"Gemini API调用失败: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            print(f"❌ Gemini API调用超时（超过{self.ai_timeout}秒）")
            raise Exception(f"Gemini API调用超时")
        except Exception as e:
            print(f"❌ Gemini API调用失败: {str(e)}")
            raise

    def _call_openai_compatible_api(self, ocr_text, prompt):
        """调用OpenAI兼容格式的API"""
        # 准备本地LLM API请求
        llm_data = {
            "model": self.llm_model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的医疗数据分析助手，请从体检报告OCR文本中提取健康指标数据，并严格按照指定的JSON格式返回。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
            "max_tokens": self.document_max_tokens
        }

        # 准备请求头
        headers = {
            "Content-Type": "application/json"
        }

        # 只有在有API Key时才添加Authorization头
        if self.llm_api_key:
            headers["Authorization"] = f"Bearer {self.llm_api_key}"

        try:
            print(f"🌐 OpenAI兼容API配置信息:")
            print(f"   - API URL: {self.llm_api_url}")
            print(f"   - 模型名称: {self.llm_model_name}")
            print(f"   - 超时时间: {self.ai_timeout}秒")
            print(f"   - 最大令牌数: {self.document_max_tokens}")
            print(f"   - API Key: {'已设置' if self.llm_api_key else '未设置'}")

            # 直接使用配置的完整API地址
            api_url = self.llm_api_url
            print(f"🔧 使用API地址: {api_url}")

            print(f"📤 请求数据大小: {len(json.dumps(llm_data))} 字符")

            # 记录请求开始时间
            import time
            start_time = time.time()

            print(f"🚀 正在发送请求到LLM服务...")
            response = requests.post(
                api_url,
                json=llm_data,
                headers=headers,
                timeout=self.ai_timeout
            )

            # 计算请求耗时
            end_time = time.time()
            request_duration = end_time - start_time

            print(f"⏱️  请求耗时: {request_duration:.2f} 秒")
            print(f"📥 API响应状态码: {response.status_code}")
            print(f"📥 API响应大小: {len(response.text)} 字符")
            print(f"📥 API响应前500字符: {response.text[:500]}...")

            if response.status_code == 200:
                result = response.json()
                # OpenAI兼容格式的响应解析
                if 'choices' in result and len(result['choices']) > 0:
                    llm_response_text = result['choices'][0]['message']['content']
                    print(f"✅ OpenAI兼容API调用成功")
                    print(f"📄 LLM响应长度: {len(llm_response_text)} 字符")

                    # 清理响应，移除可能的markdown代码块标记
                    cleaned_response = llm_response_text.strip()
                    if cleaned_response.startswith('```json'):
                        cleaned_response = cleaned_response[7:]
                    elif cleaned_response.startswith('```'):
                        cleaned_response = cleaned_response[3:]
                    if cleaned_response.endswith('```'):
                        cleaned_response = cleaned_response[:-3]
                    cleaned_response = cleaned_response.strip()

                    print(f"🧹 清理后的响应前200字符: {cleaned_response[:200]}...")

                    # 尝试解析JSON
                    try:
                        structured_data = json.loads(cleaned_response)
                        print(f"✅ JSON解析成功，包含 {len(structured_data.get('indicators', []))} 个指标")
                        return structured_data
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON解析失败: {str(e)}")
                        print(f"📄 完整LLM响应内容:\n{llm_response_text}")
                        raise Exception(f"LLM返回的不是有效的JSON格式: {str(e)}")
                else:
                    raise Exception("API返回格式错误：没有choices字段")
            else:
                raise Exception(f"API调用失败: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            print(f"❌ LLM API调用超时 (超过{self.ai_timeout}秒)")
            raise Exception("本地LLM API调用超时")
        except requests.exceptions.RequestException as e:
            print(f"❌ LLM API网络错误: {str(e)}")
            raise Exception(f"本地LLM API网络错误: {str(e)}")
        except Exception as e:
            print(f"❌ LLM API调用失败: {str(e)}")
            raise

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

        # 检查关键词映射（包含新的分类）
        type_mapping = {
            'physical_exam': physical_exam_keywords,
            'blood_routine': blood_routine_keywords,
            'biochemistry': biochemistry_keywords,
            'liver_function': liver_function_keywords,
            'kidney_function': kidney_function_keywords,
            'thyroid_function': thyroid_function_keywords,
            'tumor_markers': tumor_markers_keywords,
            'urine_exam': urine_exam_keywords,
            'blood_rheology': blood_rheology_keywords,
            'eye_exam': eye_exam_keywords,
            'ultrasound_exam': ultrasound_keywords,
            'imaging_exam': imaging_keywords,
            'diagnosis': diagnosis_keywords,
            'symptoms': symptoms_keywords,
        }

        # 优先检查病症诊断和症状（最高优先级）
        for keyword in diagnosis_keywords:
            if keyword in indicator_name:
                return 'diagnosis'
        
        for keyword in symptoms_keywords:
            if keyword in indicator_name:
                return 'symptoms'

        # 特殊处理一些复合词
        if '收缩压/舒张压' in indicator_name or '血压' in indicator_name:
            return 'physical_exam'  # 血压归为体格检查
        if '体重指数' in indicator_name or 'BMI' in indicator_name:
            return 'physical_exam'

        # 优先处理超声和影像学检查相关的特殊词汇（中等优先级）
        ultrasound_patterns = ['超声', 'B超', '彩超', '多普勒', '超声心动图']
        imaging_patterns = ['CT', 'MRI', 'X光', 'PET', 'SPECT', '造影', '断层', '磁共振']

        for pattern in ultrasound_patterns:
            if pattern in indicator_name:
                return 'ultrasound_exam'

        for pattern in imaging_patterns:
            if pattern in indicator_name:
                return 'imaging_exam'

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
                            return 'imaging_exam'
                    return 'ultrasound_exam'

        # 模糊匹配其他类型（最低优先级）
        for indicator_type, keywords in type_mapping.items():
            for keyword in keywords:
                if keyword in indicator_name:
                    return indicator_type

        return 'other_exam'

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
- **数值指标：** 血压、心率、血糖、血常规、生化检验等具体数值
- **诊断结论：** 高血压、糖尿病、脂肪肝等疾病诊断
- **症状描述：** 头痛、胸闷、皮疹等症状表现
- **检查发现：** 超声、CT、心电图等检查的描述性结果
- **体征数据：** 器官大小、形态等测量值

**特别注意：**
- 不仅要提取表格数据，还要识别段落中的健康信息
- 对于描述性检查，推断并提取结构化指标
- 确保不遗漏任何数值化的医学检查结果

**重要约束：**
1. **不要无中生有：** 只提取OCR文本中明确存在的指标数据
2. **参考值处理：** 如果报告中没有提供参考范围（normal_range），请留空或填null，不要编造
3. **异常判断：** 只有当报告中明确标注了异常（如↑↓箭头、异常字样、超出参考范围）时才标记"是"，否则留空或填null
4. **数据真实性：** 宁可少提取，也不要编造报告中不存在的内容

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
            saved_count = 0
            skipped_count = 0
            error_count = 0

            for indicator_data in indicators:
                try:
                    # 处理新的LLM响应格式
                    indicator_name = indicator_data.get('indicator', indicator_data.get('name', ''))
                    measured_value = indicator_data.get('measured_value', indicator_data.get('value', ''))
                    normal_range = indicator_data.get('normal_range', indicator_data.get('reference_range', None))
                    is_abnormal = indicator_data.get('abnormal', None)

                    # 跳过缺少指标名称的数据
                    if not indicator_name or not str(indicator_name).strip():
                        print(f"⚠️  跳过指标: 缺少指标名称")
                        skipped_count += 1
                        continue

                    # 处理measured_value的null值，增加容错性
                    if measured_value is None or measured_value == 'null' or not str(measured_value).strip():
                        clean_value = ''  # 使用空字符串而不是'None'
                        print(f"⚠️  指标 '{indicator_name}' 的检测值为空，使用空字符串")
                    else:
                        # 处理 null 值
                        if normal_range is None or normal_range == 'null':
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
                        unit=unit if unit else '',  # 确保unit不是None
                        reference_range=normal_range or '',  # 确保 None 转为空字符串
                        status=status if status else 'normal'  # 保存计算出的状态值
                    )
                    saved_count += 1
                    status_display = status if status else 'normal(默认)'
                    print(f"✅ 已保存指标 {saved_count}: {indicator_name} = {clean_value if clean_value else '(空)'} {unit if unit else ''} (参考范围:{normal_range or '空'}, 状态:{status_display})")

                except Exception as e:
                    # 单个指标保存失败不影响其他指标
                    error_count += 1
                    print(f"❌ 保存指标失败: {indicator_data.get('indicator', '未知指标')} - 错误: {str(e)}")
                    continue

            # 更新进度
            progress = 80 + int((saved_count / len(indicators)) * 15) if indicators else 95
            summary_msg = f"已保存 {saved_count}/{len(indicators)} 项指标"
            if skipped_count > 0:
                summary_msg += f"，跳过 {skipped_count} 项"
            if error_count > 0:
                summary_msg += f"，失败 {error_count} 项"
            self.update_progress('saving_data', progress, summary_msg)

            self.update_progress('completed', 100, f"处理完成 - 成功:{saved_count}, 跳过:{skipped_count}, 失败:{error_count}")
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
    """检查MinerU API状态"""
    try:
        # 从数据库获取配置
        mineru_api_url = SystemSettings.get_setting('mineru_api_url', 'http://localhost:8000')
        response = requests.get(f"{mineru_api_url}/docs", timeout=5)
        return response.status_code == 200
    except:
        return False


def get_llm_api_status():
    """检查LLM API状态"""
    try:
        # 从数据库获取配置
        llm_config = SystemSettings.get_llm_config()
        llm_provider = llm_config.get('provider', 'openai')
        llm_api_url = llm_config.get('api_url')
        llm_api_key = llm_config.get('api_key')
        llm_model_name = llm_config.get('model_name')

        if not llm_api_url or not llm_model_name:
            return False

        # 发送测试请求
        if llm_provider == 'gemini':
            # Gemini API
            gemini_api_key = SystemSettings.get_setting('gemini_api_key', '')
            if not gemini_api_key:
                return False

            check_url = f"https://generativelanguage.googleapis.com/v1beta/models/{llm_model_name}:generateContent?key={gemini_api_key}"
            data = {"contents": [{"parts": [{"text": "test"}]}]}
        else:
            # OpenAI兼容格式 - 直接使用配置的API URL
            check_url = llm_api_url
            data = {
                "model": llm_model_name,
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 5
            }

        headers = {'Content-Type': 'application/json'}
        if llm_api_key:
            headers['Authorization'] = f"Bearer {llm_api_key}"

        response = requests.post(check_url, json=data, headers=headers, timeout=10)
        return response.status_code == 200
    except:
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
            print(f"🤖 [多模态大模型] 开始处理文档")
            print(f"📄 文件路径: {file_path}")
            print(f"⏰ 处理开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            self.update_progress('ai_processing', 30, "开始多模态大模型分析...")

            # 判断文件类型
            file_ext = file_path.lower().split('.')[-1] if '.' in file_path.lower() else 'unknown'
            print(f"📋 检测到文件类型: {file_ext}")

            if file_path.lower().endswith('.pdf'):
                # PDF文件需要转换为图片
                print(f"🔄 PDF文件需要转换为图片...")
                try:
                    images = self._convert_pdf_to_images(file_path)
                    print(f"✅ PDF转换成功，共{len(images)}页")
                    self.update_progress('ai_processing', 40, f"PDF转换成功，共{len(images)}页")
                except Exception as pdf_error:
                    # 如果PDF转换失败，建议用户使用其他工作流
                    print(f"❌ PDF转换失败: {str(pdf_error)}")
                    error_msg = f"PDF文件处理失败：{str(pdf_error)}\n\n建议：\n1. 对于PDF文件，建议使用'MinerU Pipeline'或'MinerU VLM-Transformers'工作流\n2. 或者将PDF转换为图片后使用多模态工作流\n3. 或者安装poppler依赖以支持PDF转换"
                    self.update_progress('failed', 0, error_msg, is_error=True)
                    raise Exception(error_msg)
            else:
                # 图片文件直接处理
                images = [file_path]
                print(f"🖼️  检测到图片文件，直接处理")
                self.update_progress('ai_processing', 40, "检测到图片文件，直接处理")

            all_indicators = []
            total_images = len(images)
            print(f"📊 总共需要处理 {total_images} 页/张图片")

            for i, image_path in enumerate(images):
                progress = 40 + int((i / total_images) * 30)
                self.update_progress('ai_processing', progress, f"分析第 {i+1}/{total_images} 页...")

                # 处理单页图片
                indicators = self._process_single_image(image_path, i+1, total_images)
                all_indicators.extend(indicators)
                print(f"📈 第 {i+1} 页处理完成，提取到 {len(indicators)} 个指标")

            print(f"📋 所有页面处理完成，原始指标总数: {len(all_indicators)}")

            # 合并和去重指标
            print(f"🔄 开始合并和去重指标...")
            unique_indicators = self._merge_indicators(all_indicators)
            print(f"📊 去重后指标总数: {len(unique_indicators)}")

            # 保存处理结果
            processing_result = {
                'indicators': unique_indicators,
                'total_pages': total_images,
                'file_type': 'PDF' if file_path.lower().endswith('.pdf') else 'Image',
                'processing_time': datetime.now().isoformat()
            }

            self.document_processing.vl_model_result = processing_result
            self.document_processing.save()

            print(f"💾 处理结果已保存到数据库")
            print(f"⏰ 处理完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"🎉 多模态大模型处理完成!")
            print(f"{'='*80}\n")

            self.update_progress('ai_processing', 70, "多模态大模型分析完成")
            return {
                'indicators': unique_indicators,
                'total_pages': total_images
            }

        except Exception as e:
            print(f"❌ 多模态大模型处理失败: {str(e)}")
            print(f"⏰ 失败时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
            print(f"🔍 [多模态大模型] 开始处理第 {page_num}/{total_pages} 页图片")
            print(f"📁 图片路径: {image_path}")

            # 构建针对医疗报告的prompt
            prompt = self._build_vision_prompt(page_num, total_pages)
            print(f"📝 Prompt长度: {len(prompt)} 字符")
            print(f"📝 Prompt前200字符: {prompt[:200]}...")

            # 根据提供商选择不同的API调用方式
            if self.vl_provider == 'gemini':
                # 使用 Gemini Vision API
                return self._call_gemini_vision_api(image_path, prompt)
            else:
                # 使用 OpenAI 兼容格式
                return self._call_openai_vision_api(image_path, prompt)

        except Exception as e:
            print(f"❌ 处理第{page_num}页图片失败: {str(e)}")
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

            print(f"🌐 Gemini API配置信息:")
            print(f"   - API URL: {api_url}")
            print(f"   - 模型名称: {model_name}")
            print(f"   - 超时时间: {self.vl_timeout}秒")
            print(f"📤 请求数据大小: {len(json.dumps(request_data))} 字符")

            # 记录请求开始时间
            import time
            start_time = time.time()

            print(f"🚀 正在发送请求到 Gemini...")
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
            print(f"📥 响应状态码: {response.status_code}")
            print(f"📥 响应大小: {len(response.text)} 字符")
            print(f"📥 响应前500字符: {response.text[:500]}...")

            if response.status_code == 200:
                result = response.json()
                content = result['candidates'][0]['content']['parts'][0]['text']

                print(f"✅ Gemini API调用成功!")
                print(f"📄 返回内容长度: {len(content)} 字符")
                print(f"📄 返回内容前300字符: {content[:300]}...")

                # 解析返回的JSON结果
                print(f"🔧 开始解析JSON响应...")
                indicators = self._parse_vision_response(content)

                print(f"📊 解析完成，提取到 {len(indicators)} 个指标")
                for i, indicator in enumerate(indicators):
                    print(f"   指标 {i+1}: {indicator.get('indicator', 'N/A')} = {indicator.get('measured_value', 'N/A')} ({indicator.get('abnormal', 'N/A')})")

                print(f"{'='*60}\n")
                return indicators
            else:
                print(f"❌ Gemini API调用失败!")
                print(f"❌ 错误详情: {response.text}")
                raise Exception(f"Gemini API调用失败: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"❌ Gemini Vision API调用失败: {str(e)}")
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
                        "content": "你是一个专业的医疗数据分析助手，专门从体检报告图片中提取健康指标数据。"
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

            # API调用直接使用配置的完整地址
            api_url = self.vl_api_url

            print(f"🌐 OpenAI Vision API配置信息:")
            print(f"   - API URL: {api_url}")
            print(f"   - 模型名称: {self.vl_model_name}")
            print(f"   - 超时时间: {self.vl_timeout}秒")
            print(f"   - 最大令牌数: {self.vl_max_tokens}")
            print(f"   - API Key: {'已设置' if self.vl_api_key else '未设置'}")
            print(f"📤 请求数据大小: {len(json.dumps(request_data))} 字符")

            # 记录请求开始时间
            import time
            start_time = time.time()

            print(f"🚀 正在发送请求到多模态大模型...")
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
            print(f"📥 响应状态码: {response.status_code}")
            print(f"📥 响应大小: {len(response.text)} 字符")
            print(f"📥 响应前500字符: {response.text[:500]}...")

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']

                print(f"✅ API调用成功!")
                print(f"📄 返回内容长度: {len(content)} 字符")
                print(f"📄 返回内容前300字符: {content[:300]}...")

                # 解析返回的JSON结果
                print(f"🔧 开始解析JSON响应...")
                indicators = self._parse_vision_response(content)

                print(f"📊 解析完成，提取到 {len(indicators)} 个指标")
                for i, indicator in enumerate(indicators):
                    print(f"   指标 {i+1}: {indicator.get('indicator', 'N/A')} = {indicator.get('measured_value', 'N/A')} ({indicator.get('abnormal', 'N/A')})")

                print(f"{'='*60}\n")
                return indicators
            else:
                print(f"❌ API调用失败!")
                print(f"❌ 错误详情: {response.text}")
                raise Exception(f"多模态模型API调用失败: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"❌ OpenAI Vision API调用失败: {str(e)}")
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
- **数值指标：** 血压、心率、血糖、血常规、生化检验等具体检测数值
- **诊断结论：** 如"高血压"、"糖尿病"、"脂肪肝"等疾病诊断
- **症状描述：** 如"头痛"、"皮疹"、"红肿"等具体症状表现
- **检查发现：** 超声、CT、X光等影像学检查的描述性结果
- **体征数据：** 器官大小、厚度、形态等解剖结构测量值

**重要约束：**
1. **不要无中生有：** 只提取图片中明确可见或明确写明的指标数据
2. **参考值处理：** 如果图片中没有提供参考范围（normal_range），请留空或填null，不要编造
3. **异常判断：** 只有当图片中明确标注了异常（如↑↓箭头、异常字样、超出参考范围、阳性）时才标记"是"，否则留空或填null
4. **数据真实性：** 宁可少提取，也不要编造图片中不存在的内容
5. **清晰度要求：** 如果文字模糊不清无法准确识别，不要强行猜测，应该略过该项数据

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
        print(f"🔧 开始智能JSON提取和清理...")
        print(f"📄 原始文本长度: {len(text)} 字符")
        print(f"📄 原始文本前300字符: {text[:300]}...")

        # 方法1: 尝试直接解析（如果文本本身就是纯净的JSON）
        try:
            result = json.loads(text.strip())
            print(f"✅ 方法1成功: 直接解析JSON")
            return result
        except json.JSONDecodeError:
            print(f"❌ 方法1失败: 无法直接解析JSON")

        # 方法2: 清理常见的代码块标记
        cleaned_patterns = [
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
                print(f"🧹 清理模式应用: 移除了 {len(old_text) - len(cleaned_text)} 个字符")

        cleaned_text = cleaned_text.strip()
        print(f"🧹 基础清理后长度: {len(cleaned_text)} 字符")

        # 尝试解析清理后的文本
        try:
            result = json.loads(cleaned_text)
            print(f"✅ 方法2成功: 基础清理后解析成功")
            return result
        except json.JSONDecodeError as e:
            print(f"❌ 方法2失败: {str(e)}")

        # 方法3: 使用正则表达式提取JSON对象
        print(f"🔍 方法3: 使用正则表达式提取JSON对象...")

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
                print(f"🔍 模式{i}: 找到 {len(matches)} 个潜在JSON对象")

                for j, json_str in enumerate(matches):
                    print(f"   尝试对象 {j+1}: 长度 {len(json_str)} 字符")
                    try:
                        result = json.loads(json_str)
                        if 'indicators' in result:
                            print(f"✅ 方法3.{i}.{j+1}成功: 找到包含indicators的JSON对象")
                            return result
                    except json.JSONDecodeError as e:
                        print(f"   对象 {j+1} 解析失败: {str(e)[:100]}...")
                        continue

            except Exception as e:
                print(f"❌ 方法3.{i}失败: {str(e)}")
                continue

        # 方法4: 括号匹配法
        print(f"🔍 方法4: 括号匹配法...")
        json_candidates = self._extract_by_bracket_matching(text)
        for i, candidate in enumerate(json_candidates):
            try:
                result = json.loads(candidate)
                if 'indicators' in result:
                    print(f"✅ 方法4.{i+1}成功: 括号匹配找到有效JSON")
                    return result
            except json.JSONDecodeError:
                continue

        # 方法5: 最后尝试 - 修复常见的JSON错误
        print(f"🔧 方法5: 尝试修复常见JSON错误...")
        try:
            repaired_json = self._repair_json_syntax(cleaned_text)
            if repaired_json:
                result = json.loads(repaired_json)
                print(f"✅ 方法5成功: JSON修复后解析成功")
                return result
        except Exception as e:
            print(f"❌ 方法5失败: {str(e)}")

        print(f"❌ 所有JSON提取方法都失败了")
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
            print(f"🔧 开始解析视觉模型响应...")

            # 使用智能JSON提取功能
            result = self._extract_json_from_text(content)

            if not result:
                print(f"❌ 无法从响应中提取有效的JSON")
                print(f"📄 原始响应内容: {content}")
                return []

            indicators = result.get('indicators', [])

            if not indicators:
                print(f"⚠️  JSON解析成功但未找到indicators字段")
                print(f"📄 JSON内容: {json.dumps(result, ensure_ascii=False, indent=2)}")
                return []

            # 验证和清理指标数据
            cleaned_indicators = []
            for indicator in indicators:
                if isinstance(indicator, dict) and 'indicator' in indicator:
                    # 确保必要字段存在
                    cleaned_indicators.append({
                        'indicator': indicator.get('indicator', ''),
                        'measured_value': indicator.get('measured_value', ''),
                        'normal_range': indicator.get('normal_range', ''),
                        'abnormal': indicator.get('abnormal', '否')
                    })

            print(f"✅ 视觉响应解析成功，提取到 {len(cleaned_indicators)} 个有效指标")
            return cleaned_indicators

        except Exception as e:
            print(f"❌ 视觉模型响应解析失败: {str(e)}")
            print(f"📄 原始响应前500字符: {content[:500]}...")
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
            saved_count = 0
            skipped_count = 0
            error_count = 0

            for indicator_data in indicators:
                try:
                    indicator_name = indicator_data.get('indicator', '')
                    measured_value = indicator_data.get('measured_value', '')
                    normal_range = indicator_data.get('normal_range', None)
                    is_abnormal = indicator_data.get('abnormal', None)

                    # 跳过缺少指标名称的数据
                    if not indicator_name or not str(indicator_name).strip():
                        print(f"⚠️  跳过指标: 缺少指标名称")
                        skipped_count += 1
                        continue

                    # 处理measured_value的null值，增加容错性
                    if measured_value is None or measured_value == 'null' or not str(measured_value).strip():
                        clean_value = ''  # 使用空字符串而不是'None'
                        unit = ''
                        print(f"⚠️  指标 '{indicator_name}' 的检测值为空，使用空字符串")
                    else:
                        # 处理 null 值
                        if normal_range is None or normal_range == 'null':
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
                        unit=unit if unit else '',  # 确保unit不是None
                        reference_range=normal_range or '',  # 确保 None 转为空字符串
                        status=status if status else 'normal'  # 保存计算出的状态值
                    )
                    saved_count += 1
                    status_display = status if status else 'normal(默认)'
                    print(f"✅ 已保存指标 {saved_count}: {indicator_name} = {clean_value if clean_value else '(空)'} {unit if unit else ''} (参考范围:{normal_range or '空'}, 状态:{status_display})")

                except Exception as e:
                    # 单个指标保存失败不影响其他指标
                    error_count += 1
                    print(f"❌ 保存指标失败: {indicator_data.get('indicator', '未知指标')} - 错误: {str(e)}")
                    continue

            # 更新进度
            progress = 80 + int((saved_count / len(indicators)) * 15) if indicators else 95
            summary_msg = f"已保存 {saved_count}/{len(indicators)} 项指标"
            if skipped_count > 0:
                summary_msg += f"，跳过 {skipped_count} 项"
            if error_count > 0:
                summary_msg += f"，失败 {error_count} 项"
            self.update_progress('saving_data', progress, summary_msg)

            self.update_progress('completed', 100, f"处理完成 - 成功:{saved_count}, 跳过:{skipped_count}, 失败:{error_count}")
            return saved_count

        except Exception as e:
            self.update_progress('failed', 0, f"保存数据失败: {str(e)}", is_error=True)
            raise


def get_vision_model_api_status():
    """检查多模态大模型API状态"""
    try:
        config = SystemSettings.get_vl_model_config()
        if not config['api_url'] or not config['model_name']:
            return False

        # 发送测试请求 - 直接使用配置的API URL
        check_url = config['api_url']
        data = {
            "model": config['model_name'],
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 5
        }

        headers = {'Content-Type': 'application/json'}
        if config.get('api_key'):
            headers['Authorization'] = f"Bearer {config['api_key']}"

        response = requests.post(check_url, json=data, headers=headers, timeout=10)
        return response.status_code == 200
    except:
        return False


class AIService:
    """AI服务类，用于生成健康建议"""

    def __init__(self):
        # 获取LLM配置
        self.llm_api_url = SystemSettings.get_setting('llm_api_url', 'http://172.25.48.1:1234')
        self.llm_api_key = SystemSettings.get_setting('llm_api_key', '')
        self.llm_model_name = SystemSettings.get_setting('llm_model_name', 'qwen3-4b-instruct')
        # 使用统一的AI模型超时配置
        self.ai_timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))

    def get_health_advice(self, indicators):
        """根据健康指标生成AI建议"""
        try:
            # 构建prompt
            prompt = self._build_advice_prompt(indicators)

            # 准备请求数据
            llm_data = {
                "model": self.llm_model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个专业的健康顾问医生，请根据用户的体检指标数据提供健康建议。"
                    },
                    {
                        "role": "user",
                        "content": prompt
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

            # API调用直接使用配置的完整地址
            response = requests.post(
                self.llm_api_url,
                json=llm_data,
                headers=headers,
                timeout=self.ai_timeout
            )

            if response.status_code == 200:
                result = response.json()
                advice = result['choices'][0]['message']['content']
                return advice.strip()
            else:
                raise Exception(f"AI建议生成失败: {response.status_code} - {response.text}")

        except Exception as e:
            return f"很抱歉，AI建议生成失败: {str(e)}"

    def _build_advice_prompt(self, indicators):
        """构建健康建议的prompt"""
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

        return f"""
请根据以下体检指标数据，为用户提供专业的健康建议和生活方式指导。

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
- 强调本建议仅供参考，具体诊疗请咨询专业医生
"""


def call_llm_for_integration(prompt, timeout=None):
    """
    调用LLM API进行数据整合分析

    Args:
        prompt: 发送给LLM的提示词
        timeout: 超时时间（秒），默认使用系统配置

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

    # 使用统一超时配置
    if timeout is None:
        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))

    # 从系统设置读取max_tokens
    max_tokens = int(SystemSettings.get_setting('llm_max_tokens', '16000'))

    print(f"\n{'='*80}")
    print(f"[数据整合 LLM调用] 开始")
    print(f"[数据整合 LLM调用] API URL: {llm_api_url}")
    print(f"[数据整合 LLM调用] 模型: {llm_model_name}")
    print(f"[数据整合 LLM调用] 超时: {timeout}秒")
    print(f"[数据整合 LLM调用] 最大Tokens: {max_tokens}")
    print(f"[数据整合 LLM调用] API Key: {'已设置' if llm_api_key else '未设置'}")

    # 构建请求数据
    llm_data = {
        "model": llm_model_name,
        "messages": [
            {
                "role": "system",
                "content": "严格按照JSON格式返回，不添加任何其他文字。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens  # 使用系统配置的max_tokens
    }

    # 准备请求头
    headers = {
        "Content-Type": "application/json"
    }

    # 只有在有API Key时才添加Authorization头
    if llm_api_key:
        headers["Authorization"] = f"Bearer {llm_api_key}"

    try:
        # 直接使用配置的完整API地址
        api_url = llm_api_url

        print(f"[数据整合 LLM调用] 完整API地址: {api_url}")
        print(f"[数据整合 LLM调用] Prompt长度: {len(prompt)} 字符")
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
            print(f"[数据整合 LLM调用] ✓ 成功获取响应")
            print(f"[数据整合 LLM调用] 响应内容前500字符:")
            print(f"{content[:500]}")
            print(f"[数据整合 LLM调用] 响应内容后500字符:")
            print(f"{content[-500:]}")
            return content
        else:
            print(f"[数据整合 LLM调用] ✗ API返回错误")
            print(f"[数据整合 LLM调用] 错误详情: {response.text}")
            raise Exception(f"LLM API返回错误: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        print(f"[数据整合 LLM调用] ✗ 请求超时（{timeout}秒）")
        raise Exception(f"LLM API请求超时（{timeout}秒）")
    except Exception as e:
        print(f"[数据整合 LLM调用] ✗ 调用失败: {str(e)}")
        raise Exception(f"调用LLM API失败: {str(e)}")


def call_gemini_api(prompt, system_message=None, timeout=None):
    """
    调用 Google Gemini API

    Args:
        prompt: 发送给Gemini的提示词
        system_message: 系统消息（可选）
        timeout: 超时时间（秒），默认使用系统配置

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

    # 使用统一超时配置
    if timeout is None:
        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))

    # 从系统设置读取max_tokens
    max_tokens = int(SystemSettings.get_setting('llm_max_tokens', '16000'))

    print(f"\n{'='*80}")
    print(f"[Gemini API调用] 开始")
    print(f"[Gemini API调用] 模型: {model_name}")
    print(f"[Gemini API调用] API Key: {'已设置' if api_key else '未设置'}")
    print(f"[Gemini API调用] 超时: {timeout}秒")
    print(f"[Gemini API调用] 最大Tokens: {max_tokens}")

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
            "maxOutputTokens": max_tokens  # 使用系统配置的max_tokens
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
                print(f"[Gemini API调用] ✓ 成功获取响应")
                print(f"[Gemini API调用] 响应长度: {len(content)} 字符")
                return content
            else:
                print(f"[Gemini API调用] ✗ 响应中没有候选结果")
                print(f"[Gemini API调用] 响应内容: {result}")
                raise Exception("Gemini API返回了空响应")
        else:
            print(f"[Gemini API调用] ✗ API返回错误")
            print(f"[Gemini API调用] 错误详情: {response.text}")
            raise Exception(f"Gemini API返回错误: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        print(f"[Gemini API调用] ✗ 请求超时（{timeout}秒）")
        raise Exception(f"Gemini API请求超时（{timeout}秒）")
    except Exception as e:
        print(f"[Gemini API调用] ✗ 调用失败: {str(e)}")
        raise Exception(f"调用Gemini API失败: {str(e)}")


def call_gemini_vision_api(image_base64, prompt, timeout=None):
    """
    调用 Google Gemini Vision API 进行多模态理解

    Args:
        image_base64: 图片的base64编码
        prompt: 文本提示
        timeout: 超时时间（秒），默认使用系统配置

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

    # 使用统一超时配置
    if timeout is None:
        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))

    # 使用多模态模型的max_tokens配置
    max_tokens = int(SystemSettings.get_setting('vl_model_max_tokens', '4000'))

    print(f"\n{'='*80}")
    print(f"[Gemini Vision API调用] 开始")
    print(f"[Gemini Vision API调用] 模型: {model_name}")
    print(f"[Gemini Vision API调用] 超时: {timeout}秒")
    print(f"[Gemini Vision API调用] 最大Tokens: {max_tokens}")

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
            "maxOutputTokens": max_tokens  # 使用系统配置的max_tokens
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
                print(f"[Gemini Vision API调用] ✓ 成功获取响应")
                return content
            else:
                raise Exception("Gemini Vision API返回了空响应")
        else:
            raise Exception(f"Gemini Vision API返回错误: {response.status_code} - {response.text}")

    except requests.exceptions.Timeout:
        raise Exception(f"Gemini Vision API请求超时（{timeout}秒）")
    except Exception as e:
        raise Exception(f"调用Gemini Vision API失败: {str(e)}")
