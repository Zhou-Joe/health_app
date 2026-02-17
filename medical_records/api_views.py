import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.contrib.contenttypes.models import ContentType
from .models import (HealthCheckup, DocumentProcessing, HealthIndicator, Conversation, HealthAdvice, SystemSettings,
                    Medication, MedicationRecord, MedicationGroup, HealthEvent, EventItem, CareGoal, CareAction, CarePlan)
from .forms import HealthCheckupForm
from .services import DocumentProcessingService
from .utils import convert_image_to_pdf, is_image_file
from .llm_prompts import (
    DATA_INTEGRATION_SYSTEM_PROMPT,
    DATA_INTEGRATION_USER_PROMPT_TEMPLATE,
    AI_DOCTOR_SYSTEM_PROMPT,
    AI_DOCTOR_USER_PROMPT_TEMPLATE_WITH_DATA,
    AI_DOCTOR_USER_PROMPT_TEMPLATE_WITHOUT_DATA,
    build_data_integration_prompt,
    build_ai_doctor_prompt
)
from .views import call_ai_doctor_api


def _safe_get_request_json(request):
    """
    安全获取JSON请求体。
    - DRF Request: 优先使用 request.data（可重复访问）
    - Django HttpRequest: 回退使用 request.body
    """
    # DRF Request 路径
    if hasattr(request, 'data'):
        data = request.data
        if data is None:
            return {}
        if isinstance(data, dict):
            return data
        if hasattr(data, 'dict'):
            try:
                return data.dict()
            except Exception:
                return {}
        return {}

    # 兼容普通 Django Request
    try:
        raw = request.body
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def extract_json_objects(text):
    """从文本中提取所有完整的JSON对象"""
    json_objects = []
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


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def upload_and_process(request):
    """上传并处理体检报告"""
    try:
        # 检查文件上传
        if 'file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': '没有上传文件'
            }, status=400)

        file = request.FILES['file']

        # 检查文件类型
        is_pdf = file.name.lower().endswith('.pdf')
        is_image = is_image_file(file.name)

        if not is_pdf and not is_image:
            return JsonResponse({
                'success': False,
                'error': '只支持PDF和图片格式的文件'
            }, status=400)

        # 检查文件大小 (10MB限制)
        if file.size > 10 * 1024 * 1024:
            return JsonResponse({
                'success': False,
                'error': '文件大小不能超过10MB'
            }, status=400)

        # 获取表单数据
        checkup_date = request.POST.get('checkup_date')
        hospital = request.POST.get('hospital', '未知机构')

        # 根据文件类型自动选择工作流
        from .models import SystemSettings
        workflow_type = request.POST.get('workflow_type', '')
        
        if not workflow_type:
            file_ext = file.name.lower().split('.')[-1] if '.' in file.name else ''
            if file_ext == 'pdf':
                workflow_type = SystemSettings.get_pdf_ocr_workflow()
            else:
                workflow_type = 'vl_model'

        if not checkup_date:
            return JsonResponse({
                'success': False,
                'error': '请提供体检日期'
            }, status=400)

        # 验证工作流类型 - 支持所有3种工作流
        supported_workflows = ['ocr_llm', 'vlm_transformers', 'vl_model']
        if workflow_type not in supported_workflows:
            return JsonResponse({
                'success': False,
                'error': f'不支持的工作流类型: {workflow_type}，支持的类型: {", ".join(supported_workflows)}'
            }, status=400)

        # 创建体检报告记录
        health_checkup = HealthCheckup.objects.create(
            user=request.user,
            checkup_date=checkup_date,
            hospital=hospital,
            report_file=file
        )

        # 创建或更新文档处理记录
        document_processing, created = DocumentProcessing.objects.get_or_create(
            user=request.user,
            health_checkup=health_checkup,
            defaults={
                'workflow_type': workflow_type,
                'status': 'pending',
                'progress': 0
            }
        )

        # 如果记录已存在且不是pending状态，重置为pending
        if not created:
            document_processing.workflow_type = workflow_type
            document_processing.status = 'pending'
            document_processing.progress = 0
            document_processing.ocr_result = None
            document_processing.ai_result = None
            document_processing.save()

        # 保存上传的文件到临时位置
        import os
        file_extension = os.path.splitext(file.name)[1]  # 获取文件扩展名

        # 保存上传的文件到临时位置
        import os
        file_extension = os.path.splitext(file.name)[1]  # 获取文件扩展名

        # 根据工作流类型决定如何处理文件
        if is_image:
            # 图片文件处理
            if workflow_type == 'vl_model':
                # 多模态工作流：直接保存图片，不转换
                print(f"[上传处理] 多模态工作流，直接保存图片文件: {file.name}")
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                    for chunk in file.chunks():
                        tmp_file.write(chunk)
                    tmp_file_path = tmp_file.name
                print(f"[上传处理] 图片文件保存成功: {tmp_file_path}")
            else:
                # 其他工作流：转换为PDF
                print(f"[上传处理] 非多模态工作流，将图片转换为PDF: {file.name}")
                try:
                    # 将上传的图片先保存到临时文件
                    temp_image_path = None
                    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_image:
                        for chunk in file.chunks():
                            temp_image.write(chunk)
                        temp_image_path = temp_image.name
                    
                    print(f"[上传处理] 保存临时图片文件: {temp_image_path}")
                    
                    # 将图片文件转换为PDF字节数据
                    from .utils import convert_image_file_to_pdf
                    pdf_data = convert_image_file_to_pdf(temp_image_path)

                    # 创建临时PDF文件
                    pdf_extension = '.pdf'
                    with tempfile.NamedTemporaryFile(delete=False, suffix=pdf_extension) as tmp_file:
                        tmp_file.write(pdf_data)
                        tmp_file_path = tmp_file.name

                    print(f"[上传处理] 图片转PDF成功: {tmp_file_path}")
                    
                    # 清理临时图片文件
                    try:
                        os.unlink(temp_image_path)
                        print(f"[上传处理] 清理临时图片文件成功: {temp_image_path}")
                    except Exception as cleanup_error:
                        print(f"[上传处理] 清理临时图片文件失败: {cleanup_error}")

                except Exception as e:
                    print(f"[上传处理] 图片转PDF失败: {str(e)}")
                    # 清理临时文件
                    if 'temp_image_path' in locals() and temp_image_path and os.path.exists(temp_image_path):
                        try:
                            os.unlink(temp_image_path)
                        except:
                            pass
                    return JsonResponse({
                        'success': False,
                        'error': f'图片转PDF失败: {str(e)}'
                    }, status=400)
        else:
            # PDF文件直接保存
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                for chunk in file.chunks():
                    tmp_file.write(chunk)
                tmp_file_path = tmp_file.name

            print(f"[上传处理] PDF文件保存成功: {tmp_file_path}")

        # 在后台启动处理流程
        import threading
        processing_thread = threading.Thread(
            target=process_document_background,
            args=(document_processing.id, tmp_file_path),
            name=f"DocumentProcessing-{document_processing.id}"
        )
        processing_thread.daemon = False  # 改为非守护线程，确保处理完成
        processing_thread.start()

        print(f"启动后台处理线程: {processing_thread.name}")

        return JsonResponse({
            'success': True,
            'processing_id': document_processing.id,
            'message': '文件上传成功，开始处理...'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'上传失败: {str(e)}'
        }, status=500)


@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stream_ai_summary(request):
    """流式输出AI对话总结（使用LangChain）"""
    import json
    import traceback
    from django.http import StreamingHttpResponse
    from .models import SystemSettings, Conversation, HealthAdvice
    from .llm_prompts import build_ai_summary_prompt

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': '只支持POST请求'
        }, status=405)

    try:
        data = _safe_get_request_json(request)
        if not isinstance(data, dict):
            data = {}
        conversation_id = data.get('conversation_id')

        if not conversation_id:
            return JsonResponse({
                'success': False,
                'error': '对话ID不能为空'
            }, status=400)

        try:
            conversation = Conversation.objects.get(id=conversation_id, user=request.user, is_active=True)
        except Conversation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': '对话不存在或无权访问'
            }, status=404)

        messages = HealthAdvice.objects.filter(conversation=conversation).order_by('created_at')
        if not messages.exists():
            return JsonResponse({
                'success': False,
                'error': '该对话暂无消息内容'
            }, status=400)

        conversation_content_parts = []
        for i, msg in enumerate(messages, 1):
            conversation_content_parts.append(f"【第{i}轮对话】")
            conversation_content_parts.append(f"时间: {msg.created_at.strftime('%Y-%m-%d %H:%M')}")
            conversation_content_parts.append(f"用户问题: {msg.question}")
            answer_preview = msg.answer[:500] + '...' if len(msg.answer) > 500 else msg.answer
            conversation_content_parts.append(f"AI回答: {answer_preview}")
            conversation_content_parts.append("")

        conversation_content = "\n".join(conversation_content_parts)

        prompt = build_ai_summary_prompt(conversation_content)

        provider = SystemSettings.get_setting('ai_doctor_provider', 'openai')
        api_url = None
        api_key = None
        model_name = None

        if provider == 'gemini':
            gemini_config = SystemSettings.get_gemini_config()
            api_key = gemini_config['api_key']
            model_name = gemini_config['model_name']
        else:
            api_url = SystemSettings.get_setting('ai_doctor_api_url')
            api_key = SystemSettings.get_setting('ai_doctor_api_key')
            model_name = SystemSettings.get_setting('ai_doctor_model_name')

        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        max_tokens = int(SystemSettings.get_setting('ai_doctor_max_tokens', '4000'))

        if provider == 'gemini':
            if not api_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Gemini API密钥未配置'
                }, status=500)
        else:
            if not api_url or not model_name:
                return JsonResponse({
                    'success': False,
                    'error': 'AI医生API未配置'
                }, status=500)

        is_baichuan = (
            provider == 'baichuan' or
            (api_url and 'baichuan' in api_url.lower()) or
            (model_name and 'Baichuan' in model_name)
        )

        def generate():
            """生成流式响应"""
            nonlocal conversation
            full_response = ""
            error_msg = None

            try:
                yield f"data: {json.dumps({'prompt': prompt}, ensure_ascii=False)}\n\n"

                if provider == 'gemini':
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    from langchain_core.messages import HumanMessage, AIMessage

                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        temperature=0.7,
                        timeout=timeout,
                        streaming=True
                    )

                    messages_list = []
                    if is_baichuan:
                        messages_list.append(AIMessage(content=build_ai_summary_prompt.__doc__ or ""))
                        messages_list.append(HumanMessage(content=prompt))
                    else:
                        messages_list.append(HumanMessage(content=prompt))

                    for chunk in llm.stream(messages_list):
                        if hasattr(chunk, 'content') and chunk.content:
                            chunk_content = chunk.content
                            if isinstance(chunk_content, list):
                                content_text = ""
                                for item in chunk_content:
                                    if isinstance(item, str):
                                        content_text += item
                                    elif hasattr(item, 'text'):
                                        content_text += item.text
                                    elif isinstance(item, dict) and 'text' in item:
                                        content_text += item['text']
                                content = content_text
                            else:
                                content = str(chunk_content)

                            full_response += content
                            yield f"data: {json.dumps({'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

                else:
                    from langchain_openai import ChatOpenAI
                    from langchain_core.messages import HumanMessage, AIMessage

                    base_url = api_url
                    if '/chat/completions' in base_url:
                        base_url = base_url.split('/chat/completions')[0].rstrip('/')
                    elif base_url.endswith('/'):
                        base_url = base_url.rstrip('/')

                    llm = ChatOpenAI(
                        model=model_name,
                        api_key=api_key or 'not-needed',
                        base_url=base_url,
                        temperature=0.3,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        streaming=True
                    )

                    messages_list = []
                    if is_baichuan:
                        from .llm_prompts import AI_SUMMARY_SYSTEM_PROMPT
                        messages_list.append(AIMessage(content=AI_SUMMARY_SYSTEM_PROMPT))
                        messages_list.append(HumanMessage(content=prompt.replace(AI_SUMMARY_SYSTEM_PROMPT + '\n\n', '')))
                    else:
                        messages_list.append(HumanMessage(content=prompt))

                    for chunk in llm.stream(messages_list):
                        if hasattr(chunk, 'content') and chunk.content:
                            content = chunk.content
                            full_response += content
                            yield f"data: {json.dumps({'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

            except Exception as e:
                error_msg = str(e)
                import traceback
                print(f"[stream_event_ai_summary] Error: {error_msg}")
                print(f"[stream_event_ai_summary] Trace: {traceback.format_exc()}")
                yield f"data: {json.dumps({'error': error_msg, 'done': True}, ensure_ascii=False)}\n\n"

            try:
                if full_response and not error_msg:
                    from django.utils import timezone
                    conversation.ai_summary = full_response
                    conversation.ai_summary_created_at = timezone.now()
                    conversation.save(update_fields=['ai_summary', 'ai_summary_created_at'])

                    yield f"data: {json.dumps({'saved': True, 'conversation_id': conversation.id}, ensure_ascii=False)}\n\n"

            except Exception as save_error:
                yield f"data: {json.dumps({'save_error': str(save_error)}, ensure_ascii=False)}\n\n"

        response = StreamingHttpResponse(generate(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_ai_summary(request, conversation_id):
    """获取对话的AI总结"""
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user, is_active=True)
        
        return JsonResponse({
            'success': True,
            'ai_summary': conversation.ai_summary,
            'ai_summary_created_at': conversation.ai_summary_created_at.strftime('%Y-%m-%d %H:%M:%S') if conversation.ai_summary_created_at else None,
            'has_summary': bool(conversation.ai_summary)
        })
    
    except Conversation.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '对话不存在或无权访问'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取总结失败: {str(e)}'
        }, status=500)


@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stream_event_ai_summary(request):
    """流式输出健康事件AI总结（使用LangChain）"""
    import json
    from django.http import StreamingHttpResponse
    from .models import SystemSettings, HealthEvent
    from .llm_prompts import build_event_ai_summary_prompt

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': '只支持POST请求'
        }, status=405)

    try:
        data = _safe_get_request_json(request)
        if not isinstance(data, dict):
            data = {}
        event_id = data.get('event_id')

        if not event_id:
            return JsonResponse({
                'success': False,
                'error': '事件ID不能为空'
            }, status=400)

        try:
            event = HealthEvent.objects.get(id=event_id, user=request.user)
        except HealthEvent.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': '事件不存在或无权访问'
            }, status=404)

        prompt = build_event_ai_summary_prompt(event)

        provider = SystemSettings.get_setting('ai_doctor_provider', 'openai')
        api_url = None
        api_key = None
        model_name = None

        if provider == 'gemini':
            gemini_config = SystemSettings.get_gemini_config()
            api_key = gemini_config['api_key']
            model_name = gemini_config['model_name']
        else:
            api_url = SystemSettings.get_setting('ai_doctor_api_url')
            api_key = SystemSettings.get_setting('ai_doctor_api_key')
            model_name = SystemSettings.get_setting('ai_doctor_model_name')

        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        max_tokens = int(SystemSettings.get_setting('ai_doctor_max_tokens', '4000'))

        if provider == 'gemini':
            if not api_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Gemini API密钥未配置'
                }, status=500)
        else:
            if not api_url or not model_name:
                return JsonResponse({
                    'success': False,
                    'error': 'AI医生API未配置'
                }, status=500)

        is_baichuan = (
            provider == 'baichuan' or
            (api_url and 'baichuan' in api_url.lower()) or
            (model_name and 'Baichuan' in model_name)
        )

        def generate():
            nonlocal event
            full_response = ""
            error_msg = None

            try:
                print(f"[stream_event_ai_summary] Starting LLM call for event_id: {event.id}")
                yield f"data: {json.dumps({'prompt': prompt}, ensure_ascii=False)}\n\n"

                if provider == 'gemini':
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    from langchain_core.messages import HumanMessage, AIMessage

                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        temperature=0.7,
                        timeout=timeout,
                        streaming=True
                    )

                    messages_list = [HumanMessage(content=prompt)]

                    for chunk in llm.stream(messages_list):
                        if hasattr(chunk, 'content') and chunk.content:
                            chunk_content = chunk.content
                            if isinstance(chunk_content, list):
                                content_text = ""
                                for item in chunk_content:
                                    if isinstance(item, str):
                                        content_text += item
                                    elif hasattr(item, 'text'):
                                        content_text += item.text
                                    elif isinstance(item, dict) and 'text' in item:
                                        content_text += item['text']
                                content = content_text
                            else:
                                content = str(chunk_content)

                            full_response += content
                            yield f"data: {json.dumps({'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

                else:
                    from langchain_openai import ChatOpenAI
                    from langchain_core.messages import HumanMessage, AIMessage

                    base_url = api_url
                    if '/chat/completions' in base_url:
                        base_url = base_url.split('/chat/completions')[0].rstrip('/')
                    elif base_url.endswith('/'):
                        base_url = base_url.rstrip('/')

                    llm = ChatOpenAI(
                        model=model_name,
                        api_key=api_key or 'not-needed',
                        base_url=base_url,
                        temperature=0.3,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        streaming=True
                    )

                    messages_list = []
                    if is_baichuan:
                        from .llm_prompts import EVENT_AI_SUMMARY_SYSTEM_PROMPT
                        messages_list.append(AIMessage(content=EVENT_AI_SUMMARY_SYSTEM_PROMPT))
                        messages_list.append(HumanMessage(content=prompt.replace(EVENT_AI_SUMMARY_SYSTEM_PROMPT + '\n\n', '')))
                    else:
                        messages_list.append(HumanMessage(content=prompt))

                    for chunk in llm.stream(messages_list):
                        if hasattr(chunk, 'content') and chunk.content:
                            content = chunk.content
                            full_response += content
                            yield f"data: {json.dumps({'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                    print(f"[stream_event_ai_summary] LLM streaming completed, full_response length: {len(full_response)}")

            except Exception as e:
                error_msg = str(e)
                import traceback
                print(f"[stream_event_ai_summary] LLM Error: {error_msg}")
                print(f"[stream_event_ai_summary] Trace: {traceback.format_exc()}")
                yield f"data: {json.dumps({'error': error_msg, 'done': True}, ensure_ascii=False)}\n\n"

            try:
                if full_response and not error_msg:
                    from django.utils import timezone
                    event_id = event.id
                    event = HealthEvent.objects.get(id=event_id)
                    event.ai_summary = full_response
                    event.ai_summary_created_at = timezone.now()
                    event.save(update_fields=['ai_summary', 'ai_summary_created_at'])

                    yield f"data: {json.dumps({'saved': True, 'event_id': event.id}, ensure_ascii=False)}\n\n"

            except Exception as save_error:
                import traceback
                yield f"data: {json.dumps({'save_error': str(save_error), 'trace': traceback.format_exc()}, ensure_ascii=False)}\n\n"

        response = StreamingHttpResponse(generate(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Connection'] = 'keep-alive'
        return response

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': f'生成AI总结失败: {str(e)}',
            'trace': traceback.format_exc()[:500]
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_event_ai_summary(request, event_id):
    """获取健康事件的AI总结"""
    try:
        event = HealthEvent.objects.get(id=event_id, user=request.user)
        
        return JsonResponse({
            'success': True,
            'ai_summary': event.ai_summary,
            'ai_summary_created_at': event.ai_summary_created_at.strftime('%Y-%m-%d %H:%M:%S') if event.ai_summary_created_at else None,
            'has_summary': bool(event.ai_summary)
        })
    
    except HealthEvent.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '事件不存在或无权访问'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取总结失败: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_checkup_ai_summary(request, checkup_id):
    """获取体检报告的AI总结"""
    from .models import HealthCheckup
    
    try:
        checkup = HealthCheckup.objects.get(id=checkup_id, user=request.user)
        
        return JsonResponse({
            'success': True,
            'ai_summary': checkup.ai_summary,
            'ai_summary_created_at': checkup.ai_summary_created_at.strftime('%Y-%m-%d %H:%M:%S') if checkup.ai_summary_created_at else None,
            'has_summary': bool(checkup.ai_summary)
        })
    
    except HealthCheckup.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '体检报告不存在或无权访问'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取总结失败: {str(e)}'
        }, status=500)


@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stream_checkup_ai_summary(request):
    """流式输出体检报告AI总结（使用LangChain）"""
    import json
    from django.http import StreamingHttpResponse
    from .models import SystemSettings, HealthCheckup
    from .llm_prompts import build_checkup_ai_summary_prompt, CHECKUP_AI_SUMMARY_SYSTEM_PROMPT

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': '只支持POST请求'
        }, status=405)

    try:
        data = _safe_get_request_json(request)
        if not isinstance(data, dict):
            data = {}
        checkup_id = data.get('checkup_id')

        if not checkup_id:
            return JsonResponse({
                'success': False,
                'error': '体检报告ID不能为空'
            }, status=400)

        try:
            checkup = HealthCheckup.objects.get(id=checkup_id, user=request.user)
        except HealthCheckup.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': '体检报告不存在或无权访问'
            }, status=404)

        prompt = build_checkup_ai_summary_prompt(checkup)

        provider = SystemSettings.get_setting('ai_doctor_provider', 'openai')
        api_url = None
        api_key = None
        model_name = None

        if provider == 'gemini':
            gemini_config = SystemSettings.get_gemini_config()
            api_key = gemini_config['api_key']
            model_name = gemini_config['model_name']
        else:
            api_url = SystemSettings.get_setting('ai_doctor_api_url')
            api_key = SystemSettings.get_setting('ai_doctor_api_key')
            model_name = SystemSettings.get_setting('ai_doctor_model_name')

        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        max_tokens = int(SystemSettings.get_setting('ai_doctor_max_tokens', '4000'))

        if provider == 'gemini':
            if not api_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Gemini API密钥未配置'
                }, status=500)
        else:
            if not api_url or not model_name:
                return JsonResponse({
                    'success': False,
                    'error': 'AI医生API未配置'
                }, status=500)

        is_baichuan = (
            provider == 'baichuan' or
            (api_url and 'baichuan' in api_url.lower()) or
            (model_name and 'Baichuan' in model_name)
        )

        def generate():
            nonlocal checkup
            full_response = ""
            error_msg = None

            try:
                print(f"[stream_checkup_ai_summary] Starting LLM call for checkup_id: {checkup.id}")
                yield f"data: {json.dumps({'prompt': prompt}, ensure_ascii=False)}\n\n"

                if provider == 'gemini':
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    from langchain_core.messages import HumanMessage, AIMessage

                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        temperature=0.7,
                        timeout=timeout,
                        streaming=True
                    )

                    messages_list = [HumanMessage(content=prompt)]

                    for chunk in llm.stream(messages_list):
                        if hasattr(chunk, 'content') and chunk.content:
                            chunk_content = chunk.content
                            if isinstance(chunk_content, list):
                                content_text = ""
                                for item in chunk_content:
                                    if isinstance(item, str):
                                        content_text += item
                                    elif hasattr(item, 'text'):
                                        content_text += item.text
                                    elif isinstance(item, dict) and 'text' in item:
                                        content_text += item['text']
                                content = content_text
                            else:
                                content = str(chunk_content)

                            full_response += content
                            yield f"data: {json.dumps({'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

                else:
                    from langchain_openai import ChatOpenAI
                    from langchain_core.messages import HumanMessage, AIMessage

                    base_url = api_url
                    if '/chat/completions' in base_url:
                        base_url = base_url.split('/chat/completions')[0].rstrip('/')
                    elif base_url.endswith('/'):
                        base_url = base_url.rstrip('/')

                    llm = ChatOpenAI(
                        model=model_name,
                        api_key=api_key or 'not-needed',
                        base_url=base_url,
                        temperature=0.3,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        streaming=True
                    )

                    messages_list = []
                    if is_baichuan:
                        messages_list.append(AIMessage(content=CHECKUP_AI_SUMMARY_SYSTEM_PROMPT))
                        messages_list.append(HumanMessage(content=prompt.replace(CHECKUP_AI_SUMMARY_SYSTEM_PROMPT + '\n\n', '')))
                    else:
                        messages_list.append(HumanMessage(content=prompt))

                    for chunk in llm.stream(messages_list):
                        if hasattr(chunk, 'content') and chunk.content:
                            content = chunk.content
                            full_response += content
                            yield f"data: {json.dumps({'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
                    print(f"[stream_checkup_ai_summary] LLM streaming completed, full_response length: {len(full_response)}")

            except Exception as e:
                error_msg = str(e)
                import traceback
                print(f"[stream_checkup_ai_summary] LLM Error: {error_msg}")
                print(f"[stream_checkup_ai_summary] Trace: {traceback.format_exc()}")
                yield f"data: {json.dumps({'error': error_msg, 'done': True}, ensure_ascii=False)}\n\n"

            try:
                if full_response and not error_msg:
                    from django.utils import timezone
                    checkup_id = checkup.id
                    checkup = HealthCheckup.objects.get(id=checkup_id)
                    checkup.ai_summary = full_response
                    checkup.ai_summary_created_at = timezone.now()
                    checkup.save(update_fields=['ai_summary', 'ai_summary_created_at'])

                    yield f"data: {json.dumps({'saved': True, 'checkup_id': checkup.id}, ensure_ascii=False)}\n\n"

            except Exception as save_error:
                import traceback
                yield f"data: {json.dumps({'save_error': str(save_error), 'trace': traceback.format_exc()}, ensure_ascii=False)}\n\n"

        response = StreamingHttpResponse(generate(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Connection'] = 'keep-alive'
        return response

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': f'生成AI总结失败: {str(e)}',
            'trace': traceback.format_exc()[:500]
        }, status=500)


def process_document_background(processing_id, file_path):
    """后台处理文档"""
    import threading
    current_thread = threading.current_thread()
    print(f"[{current_thread.name}] 开始处理文档，处理ID: {processing_id}")

    try:
        from .services import DocumentProcessingService

        # 获取处理记录
        document_processing = DocumentProcessing.objects.get(id=processing_id)
        print(f"[{current_thread.name}] 获取处理记录成功: {document_processing.health_checkup.hospital}")

        # 创建处理服务
        service = DocumentProcessingService(document_processing)
        print(f"[{current_thread.name}] 创建处理服务成功")

        # 执行处理
        print(f"[{current_thread.name}] 开始执行完整处理流程...")
        result = service.process_document(file_path)
        print(f"[{current_thread.name}] 处理完成，结果: {result}")

        # 清理临时文件
        try:
            os.unlink(file_path)
            print(f"[{current_thread.name}] 清理临时文件成功")
        except:
            print(f"[{current_thread.name}] 清理临时文件失败，忽略")

        return result

    except Exception as e:
        print(f"[{current_thread.name}] 处理失败: {str(e)}")

        # 清理临时文件
        try:
            os.unlink(file_path)
        except:
            pass

        # 更新错误状态
        try:
            document_processing = DocumentProcessing.objects.get(id=processing_id)
            document_processing.status = 'failed'
            document_processing.error_message = str(e)
            document_processing.save()
            print(f"[{current_thread.name}] 更新错误状态成功")
        except Exception as save_error:
            print(f"[{current_thread.name}] 更新错误状态失败: {str(save_error)}")

        return None


@require_http_methods(["GET"])
def get_processing_status(request, processing_id):
    """获取处理状态"""
    try:
        # 移除用户认证要求，允许前端JavaScript访问
        document_processing = get_object_or_404(
            DocumentProcessing,
            id=processing_id
        )

        # 获取相关的健康指标数量
        indicators_count = HealthIndicator.objects.filter(
            checkup=document_processing.health_checkup
        ).count()

        # 获取状态消息
        status_messages = {
            'pending': '等待开始处理...',
            'uploading': '正在上传文件...',
            'ocr_processing': '正在进行OCR文字识别...',
            'ai_processing': '正在进行AI智能分析...',
            'saving_data': '正在保存数据到数据库...',
            'completed': '处理完成！',
            'failed': '处理失败'
        }
        status_message = status_messages.get(document_processing.status, '处理中...')

        response_data = {
            'status': document_processing.status,
            'progress': document_processing.progress,
            'status_message': status_message,
            'error_message': document_processing.error_message,
            'indicators_count': indicators_count,
            'created_at': document_processing.created_at.isoformat(),
            'updated_at': document_processing.updated_at.isoformat(),
            'health_checkup_id': document_processing.health_checkup.id,
        }

        # 如果处理完成，提供处理时间
        if document_processing.processing_time:
            response_data['processing_time'] = str(document_processing.processing_time)

        # 提供OCR结果
        if document_processing.ocr_result:
            response_data['ocr_result'] = document_processing.ocr_result
            response_data['ocr_result_length'] = len(document_processing.ocr_result)
        else:
            response_data['ocr_result'] = None
            response_data['ocr_result_length'] = 0

        # 提供LLM结果
        if document_processing.ai_result:
            response_data['ai_result'] = document_processing.ai_result
            response_data['has_ai_result'] = True
            # 检查AI结果中的指标数量
            if isinstance(document_processing.ai_result, dict) and 'indicators' in document_processing.ai_result:
                response_data['ai_indicators_count'] = len(document_processing.ai_result['indicators'])
                response_data['ai_indicators'] = document_processing.ai_result['indicators']
            else:
                response_data['ai_indicators_count'] = 0
                response_data['ai_indicators'] = []
        else:
            response_data['ai_result'] = None
            response_data['has_ai_result'] = False
            response_data['ai_indicators_count'] = 0
            response_data['ai_indicators'] = []

        # 提供多模态模型结果
        if document_processing.vl_model_result:
            response_data['vl_model_result'] = document_processing.vl_model_result
            response_data['has_vl_model_result'] = True
            # 检查VL模型结果中的指标数量
            if isinstance(document_processing.vl_model_result, dict) and 'indicators' in document_processing.vl_model_result:
                response_data['vl_indicators_count'] = len(document_processing.vl_model_result['indicators'])
            else:
                response_data['vl_indicators_count'] = 0
        else:
            response_data['vl_model_result'] = None
            response_data['has_vl_model_result'] = False
            response_data['vl_indicators_count'] = 0

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取状态失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_processing_history(request):
    """获取处理历史"""
    try:
        # 获取用户最近的处理记录
        processings = DocumentProcessing.objects.filter(
            user=request.user
        ).order_by('-created_at')[:10]

        history = []
        for proc in processings:
            indicators_count = HealthIndicator.objects.filter(
                checkup=proc.health_checkup
            ).count()

            history.append({
                'id': proc.id,
                'status': proc.status,
                'progress': proc.progress,
                'hospital': proc.health_checkup.hospital,
                'checkup_date': proc.health_checkup.checkup_date.isoformat(),
                'indicators_count': indicators_count,
                'created_at': proc.created_at.isoformat(),
                'error_message': proc.error_message,
            })

        return JsonResponse({
            'success': True,
            'history': history
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取历史记录失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_ocr_result(request, processing_id):
    """获取OCR结果"""
    try:
        document_processing = get_object_or_404(
            DocumentProcessing,
            id=processing_id,
            user=request.user
        )

        if not document_processing.ocr_result:
            return JsonResponse({
                'success': False,
                'error': 'OCR结果尚未生成'
            }, status=404)

        return JsonResponse({
            'success': True,
            'ocr_result': document_processing.ocr_result
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取OCR结果失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_ai_result(request, processing_id):
    """获取AI处理结果"""
    try:
        document_processing = get_object_or_404(
            DocumentProcessing,
            id=processing_id,
            user=request.user
        )

        if not document_processing.ai_result:
            return JsonResponse({
                'success': False,
                'error': 'AI处理结果尚未生成'
            }, status=404)

        return JsonResponse({
            'success': True,
            'ai_result': document_processing.ai_result
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取AI结果失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_common_hospitals(request):
    """获取用户已有记录的体检机构列表"""
    try:
        from django.db.models import Q, Count, Max

        # 按医院名称分组，统计使用次数，并获取最近使用日期
        user_hospitals = HealthCheckup.objects.filter(
            user=request.user
        ).exclude(
            Q(hospital__isnull=True) | Q(hospital='')
        ).exclude(
            hospital='未知机构'
        ).values('hospital').annotate(
            usage_count=Count('id'),
            last_used=Max('checkup_date')
        ).order_by('-usage_count', 'hospital')

        # 获取机构名称和统计
        hospitals_data = []
        for item in user_hospitals:
            hospitals_data.append({
                'name': item['hospital'],
                'usage_count': item['usage_count'],
                'last_used': item['last_used'].strftime('%Y-%m-%d')
            })

        # 如果用户没有记录，返回空数组
        if not hospitals_data:
            return JsonResponse({
                'success': True,
                'hospitals': [],
                'count': 0,
                'message': '暂无历史记录'
            })

        return JsonResponse({
            'success': True,
            'hospitals': hospitals_data,
            'count': len(hospitals_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取用户体检机构列表失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_conversations(request):
    """获取用户的对话列表"""
    try:
        conversations = Conversation.get_user_conversations(request.user, limit=20)
        conversations_data = []

        for conversation in conversations:
            latest_message = conversation.get_latest_message()
            message_count = conversation.get_message_count()

            # 只显示有消息的对话（过滤掉空对话，防止显示无消息的对话记录）
            if message_count > 0:
                conversation_data = {
                    'id': conversation.id,
                    'title': conversation.title,
                    'created_at': conversation.created_at.strftime('%Y-%m-%d %H:%M'),
                    'updated_at': conversation.updated_at.strftime('%Y-%m-%d %H:%M'),
                    'message_count': message_count,
                }

                # 添加最新消息信息
                if latest_message:
                    conversation_data['latest_message'] = {
                        'question': latest_message.question,
                        'created_at': latest_message.created_at.strftime('%Y-%m-%d %H:%M')
                    }

                conversations_data.append(conversation_data)

        return JsonResponse({
            'success': True,
            'conversations': conversations_data,
            'count': len(conversations_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取对话列表失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_conversation_messages(request, conversation_id):
    """获取对话中的所有消息"""
    try:
        # 验证对话属于当前用户
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)

        # 获取对话中的所有消息
        messages = HealthAdvice.get_conversation_messages(conversation_id)
        messages_data = []

        for message in messages:
            messages_data.append({
                'id': message.id,
                'question': message.question,
                'answer': message.answer,
                'prompt_sent': message.prompt_sent or '',
                'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })

        return JsonResponse({
            'success': True,
            'conversation': {
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': conversation.updated_at.strftime('%Y-%m-%d %H:%M'),
            },
            'messages': messages_data,
            'count': len(messages_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取对话消息失败: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
@login_required
def create_new_conversation(request):
    """创建新对话"""
    try:
        from datetime import datetime
        import json

        data = json.loads(request.body)
        title = data.get('title', '').strip()

        if not title:
            title = f"新对话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        conversation = Conversation.create_new_conversation(request.user, title)

        return JsonResponse({
            'success': True,
            'conversation': {
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at.strftime('%Y-%m-%d %H:%M'),
                'updated_at': conversation.updated_at.strftime('%Y-%m-%d %H:%M'),
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'创建新对话失败: {str(e)}'
        }, status=500)


@require_http_methods(["DELETE"])
@login_required
def delete_conversation(request, conversation_id):
    """删除对话"""
    try:
        # 验证对话属于当前用户
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)

        # 直接删除对话及其关联的消息
        conversation.delete()

        return JsonResponse({
            'success': True,
            'message': '对话已删除'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'删除对话失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_advices(request):
    """获取用户的咨询历史列表（用于前端刷新）"""
    try:
        from django.template.loader import render_to_string
        from .models import HealthAdvice, Conversation

        user_advices = []

        # 获取用户的活跃对话
        conversations = Conversation.get_user_conversations(request.user)

        for conversation in conversations:
            latest_message = conversation.get_latest_message()
            message_count = conversation.get_message_count()
            
            # 只显示有消息的对话（过滤掉空对话，防止显示无消息的对话记录）
            if message_count > 0 and latest_message:
                user_advices.append({
                    'id': conversation.id,
                    'is_conversation': True,
                    'title': conversation.title,
                    'message_count': message_count,
                    'latest_question': latest_message.question[:50] + ('...' if len(latest_message.question) > 50 else ''),
                    'answer': latest_message.answer[:100] + ('...' if len(latest_message.answer) > 100 else ''),
                    'updated_at': conversation.updated_at,
                })

        # 如果没有对话，显示旧的HealthAdvice记录
        if not user_advices:
            old_advices = HealthAdvice.objects.filter(
                user=request.user,
                conversation__isnull=True  # 只获取没有关联对话的旧记录
            ).order_by('-created_at')[:10]

            for advice in old_advices:
                user_advices.append({
                    'id': advice.id,
                    'is_conversation': False,
                    'title': advice.question[:30] + ('...' if len(advice.question) > 30 else ''),
                    'message_count': 1,
                    'latest_question': advice.question,
                    'answer': advice.answer[:100] + ('...' if len(advice.answer) > 100 else ''),
                    'updated_at': advice.created_at,
                })

        # 渲染HTML
        html_content = render_to_string(
            'medical_records/ai_advice_history.html',
            {'user_advices': user_advices}
        )

        return JsonResponse({
            'success': True,
            'html': html_content,
            'count': len(user_advices)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取咨询历史失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
def check_services_status(request):
    """检查所有服务状态"""
    try:
        from .services import get_mineru_api_status, get_llm_api_status, get_vision_model_api_status

        # 检查各个服务状态
        ocr_status = get_mineru_api_status()
        llm_status = get_llm_api_status()
        vl_status = get_vision_model_api_status()

        # 获取PDF OCR工作流设置
        from .models import SystemSettings
        pdf_ocr_workflow = SystemSettings.get_pdf_ocr_workflow()

        response_data = {
            'ocr_status': 'online' if ocr_status else 'offline',
            'llm_status': 'online' if llm_status else 'offline',
            'vlm_status': 'online' if vl_status else 'offline',
            'pdf_ocr_workflow': pdf_ocr_workflow,
            'supported_workflows': ['ocr_llm', 'vlm_transformers', 'vl_model']
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'检查服务状态失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_user_checkups(request):
    """获取用户的体检报告列表"""
    try:
        from django.db.models import Count

        # 获取用户的所有体检报告，按日期降序排列
        checkups = HealthCheckup.objects.filter(
            user=request.user
        ).annotate(
            indicator_count=Count('indicators')
        ).order_by('-checkup_date')

        checkups_data = []
        for checkup in checkups:
            checkups_data.append({
                'id': checkup.id,
                'checkup_date': checkup.checkup_date.strftime('%Y-%m-%d'),
                'hospital': checkup.hospital,
                'indicator_count': checkup.indicator_count
            })

        return JsonResponse({
            'success': True,
            'checkups': checkups_data,
            'count': len(checkups_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取体检报告列表失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_checkup_detail(request, checkup_id):
    """获取单个体检报告的详细信息"""
    try:
        checkup = HealthCheckup.objects.get(id=checkup_id, user=request.user)
        
        indicators = checkup.indicators.all()
        indicators_data = []
        for indicator in indicators:
            indicators_data.append({
                'id': indicator.id,
                'indicator_type': indicator.indicator_type,
                'indicator_name': indicator.indicator_name,
                'value': indicator.value,
                'unit': indicator.unit,
                'reference_range': indicator.reference_range,
                'status': indicator.status,
            })
        
        return JsonResponse({
            'success': True,
            'checkup': {
                'id': checkup.id,
                'checkup_date': checkup.checkup_date.strftime('%Y-%m-%d'),
                'hospital': checkup.hospital,
                'report_file': checkup.report_file.url if checkup.report_file else None,
                'notes': checkup.notes,
            },
            'indicators': indicators_data,
            'count': len(indicators_data)
        })
        
    except HealthCheckup.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '体检报告不存在'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取体检报告详情失败: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
@login_required
def integrate_data(request):
    """AI智能整合多份体检报告的数据"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        import json
        import re
        import time
        from .services import call_llm_for_integration
        from .models import SystemSettings

        logger.info(f"\n{'='*80}")
        logger.info(f"[数据整合] API调用开始")
        logger.info(f"[数据整合] 用户: {request.user.username}")

        # 获取请求数据
        data = json.loads(request.body)
        checkup_ids = data.get('checkup_ids', [])
        user_prompt = data.get('user_prompt', '').strip()  # 获取用户提示词（可选）

        logger.info(f"[数据整合] 选择的报告ID: {checkup_ids}")
        logger.info(f"[数据整合] 报告数量: {len(checkup_ids)}")

        if user_prompt:
            logger.info(f"[数据整合] ✓ 用户提供了自定义提示词")
            logger.info(f"[数据整合] 用户提示词内容: {user_prompt}")
        else:
            logger.info(f"[数据整合] - 未提供用户提示词，使用默认规则")

        if not checkup_ids:
            return JsonResponse({
                'success': False,
                'error': '请选择要整合的体检报告'
            }, status=400)

        # 验证报告所有权
        checkups = HealthCheckup.objects.filter(
            id__in=checkup_ids,
            user=request.user
        )

        if checkups.count() != len(checkup_ids):
            logger.info(f"[数据整合] ✗ 报告验证失败")
            return JsonResponse({
                'success': False,
                'error': '部分报告不存在或无权访问'
            }, status=403)

        logger.info(f"[数据整合] ✓ 报告验证通过")

        # 获取所有指标
        indicators = HealthIndicator.objects.filter(
            checkup__in=checkups
        ).select_related('checkup')

        logger.info(f"[数据整合] 获取到指标总数: {indicators.count()}")

        # 按指标名称分组（模糊匹配）
        indicators_by_name = {}
        for indicator in indicators:
            name_key = indicator.indicator_name.lower().strip()
            if name_key not in indicators_by_name:
                indicators_by_name[name_key] = []
            indicators_by_name[name_key].append(indicator)

        logger.info(f"[数据整合] 指标分组数: {len(indicators_by_name)}")

        # 准备发送给LLM的数据
        indicators_summary = []

        for name_key, inds in indicators_by_name.items():
            # 收集该指标的所有变体
            variants = []

            for ind in inds:
                variants.append({
                    'id': ind.id,
                    'name': ind.indicator_name,
                    'value': ind.value,
                    'unit': ind.unit,
                    'reference_range': ind.reference_range,  # 仅用于LLM参考，不返回
                    'status': ind.status,
                    'type': ind.indicator_type
                })

            indicators_summary.append({
                'key': name_key,
                'variants': variants
            })

        # 构建Prompt，使用统一的提示词配置
        indicators_data_json = json.dumps(indicators_summary, ensure_ascii=False, indent=2)
        system_prompt, user_prompt = build_data_integration_prompt(indicators_data_json, user_prompt)

        logger.info(f"[数据整合] Prompt构建完成，长度: {len(user_prompt)} 字符")
        logger.info(f"[数据整合] 开始调用LLM...")

        # 获取LLM提供商配置
        llm_config = SystemSettings.get_llm_config()
        llm_provider = llm_config.get('provider', 'openai')
        logger.info(f"[数据整合] LLM提供商: {llm_provider}")

        # 调用LLM
        try:
            llm_start = time.time()

            if llm_provider == 'gemini':
                # 使用 Gemini API
                logger.info(f"[数据整合] 使用 Gemini API")
                from .services import call_gemini_api
                # Gemini不使用system_message，直接使用prompt
                timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
                llm_response = call_gemini_api(user_prompt, timeout=timeout)
            else:
                # 使用 OpenAI 兼容格式
                logger.info(f"[数据整合] 使用 OpenAI 兼容格式")
                # 使用统一的AI模型超时配置
                timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
                llm_response = call_llm_for_integration(system_prompt, user_prompt, timeout=timeout)

            llm_end = time.time()
            logger.info(f"[数据整合] ✓ LLM调用完成，耗时: {llm_end - llm_start:.2f}秒")
        except Exception as e:
            logger.info(f"[数据整合] ✗ LLM调用失败: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': f'调用LLM失败: {str(e)}'
            }, status=500)

        # 解析LLM响应
        try:
            logger.info(f"[数据整合] 开始解析LLM响应...")

            # 清理LLM响应中的thinking标签和思考过程
            cleaned_response = llm_response.strip()

            # 移除markdown代码块标记
            if cleaned_response.startswith('```'):
                logger.info(f"[数据整合] 检测到markdown标记，正在清理...")
                cleaned_response = re.sub(r'^```\w*\n?', '', cleaned_response)
                cleaned_response = re.sub(r'\n?```$', '', cleaned_response)
                logger.info(f"[数据整合] Markdown清理完成")

            # 移除thinking标签和思考过程
            thinking_patterns = [
                (r'<thought>[\s\S]*?</thought>', '', re.IGNORECASE),
                (r'<thinking>[\s\S]*?</thinking>', '', re.IGNORECASE),
                (r'<think>[\s\S]*?</think>', '', re.IGNORECASE),
                (r'思考过程[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
                (r'分析[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
                (r'让我先分析[\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
                (r'分析如下[:：][\s\S]*?(?=\n\s*\{)', '', re.IGNORECASE),
            ]

            for pattern, replacement, *flags in thinking_patterns:
                flags = flags[0] if flags else 0
                old_text = cleaned_response
                cleaned_response = re.sub(pattern, replacement, cleaned_response, flags=flags)
                if old_text != cleaned_response:
                    logger.info(f"[数据整合] 清理thinking标签/思考过程: 移除了 {len(old_text) - len(cleaned_response)} 个字符")

            cleaned_response = cleaned_response.strip()

            # 智能提取JSON对象
            result_json = None

            # 方法1: 尝试直接解析
            try:
                result_json = json.loads(cleaned_response)
                logger.info(f"[数据整合] ✓ JSON解析成功（直接解析）")
            except json.JSONDecodeError:
                logger.info(f"[数据整合] 直接解析失败，尝试提取JSON对象...")

            # 方法2: 提取所有JSON对象，找到包含changes的有效JSON
            if not result_json:
                json_objects = extract_json_objects(cleaned_response)
                logger.info(f"[数据整合] 找到 {len(json_objects)} 个JSON对象")

                for i, json_str in enumerate(json_objects):
                    try:
                        parsed = json.loads(json_str)
                        if 'changes' in parsed:
                            result_json = parsed
                            logger.info(f"[数据整合] ✓ JSON提取成功（对象{i+1}，包含changes字段）")
                            break
                    except json.JSONDecodeError:
                        continue

            if not result_json:
                logger.info(f"[数据整合] ✗ 无法提取有效的JSON")
                raise Exception("无法从LLM响应中提取有效的JSON对象")

            changes = result_json.get('changes', [])
            logger.info(f"[数据整合] LLM返回的变更数量: {len(changes)}")

            # 验证返回的changes格式
            validated_changes = []

            for change in changes:
                if not isinstance(change, dict):
                    logger.info(f"[数据整合] 跳过无效变更（非字典）")
                    continue

                indicator_id = change.get('indicator_id')
                if not indicator_id:
                    logger.info(f"[数据整合] 跳过无效变更（无indicator_id）")
                    continue

                # 打印LLM返回的原始数据
                logger.info(f"[数据整合] 处理指标{indicator_id}，LLM返回: {change}")

                # 验证indicator_id存在
                try:
                    indicator = HealthIndicator.objects.get(id=indicator_id)
                except HealthIndicator.DoesNotExist:
                    logger.info(f"[数据整合] 跳过无效变更（indicator_id={indicator_id}不存在）")
                    continue

                # 原始数据（用于前端显示）
                original_data = {
                    'indicator_name': indicator.indicator_name,
                    'value': indicator.value,
                    'unit': indicator.unit or '',
                    'reference_range': indicator.reference_range or '',
                    'status': indicator.status,
                    'indicator_type': indicator.indicator_type or ''
                }

                # 直接使用LLM返回的字段（不再检查null或比较值）
                # 注意：reference_range不再处理
                actual_changes = {}

                if 'indicator_name' in change:
                    actual_changes['indicator_name'] = change['indicator_name']
                    logger.info(f"[数据整合]   指标{indicator_id}: 名称 {indicator.indicator_name} -> {change['indicator_name']}")

                if 'value' in change:
                    actual_changes['value'] = str(change['value'])
                    logger.info(f"[数据整合]   指标{indicator_id}: 值 {indicator.value} -> {change['value']}")

                if 'unit' in change:
                    actual_changes['unit'] = change['unit']
                    logger.info(f"[数据整合]   指标{indicator_id}: 单位 {indicator.unit} -> {change['unit']}")

                # 忽略reference_range字段（即使LLM返回也不处理）
                if 'reference_range' in change:
                    logger.info(f"[数据整合]   指标{indicator_id}: 参考范围被忽略（系统已禁用此字段更新）")

                if 'status' in change:
                    actual_changes['status'] = change['status']
                    logger.info(f"[数据整合]   指标{indicator_id}: 状态 {indicator.status} -> {change['status']}")

                if 'indicator_type' in change:
                    actual_changes['indicator_type'] = change['indicator_type']
                    logger.info(f"[数据整合]   指标{indicator_id}: 分类 {indicator.indicator_type} -> {change['indicator_type']}")

                # 提取reason字段（如果存在）
                reason = change.get('reason', '')

                # 添加到变更列表
                validated_changes.append({
                    'indicator_id': indicator_id,
                    'original': original_data,
                    'changes': actual_changes,
                    'reason': reason  # 保存修改理由
                })

            logger.info(f"[数据整合] ✓ 验证完成，有效变更: {len(validated_changes)}")

            # 收集已变更的indicator_id
            changed_indicator_ids = set(change['indicator_id'] for change in validated_changes)
            logger.info(f"[数据整合] 已变更指标ID: {changed_indicator_ids}")

            # 添加所有未变更的指标
            unchanged_indicators = []
            for indicator in indicators:
                if indicator.id not in changed_indicator_ids:
                    original_data = {
                        'indicator_name': indicator.indicator_name,
                        'value': indicator.value,
                        'unit': indicator.unit or '',
                        'reference_range': indicator.reference_range or '',
                        'status': indicator.status,
                        'indicator_type': indicator.indicator_type or ''
                    }
                    unchanged_indicators.append({
                        'indicator_id': indicator.id,
                        'original': original_data,
                        'changes': {},  # 空表示无变更
                        'unchanged': True  # 标记为无变化
                    })

            logger.info(f"[数据整合] 未变更指标数量: {len(unchanged_indicators)}")

            # 合并变更和未变更的指标
            all_indicators = validated_changes + unchanged_indicators

            # 构建响应
            logger.info(f"[数据整合] ✓ 数据整合完成")
            print(f"{'='*80}\n")

            return JsonResponse({
                'success': True,
                'total_indicators': indicators.count(),
                'unique_groups': len(indicators_by_name),
                'changed_count': len(validated_changes),
                'unchanged_count': len(unchanged_indicators),
                'changes': validated_changes,  # 只包含变更的
                'all_indicators': all_indicators  # 包含所有指标
            })

        except json.JSONDecodeError as e:
            logger.info(f"[数据整合] ✗ JSON解析错误: {str(e)}")
            logger.info(f"[数据整合] LLM响应内容:\n{llm_response[:1000]}")

            # 检查响应是否可能被截断
            response_len = len(llm_response)
            logger.info(f"[数据整合] 响应总长度: {response_len} 字符")

            # 检查响应末尾是否为不完整的JSON
            trimmed = llm_response.strip()
            if not trimmed.endswith('}') and not trimmed.endswith(']'):
                logger.info(f"[数据整合] ⚠️  检测到响应可能被截断（不以}}或]结尾）")
                error_msg = f'LLM响应被截断，max_tokens设置可能不足。当前响应长度: {response_len} 字符。建议增加max_tokens参数或减少数据量。错误详情: {str(e)}'
            else:
                error_msg = f'LLM返回格式错误: {str(e)}'

            return JsonResponse({
                'success': False,
                'error': error_msg,
                'response_length': response_len,
                'llm_response_preview': llm_response[:1000]
            }, status=500)
        except Exception as e:
            import traceback
            logger.info(f"[数据整合] ✗ 处理失败: {str(e)}")
            logger.info(f"[数据整合] 错误追踪:\n{traceback.format_exc()[:1000]}")
            return JsonResponse({
                'success': False,
                'error': f'解析LLM响应失败: {str(e)}',
                'traceback': traceback.format_exc()[:1000],
                'llm_response': llm_response[:1000]
            }, status=500)

    except Exception as e:
        import traceback
        logger.info(f"[数据整合] ✗ 严重错误: {str(e)}")
        logger.info(f"[数据整合] 错误追踪:\n{traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': f'数据整合失败: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)


@require_http_methods(["POST"])
@login_required
def apply_integration(request):
    """应用数据整合结果到数据库（仅更新指标，不合并报告）"""
    try:
        from django.db import transaction
        import time

        print(f"\n{'='*80}")
        print(f"[应用更新] 开始")
        print(f"[应用更新] 用户: {request.user.username}")

        data = json.loads(request.body)
        changes = data.get('changes', [])

        print(f"[应用更新] 待应用的变更数量: {len(changes)}")

        if not changes:
            print(f"[应用更新] ✗ 没有要应用的更改")
            return JsonResponse({
                'success': False,
                'error': '没有要应用的更改'
            }, status=400)

        updated_count = 0
        update_details = []
        skipped_count = 0

        with transaction.atomic():
            print(f"[应用更新] 开始事务处理...")
            start_time = time.time()

            for idx, change in enumerate(changes, 1):
                indicator_id = change.get('indicator_id')
                change_data = change.get('changes', {})

                print(f"[应用更新] {idx}/{len(changes)} 处理指标 {indicator_id}...")

                try:
                    indicator = HealthIndicator.objects.get(
                        id=indicator_id,
                        checkup__user=request.user
                    )
                except HealthIndicator.DoesNotExist:
                    print(f"[应用更新]   ✗ 跳过（指标不存在）")
                    skipped_count += 1
                    continue

                before_state = {
                    'indicator_name': indicator.indicator_name,
                    'value': indicator.value,
                    'unit': indicator.unit,
                    'reference_range': indicator.reference_range,
                    'status': indicator.status,
                    'indicator_type': indicator.indicator_type
                }

                print(f"[应用更新]   原始: {indicator.indicator_name} = {indicator.value} {indicator.unit or ''}")

                if change_data.get('indicator_name'):
                    print(f"[应用更新]   -> 名称: {indicator.indicator_name} -> {change_data['indicator_name']}")
                    indicator.indicator_name = change_data['indicator_name']

                if change_data.get('value'):
                    print(f"[应用更新]   -> 值: {indicator.value} -> {change_data['value']}")
                    indicator.value = change_data['value']

                if change_data.get('unit') is not None:
                    print(f"[应用更新]   -> 单位: {indicator.unit} -> {change_data['unit']}")
                    indicator.unit = change_data['unit']

                if change_data.get('reference_range') is not None:
                    print(f"[应用更新]   -> 参考范围: {indicator.reference_range} -> {change_data['reference_range']}")
                    indicator.reference_range = change_data['reference_range']

                if change_data.get('status'):
                    print(f"[应用更新]   -> 状态: {indicator.status} -> {change_data['status']}")
                    indicator.status = change_data['status']

                if change_data.get('indicator_type'):
                    print(f"[应用更新]   -> 分类: {indicator.indicator_type} -> {change_data['indicator_type']}")
                    indicator.indicator_type = change_data['indicator_type']

                indicator.save()
                updated_count += 1
                print(f"[应用更新]   ✓ 保存成功")

                update_details.append({
                    'indicator_id': indicator_id,
                    'checkup_date': indicator.checkup.checkup_date.strftime('%Y-%m-%d'),
                    'hospital': indicator.checkup.hospital,
                    'before': before_state,
                    'after': {
                        'indicator_name': indicator.indicator_name,
                        'value': indicator.value,
                        'unit': indicator.unit,
                        'reference_range': indicator.reference_range,
                        'status': indicator.status,
                        'indicator_type': indicator.indicator_type
                    },
                    'reason': change.get('reason', '')
                })

            print(f"[应用更新] 数据整合模式：仅更新指标，不合并报告、不打包ZIP、不删除记录")

        end_time = time.time()
        duration = end_time - start_time

        print(f"[应用更新] ✓ 所有更新完成")
        print(f"[应用更新] 成功更新: {updated_count} 个指标，跳过: {skipped_count} 个")
        print(f"[应用更新] 耗时: {duration:.2f}秒")
        print(f"{'='*80}\n")

        return JsonResponse({
            'success': True,
            'updated_count': updated_count,
            'update_details': update_details
        })

    except Exception as e:
        import traceback
        print(f"[应用更新] ✗ 更新失败: {str(e)}")
        print(f"[应用更新] 错误追踪:\n{traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': f'应用更改失败: {str(e)}',
            'traceback': traceback.format_exc()
        }, status=500)

@csrf_exempt
@api_view(['POST'])
@permission_classes([IsAuthenticated])  # 使用Token认证，兼容小程序
def stream_ai_advice(request):
    """流式输出AI健康建议（使用LangChain）"""
    import json
    import traceback
    from django.http import StreamingHttpResponse
    from .models import SystemSettings

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': '只支持POST请求'
        }, status=405)

    try:
        # 获取请求数据
        data = _safe_get_request_json(request)
        if not isinstance(data, dict):
            data = {}
        question = data.get('question', '').strip()

        if not question:
            return JsonResponse({
                'success': False,
                'error': '问题不能为空'
            }, status=400)

        # 获取对话ID（可选）
        conversation_id = data.get('conversation_id')
        conversation_mode = data.get('conversation_mode', 'new_conversation')
        report_mode = data.get('report_mode')
        medication_mode = data.get('medication_mode')
        event_mode = data.get('event_mode', 'no_event')
        selected_event_id = data.get('selected_event')
        conversation = None

        # 只在非新对话模式下才加载历史对话
        if conversation_mode != 'new_conversation' and conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, user=request.user, is_active=True)
            except Conversation.DoesNotExist:
                pass

        # 获取选择的事件（优先处理）
        selected_reports = None
        selected_medications = None
        selected_event_id_for_save = None
        
        # 继续对话时，如果用户没有显式修改事件选择，则复用上次的选择
        if conversation_mode != 'new_conversation' and conversation:
            from .models import HealthAdvice
            latest_advice = HealthAdvice.objects.filter(
                conversation=conversation,
                user=request.user
            ).order_by('-created_at').first()

            if latest_advice:
                # 如果用户没有显式修改事件模式，并且上次有选择事件，则复用
                if (event_mode == 'no_event' or event_mode is None) and latest_advice.selected_event:
                    try:
                        selected_event_id = latest_advice.selected_event
                        selected_event_id_for_save = latest_advice.selected_event
                        event_mode = 'select_event'
                        print(f"[Web流式AI] 复用上次选择的事件ID: {selected_event_id}")
                    except Exception as e:
                        print(f"[Web流式AI] 复用上事件失败: {e}")
        
        if event_mode == 'select_event' and selected_event_id:
            selected_event_id_for_save = selected_event_id
            try:
                from .models import HealthEvent, EventItem
                selected_event = HealthEvent.objects.get(id=selected_event_id, user=request.user)
                print(f"[Web流式AI] 选择了事件: {selected_event.name} (ID: {selected_event.id})")
                
                # 从事件中提取报告和药单
                event_items = selected_event.get_all_items()
                selected_reports_list = []
                selected_medications_list = []
                
                for item in event_items:
                    model_name = item.content_type.model
                    
                    if model_name == 'healthcheckup':
                        try:
                            from .models import HealthCheckup
                            checkup = HealthCheckup.objects.get(id=item.object_id, user=request.user)
                            selected_reports_list.append(checkup)
                        except HealthCheckup.DoesNotExist:
                            continue
                    elif model_name == 'medication':
                        try:
                            from .models import Medication
                            medication = Medication.objects.get(id=item.object_id, user=request.user, is_active=True)
                            selected_medications_list.append(medication)
                        except Medication.DoesNotExist:
                            continue
                    elif model_name == 'medicationgroup':
                        try:
                            from .models import MedicationGroup, Medication
                            group = MedicationGroup.objects.get(id=item.object_id, user=request.user)
                            group_medications = Medication.objects.filter(group=group, user=request.user, is_active=True)
                            selected_medications_list.extend(group_medications)
                        except MedicationGroup.DoesNotExist:
                            continue
                
                # 去重
                selected_reports_list = list(set(selected_reports_list))
                selected_medications_list = list(set(selected_medications_list))
                
                print(f"[Web流式AI] 从事件中获取了 {len(selected_reports_list)} 份报告，{len(selected_medications_list)} 个药单")
                
                if selected_reports_list:
                    from .models import HealthCheckup
                    selected_reports = HealthCheckup.objects.filter(id__in=[r.id for r in selected_reports_list])
                
                if selected_medications_list:
                    from .models import Medication
                    selected_medications = Medication.objects.filter(id__in=[m.id for m in selected_medications_list])
                
            except HealthEvent.DoesNotExist:
                pass

        # 初始化选择的报告和药单ID列表（无论是否选择事件）
        selected_report_ids = data.get('selected_report_ids', [])
        selected_medication_ids = data.get('selected_medication_ids', [])

        if event_mode != 'select_event' or not selected_event_id:
            # 没有选择事件，单独处理报告和药单
            # 获取选择的报告ID
            if selected_report_ids:
                from .models import HealthCheckup
                selected_reports = HealthCheckup.objects.filter(
                    id__in=selected_report_ids,
                    user=request.user
                )

            # 获取选择的药单ID
            if selected_medication_ids:
                from .models import Medication, MedicationGroup
                selected_medications_list = []

                for med_id in selected_medication_ids:
                    # 处理药单组（前端可能传递 "group_3" 格式）
                    if isinstance(med_id, str) and med_id.startswith('group_'):
                        group_id = med_id.replace('group_', '')
                        try:
                            group = MedicationGroup.objects.get(id=group_id, user=request.user)
                            # 添加药单组中的所有药物
                            group_medications = Medication.objects.filter(
                                group=group,
                                user=request.user,
                                is_active=True
                            )
                            selected_medications_list.extend(group_medications)
                        except MedicationGroup.DoesNotExist:
                            pass
                    else:
                        # 处理单个药单
                        try:
                            medication = Medication.objects.get(
                                id=med_id,
                                user=request.user,
                                is_active=True
                            )
                            selected_medications_list.append(medication)
                        except (Medication.DoesNotExist, ValueError):
                            pass

                # 去重
                selected_medications_list = list(set(selected_medications_list))

                if selected_medications_list:
                    selected_medications = Medication.objects.filter(
                        id__in=[m.id for m in selected_medications_list]
                    )

        # 获取AI医生设置
        provider = SystemSettings.get_setting('ai_doctor_provider', 'openai')

        # 初始化变量
        api_url = None
        api_key = None
        model_name = None

        # 根据 provider 获取不同的配置
        if provider == 'gemini':
            gemini_config = SystemSettings.get_gemini_config()
            api_key = gemini_config['api_key']
            model_name = gemini_config['model_name']
        else:
            api_url = SystemSettings.get_setting('ai_doctor_api_url')
            api_key = SystemSettings.get_setting('ai_doctor_api_key')
            model_name = SystemSettings.get_setting('ai_doctor_model_name')

        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        max_tokens = int(SystemSettings.get_setting('ai_doctor_max_tokens', '4000'))

        # 验证配置
        if provider == 'gemini':
            if not api_key:
                return JsonResponse({
                    'success': False,
                    'error': 'Gemini API密钥未配置'
                }, status=500)
        else:
            if not api_url or not model_name:
                return JsonResponse({
                    'success': False,
                    'error': 'AI医生API未配置'
                }, status=500)

        # 获取对话上下文
        from .views import get_conversation_context, format_health_data_for_prompt
        conversation_context = get_conversation_context(request.user, conversation)

        # 检测并记录对话模式
        is_continuation = conversation_mode != 'new_conversation' and conversation
        if is_continuation:
            print(f"[Web流式AI] ✓ 检测到继续对话模式")
            print(f"[Web流式AI]   对话ID: {conversation.id}")
            print(f"[Web流式AI]   对话标题: {conversation.title}")
            print(f"[Web流式AI]   历史轮次: {len(conversation_context)}")
        else:
            print(f"[Web流式AI] → 新对话模式")

        # 继续对话时，如果未显式选择报告/药单，则复用该对话最近一次的选择
        if conversation_mode != 'new_conversation' and conversation:
            from .models import HealthAdvice
            latest_advice = HealthAdvice.objects.filter(
                conversation=conversation,
                user=request.user
            ).order_by('-created_at').first()

            if latest_advice:
                # 报告：仅在用户未选择且未明确表示“不使用报告”时复用
                if (not selected_report_ids) and report_mode != 'no_reports':
                    try:
                        selected_report_ids = json.loads(latest_advice.selected_reports) if latest_advice.selected_reports else []
                    except json.JSONDecodeError:
                        selected_report_ids = []

                # 药单：仅在用户未选择且未明确表示“不使用药单”时复用
                if (not selected_medication_ids) and medication_mode != 'no_medications':
                    try:
                        selected_medication_ids = json.loads(latest_advice.selected_medications) if latest_advice.selected_medications else []
                    except json.JSONDecodeError:
                        selected_medication_ids = []

                # 复用后重建查询集
                if selected_report_ids:
                    from .models import HealthCheckup
                    selected_reports = HealthCheckup.objects.filter(
                        id__in=selected_report_ids,
                        user=request.user
                    )
                if selected_medication_ids:
                    from .models import Medication, MedicationGroup
                    selected_medications_list = []

                    for med_id in selected_medication_ids:
                        # 处理药单组（前端可能传递 "group_3" 格式）
                        if isinstance(med_id, str) and med_id.startswith('group_'):
                            group_id = med_id.replace('group_', '')
                            try:
                                group = MedicationGroup.objects.get(id=group_id, user=request.user)
                                # 添加药单组中的所有药物
                                group_medications = Medication.objects.filter(
                                    group=group,
                                    user=request.user,
                                    is_active=True
                                )
                                selected_medications_list.extend(group_medications)
                            except MedicationGroup.DoesNotExist:
                                pass
                        else:
                            # 处理单个药单
                            try:
                                medication = Medication.objects.get(
                                    id=med_id,
                                    user=request.user,
                                    is_active=True
                                )
                                selected_medications_list.append(medication)
                            except (Medication.DoesNotExist, ValueError):
                                pass

                    # 去重
                    selected_medications_list = list(set(selected_medications_list))

                    if selected_medications_list:
                        selected_medications = Medication.objects.filter(
                            id__in=[m.id for m in selected_medications_list]
                        )

        # 判断是否为百川API（支持system角色）
        is_baichuan = (
            provider == 'baichuan' or
            (api_url and 'baichuan' in api_url.lower()) or
            (model_name and 'Baichuan' in model_name)
        )

        # 构建系统提示词（使用统一的prompt配置）
        system_prompt = AI_DOCTOR_SYSTEM_PROMPT

        # 构建用户消息
        # 检测是否为继续对话
        is_continuation = conversation_mode != 'new_conversation' and conversation

        if is_continuation:
            # 继续对话：强调这是后续问题，要求AI关注新问题
            user_message_parts = [
                f"【继续对话】用户提出后续问题",
                f"当前问题：{question}",
                "",
                "【重要说明】",
                "1. 这是同一对话的延续，用户正在基于之前的讨论提出新的问题",
                "2. 请重点理解和回答用户的当前问题，不要重复之前的建议",
                "3. 如果当前问题与之前的讨论相关，请简要回顾相关要点，然后深入回答新问题",
                "4. 如果用户提出了新的健康担忧，请结合历史背景全面分析",
                "5. 保持对话的连贯性，使用一致的语气和建议风格"
            ]
        else:
            # 新对话
            user_message_parts = [f"当前问题：{question}"]

        # 添加个人信息
        try:
            user_profile = request.user.userprofile
            if user_profile.birth_date or user_profile.gender:
                user_message_parts.append("\n个人信息：")
                user_message_parts.append(f"性别：{user_profile.get_gender_display()}")
                if user_profile.age:
                    user_message_parts.append(f"年龄：{user_profile.age}岁")
        except:
            pass

        # 添加对话历史（仅在继续对话时）
        if is_continuation and conversation_context:
            user_message_parts.append("\n【最近的对话历史（供参考）】")
            for i, ctx in enumerate(conversation_context[-3:], 1):  # 只显示最近3轮
                user_message_parts.append(f"\n第{i}轮对话:")
                user_message_parts.append(f"  时间: {ctx['time']}")
                user_message_parts.append(f"  用户问题: {ctx['question']}")
                user_message_parts.append(f"  AI回答摘要: {ctx['answer']}")
            user_message_parts.append("\n请基于以上历史，重点关注用户的新问题。")

        # 检查是否真的有健康数据
        has_health_data = False
        if selected_reports is not None and selected_reports.exists():
            from .views import get_selected_reports_health_data
            health_data = get_selected_reports_health_data(request.user, selected_reports)

            if health_data and health_data.get('checkups') and len(health_data['checkups']) > 0:
                has_health_data = True
                health_data_text = format_health_data_for_prompt(health_data) if health_data else ""

        # 添加药单信息
        medication_data_text = ""
        if selected_medications is not None and selected_medications.exists():
            medication_parts = ["\n用药信息："]
            for med in selected_medications:
                medication_parts.append(f"- {med.medicine_name}")
                medication_parts.append(f"  服药方式：{med.dosage}")
                medication_parts.append(f"  疗程：{med.start_date} 至 {med.end_date} (共{med.total_days}天)")
                medication_parts.append(f"  当前进度：已服药{med.days_taken}/{med.total_days}天 ({med.progress_percentage}%)")
                if med.notes:
                    medication_parts.append(f"  备注：{med.notes}")
                medication_parts.append("")  # 空行分隔
            medication_data_text = "\n".join(medication_parts)

        # 构建用户消息的健康数据和药单信息部分
        if has_health_data or medication_data_text:
            # 添加健康数据
            if has_health_data:
                user_message_parts.append(f"\n用户健康数据：\n{health_data_text}")

            # 添加药单信息
            if medication_data_text:
                user_message_parts.append(medication_data_text)

            # 只有在非继续对话时才添加通用指导性提示
            if not is_continuation:
                user_message_parts.append("\n请基于以上信息：")
                user_message_parts.append("1. 结合对话历史，理解用户的连续关注点")
                user_message_parts.append("2. 分析用户的健康状况和趋势")
                if medication_data_text:
                    user_message_parts.append("3. 结合用户的用药情况，分析药物与健康状况的关系")
                    user_message_parts.append("4. 针对用户的具体问题提供专业建议")
                    user_message_parts.append("5. 注意观察指标的历史变化趋势")
                    user_message_parts.append("6. 给出实用的生活方式和医疗建议")
                    user_message_parts.append("7. 如有异常指标，请特别说明并建议应对措施")
                else:
                    user_message_parts.append("3. 针对用户的具体问题提供专业建议")
                    user_message_parts.append("4. 注意观察指标的历史变化趋势")
                    user_message_parts.append("5. 给出实用的生活方式和医疗建议")
                    user_message_parts.append("6. 如有异常指标，请特别说明并建议应对措施")
        else:
            # 没有提供健康数据和药单信息
            notice_parts = ["\n注意："]
            if selected_reports is not None and not selected_reports.exists():
                notice_parts.append("用户选择不提供任何体检报告数据")
            if selected_medications is not None and not selected_medications.exists():
                if len(notice_parts) > 1:
                    notice_parts.append("，不提供用药信息")
                else:
                    notice_parts.append("用户选择不提供用药信息")
            notice_parts.append("，请仅基于问题提供一般性健康建议。")

            user_message_parts.append("".join(notice_parts))

            # 只有在非继续对话时才添加通用指导性提示
            if not is_continuation:
                user_message_parts.extend([
                    "\n请基于以上问题：",
                    "1. 结合对话历史，理解用户的关注点",
                    "2. 提供一般性的健康建议和知识",
                    "3. 针对用户的具体问题给出专业建议",
                    "4. 建议何时需要就医或专业咨询",
                    "5. 给出实用的生活方式和预防措施"
                ])

        user_message = "\n".join(user_message_parts)

        # 如果不支持system角色，合并为单一prompt
        if not is_baichuan:
            prompt = f"{system_prompt}\n\n{user_message}"
        else:
            # 支持system角色时，保留分离的消息格式
            # 用于保存到数据库
            prompt = f"[系统提示]\n{system_prompt}\n\n[用户消息]\n{user_message}"

        # 生成流式响应
        def generate():
            """生成流式响应"""
            from .models import HealthAdvice as HA  # Import locally to avoid closure issues
            nonlocal conversation
            full_response = ""
            error_msg = None

            try:
                # 首先发送prompt内容
                yield f"data: {json.dumps({'prompt': prompt}, ensure_ascii=False)}\n\n"

                # 根据提供商选择不同的流式调用方式
                if provider == 'gemini':
                    # 使用 LangChain 的 ChatGoogleGenerativeAI
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        temperature=0.7,
                        timeout=timeout,
                        streaming=True
                    )

                    # 构建消息列表（支持system角色）
                    messages = []
                    if is_baichuan:
                        # 百川API：使用assistant和user分离
                        messages.append(AIMessage(content=system_prompt))
                        messages.append(HumanMessage(content=user_message))
                        print(f"[AI医生-流式-Gemini] 使用assistant角色模式")
                    else:
                        # 其他API：合并为单一消息
                        messages.append(HumanMessage(content=prompt))

                    # 流式输出
                    for chunk in llm.stream(messages):
                        if hasattr(chunk, 'content') and chunk.content:
                            # Gemini 返回的 content 可能是列表或字符串
                            chunk_content = chunk.content

                            # 如果是列表，提取文本内容
                            if isinstance(chunk_content, list):
                                content_text = ""
                                for item in chunk_content:
                                    if isinstance(item, str):
                                        content_text += item
                                    elif hasattr(item, 'text'):
                                        content_text += item.text
                                    elif isinstance(item, dict) and 'text' in item:
                                        content_text += item['text']
                                content = content_text
                            else:
                                # 如果已经是字符串，直接使用
                                content = str(chunk_content)

                            full_response += content

                            # 发送SSE格式的数据
                            yield f"data: {json.dumps({'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                    # 流式输出完成
                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

                else:
                    # 使用 OpenAI 兼容格式（LangChain）
                    from langchain_openai import ChatOpenAI
                    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                    # 处理 API URL，避免重复路径
                    # LangChain 会自动添加 /chat/completions，所以如果 URL 中已包含，需要移除
                    base_url = api_url
                    if '/chat/completions' in base_url:
                        # 如果 URL 已包含 /chat/completions，移除它（包括可能的 /v1 前缀）
                        base_url = base_url.split('/chat/completions')[0].rstrip('/')
                    elif base_url.endswith('/'):
                        # 移除末尾的斜杠
                        base_url = base_url.rstrip('/')

                    # 初始化LangChain LLM
                    llm = ChatOpenAI(
                        model=model_name,
                        # 兼容本地OpenAI兼容服务：允许未配置API Key
                        api_key=api_key or 'not-needed',
                        base_url=base_url,
                        temperature=0.3,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        streaming=True
                    )

                    # 构建消息列表（支持system角色）
                    messages = []
                    if is_baichuan:
                        # 百川API：使用assistant和user分离
                        messages.append(AIMessage(content=system_prompt))
                        messages.append(HumanMessage(content=user_message))
                        print(f"[AI医生-流式-OpenAI兼容] 使用assistant角色模式，模型：{model_name}")
                    else:
                        # 其他API：合并为单一消息
                        messages.append(HumanMessage(content=prompt))

                    # 流式输出
                    for chunk in llm.stream(messages):
                        if hasattr(chunk, 'content') and chunk.content:
                            content = chunk.content
                            full_response += content

                            # 发送SSE格式的数据
                            yield f"data: {json.dumps({'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                    # 流式输出完成
                    yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"

            except Exception as e:
                # 发送错误信息
                error_msg = str(e)
                yield f"data: {json.dumps({'error': error_msg, 'done': True}, ensure_ascii=False)}\n\n"

            # 保存到数据库（在流式完成后）
            try:
                if full_response and not error_msg:
                    # 创建或获取对话
                    from .models import Conversation as Conv
                    if not conversation:
                        question_text = question[:50]
                        if len(question) > 50:
                            question_text += '...'
                        conversation = Conv.create_new_conversation(request.user, f"健康咨询: {question_text}")

                    # 保存AI建议
                    advice = HA.objects.create(
                        user=request.user,
                        conversation=conversation,
                        question=question,
                        answer=full_response,
                        is_generating=False,  # 流式输出完成，标记为已完成
                        prompt_sent=prompt,
                        conversation_context=json.dumps(conversation_context, ensure_ascii=False) if conversation_context else None,
                        selected_reports=json.dumps(selected_report_ids, ensure_ascii=False) if selected_report_ids else None,
                        selected_medications=json.dumps(selected_medication_ids, ensure_ascii=False) if selected_medication_ids else None,
                        selected_event=selected_event_id_for_save if selected_event_id_for_save else None
                    )

                    # 发送保存成功的消息
                    yield f"data: {json.dumps({'saved': True, 'advice_id': advice.id, 'conversation_id': conversation.id}, ensure_ascii=False)}\n\n"

            except Exception as save_error:
                # 保存失败，但流式输出已完成
                yield f"data: {json.dumps({'save_error': str(save_error)}, ensure_ascii=False)}\n\n"

        # 返回流式响应
        response = StreamingHttpResponse(generate(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # 禁用Nginx缓冲
        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }, status=500)


@csrf_exempt  # 禁用CSRF检查（小程序使用Token认证）
@api_view(['POST'])
@permission_classes([IsAuthenticated])  # 使用Token认证，兼容小程序
def stream_advice_sync(request):
    """非流式版本的AI健康建议（小程序专用，复用stream_ai_advice的逻辑）"""
    import json
    import traceback
    from django.http import JsonResponse
    from .models import SystemSettings, Conversation as Conv

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': '只支持POST请求'
        }, status=405)

    try:
        # 获取请求数据（与stream_ai_advice相同）
        data = _safe_get_request_json(request)
        if not isinstance(data, dict):
            data = {}
        question = data.get('question', '').strip()

        if not question:
            return JsonResponse({
                'success': False,
                'error': '问题不能为空'
            }, status=400)

        # 获取对话ID（可选）
        conversation_id = data.get('conversation_id')
        conversation_mode = data.get('conversation_mode', 'new_conversation')
        report_mode = data.get('report_mode')
        medication_mode = data.get('medication_mode')
        conversation = None

        # 只在非新对话模式下才加载历史对话
        if conversation_mode != 'new_conversation' and conversation_id:
            try:
                conversation = Conv.objects.get(id=conversation_id, user=request.user, is_active=True)
            except Conv.DoesNotExist:
                pass

        # 获取选择的报告ID
        selected_report_ids = data.get('selected_report_ids', [])
        selected_reports = None
        if selected_report_ids:
            from .models import HealthCheckup
            selected_reports = HealthCheckup.objects.filter(
                id__in=selected_report_ids,
                user=request.user
            )

        # 获取选择的药单ID
        selected_medication_ids = data.get('selected_medication_ids', [])
        selected_medications = None
        if selected_medication_ids:
            from .models import Medication, MedicationGroup
            selected_medications_list = []

            for med_id in selected_medication_ids:
                # 处理药单组（前端可能传递 "group_3" 格式）
                if isinstance(med_id, str) and med_id.startswith('group_'):
                    group_id = med_id.replace('group_', '')
                    try:
                        group = MedicationGroup.objects.get(id=group_id, user=request.user)
                        # 添加药单组中的所有药物
                        group_medications = Medication.objects.filter(
                            group=group,
                            user=request.user,
                            is_active=True
                        )
                        selected_medications_list.extend(group_medications)
                    except MedicationGroup.DoesNotExist:
                        pass
                else:
                    # 处理单个药单
                    try:
                        medication = Medication.objects.get(
                            id=med_id,
                            user=request.user,
                            is_active=True
                        )
                        selected_medications_list.append(medication)
                    except (Medication.DoesNotExist, ValueError):
                        pass

            # 去重
            selected_medications_list = list(set(selected_medications_list))

            if selected_medications_list:
                selected_medications = Medication.objects.filter(
                    id__in=[m.id for m in selected_medications_list]
                )

        # 获取AI医生设置
        provider = SystemSettings.get_setting('ai_doctor_provider', 'openai')
        api_url = None
        api_key = None
        model_name = None

        if provider == 'gemini':
            gemini_config = SystemSettings.get_gemini_config()
            api_key = gemini_config.get('api_key')
            model_name = gemini_config.get('model_name')
        else:
            api_url = SystemSettings.get_setting('ai_doctor_api_url')
            api_key = SystemSettings.get_setting('ai_doctor_api_key')
            model_name = SystemSettings.get_setting('ai_doctor_model_name')

        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        max_tokens = int(SystemSettings.get_setting('ai_doctor_max_tokens', '4000'))

        # 验证配置
        if provider == 'gemini':
            if not api_key or not model_name:
                return JsonResponse({
                    'success': False,
                    'error': 'Gemini API未配置'
                }, status=500)
        else:
            if not api_url or not model_name:
                return JsonResponse({
                    'success': False,
                    'error': 'AI医生API未配置'
                }, status=500)

        # 获取对话上下文
        from .views import get_conversation_context, format_health_data_for_prompt
        conversation_context = get_conversation_context(request.user, conversation)

        # 检测并记录对话模式
        is_continuation = conversation_mode != 'new_conversation' and conversation
        if is_continuation:
            print(f"[小程序-同步AI] ✓ 检测到继续对话模式")
        else:
            print(f"[小程序-同步AI] → 新对话模式")

        # 继续对话时，复用上次的选择
        if conversation_mode != 'new_conversation' and conversation:
            from .models import HealthAdvice
            latest_advice = HealthAdvice.objects.filter(
                conversation=conversation,
                user=request.user
            ).order_by('-created_at').first()

            if latest_advice:
                if not selected_report_ids and report_mode != 'no_reports':
                    try:
                        selected_report_ids = json.loads(latest_advice.selected_reports) if latest_advice.selected_reports else []
                    except json.JSONDecodeError:
                        selected_report_ids = []

                if not selected_medication_ids and medication_mode != 'no_medications':
                    try:
                        selected_medication_ids = json.loads(latest_advice.selected_medications) if latest_advice.selected_medications else []
                    except json.JSONDecodeError:
                        selected_medication_ids = []

                if selected_report_ids:
                    from .models import HealthCheckup
                    selected_reports = HealthCheckup.objects.filter(
                        id__in=selected_report_ids,
                        user=request.user
                    )
                if selected_medication_ids:
                    from .models import Medication, MedicationGroup
                    selected_medications_list = []

                    for med_id in selected_medication_ids:
                        # 处理药单组（前端可能传递 "group_3" 格式）
                        if isinstance(med_id, str) and med_id.startswith('group_'):
                            group_id = med_id.replace('group_', '')
                            try:
                                group = MedicationGroup.objects.get(id=group_id, user=request.user)
                                # 添加药单组中的所有药物
                                group_medications = Medication.objects.filter(
                                    group=group,
                                    user=request.user,
                                    is_active=True
                                )
                                selected_medications_list.extend(group_medications)
                            except MedicationGroup.DoesNotExist:
                                pass
                        else:
                            # 处理单个药单
                            try:
                                medication = Medication.objects.get(
                                    id=med_id,
                                    user=request.user,
                                    is_active=True
                                )
                                selected_medications_list.append(medication)
                            except (Medication.DoesNotExist, ValueError):
                                pass

                    # 去重
                    selected_medications_list = list(set(selected_medications_list))

                    if selected_medications_list:
                        selected_medications = Medication.objects.filter(
                            id__in=[m.id for m in selected_medications_list]
                        )

        # 构建系统提示词和用户消息（与stream_ai_advice完全相同）
        from .llm_prompts import AI_DOCTOR_SYSTEM_PROMPT

        system_prompt = AI_DOCTOR_SYSTEM_PROMPT
        is_continuation = conversation_mode != 'new_conversation' and conversation

        if is_continuation:
            user_message_parts = [
                f"【继续对话】用户提出后续问题",
                f"当前问题：{question}",
                "",
                "【重要说明】",
                "1. 这是同一对话的延续，用户正在基于之前的讨论提出新的问题",
                "2. 请重点理解和回答用户的当前问题，不要重复之前的建议",
                "3. 如果当前问题与之前的讨论相关，请简要回顾相关要点，然后深入回答新问题",
                "4. 如果用户提出了新的健康担忧，请结合历史背景全面分析",
                "5. 保持对话的连贯性，使用一致的语气和建议风格"
            ]
        else:
            user_message_parts = [f"当前问题：{question}"]

        # 添加个人信息
        try:
            user_profile = request.user.userprofile
            if user_profile.birth_date or user_profile.gender:
                user_message_parts.append("\n个人信息：")
                user_message_parts.append(f"性别：{user_profile.get_gender_display()}")
                if user_profile.age:
                    user_message_parts.append(f"年龄：{user_profile.age}岁")
        except:
            pass

        # 添加对话历史（仅在继续对话时）
        if is_continuation and conversation_context:
            user_message_parts.append("\n【最近的对话历史（供参考）】")
            for i, ctx in enumerate(conversation_context[-3:], 1):
                user_message_parts.append(f"\n第{i}轮对话:")
                user_message_parts.append(f"  时间: {ctx['time']}")
                user_message_parts.append(f"  用户问题: {ctx['question']}")
                user_message_parts.append(f"  AI回答摘要: {ctx['answer']}")
            user_message_parts.append("\n请基于以上历史，重点关注用户的新问题。")

        # 添加健康数据和药单信息
        has_health_data = False
        if selected_reports is not None and selected_reports.exists():
            from .views import get_selected_reports_health_data
            health_data = get_selected_reports_health_data(request.user, selected_reports)

            if health_data and health_data.get('checkups') and len(health_data['checkups']) > 0:
                has_health_data = True
                health_data_text = format_health_data_for_prompt(health_data) if health_data else ""

        medication_data_text = ""
        if selected_medications is not None and selected_medications.exists():
            medication_parts = ["\n用药信息："]
            for med in selected_medications:
                medication_parts.append(f"- {med.medicine_name}")
                medication_parts.append(f"  服药方式：{med.dosage}")
                medication_parts.append(f"  疗程：{med.start_date} 至 {med.end_date} (共{med.total_days}天)")
                medication_parts.append(f"  当前进度：已服药{med.days_taken}/{med.total_days}天 ({med.progress_percentage}%)")
                if med.notes:
                    medication_parts.append(f"  备注：{med.notes}")
                medication_parts.append("")
            medication_data_text = "\n".join(medication_parts)

        # 构建用户消息的健康数据和药单信息部分
        if has_health_data or medication_data_text:
            if has_health_data:
                user_message_parts.append(f"\n用户健康数据：\n{health_data_text}")

            if medication_data_text:
                user_message_parts.append(medication_data_text)

            if not is_continuation:
                user_message_parts.append("\n请基于以上信息：")
                user_message_parts.append("1. 结合对话历史，理解用户的连续关注点")
                user_message_parts.append("2. 分析用户的健康状况和趋势")
                if medication_data_text:
                    user_message_parts.append("3. 结合用户的用药情况，分析药物与健康状况的关系")
                    user_message_parts.append("4. 针对用户的具体问题提供专业建议")
                    user_message_parts.append("5. 注意观察指标的历史变化趋势")
                    user_message_parts.append("6. 给出实用的生活方式和医疗建议")
                    user_message_parts.append("7. 如有异常指标，请特别说明并建议应对措施")
                else:
                    user_message_parts.append("3. 针对用户的具体问题提供专业建议")
                    user_message_parts.append("4. 注意观察指标的历史变化趋势")
                    user_message_parts.append("5. 给出实用的生活方式和医疗建议")
                    user_message_parts.append("6. 如有异常指标，请特别说明并建议应对措施")
        else:
            notice_parts = ["\n注意："]
            if selected_reports is not None and not selected_reports.exists():
                notice_parts.append("用户选择不提供任何体检报告数据")
            if selected_medications is not None and not selected_medications.exists():
                if len(notice_parts) > 1:
                    notice_parts.append("，不提供用药信息")
                else:
                    notice_parts.append("用户选择不提供用药信息")
            notice_parts.append("，请仅基于问题提供一般性健康建议。")

            user_message_parts.append("".join(notice_parts))

            if not is_continuation:
                user_message_parts.extend([
                    "\n请基于以上问题：",
                    "1. 结合对话历史，理解用户的关注点",
                    "2. 提供一般性的健康建议和知识",
                    "3. 针对用户的具体问题给出专业建议",
                    "4. 建议何时需要就医或专业咨询",
                    "5. 给出实用的生活方式和预防措施"
                ])

        user_message = "\n".join(user_message_parts)
        prompt = f"{system_prompt}\n\n{user_message}"

        print(f"[小程序-同步AI] 开始调用LLM，问题长度: {len(question)}")

        # 调用LLM（非流式）
        from langchain_core.messages import HumanMessage

        if provider == 'gemini':
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=0.3,
                timeout=timeout,
                streaming=False
            )
        else:
            from langchain_openai import ChatOpenAI

            # 处理 API URL
            base_url = api_url
            if '/chat/completions' in base_url:
                base_url = base_url.split('/chat/completions')[0].rstrip('/')
            elif base_url.endswith('/'):
                base_url = base_url.rstrip('/')

            # 初始化LangChain LLM（非流式）
            llm = ChatOpenAI(
                model=model_name,
                # 兼容本地OpenAI兼容服务：允许未配置API Key
                api_key=api_key or 'not-needed',
                base_url=base_url,
                temperature=0.3,
                max_tokens=max_tokens,
                timeout=timeout,
                streaming=False
            )

        # 调用LLM
        messages = [HumanMessage(content=prompt)]
        result = llm.invoke(messages)
        full_response = result.content

        print(f"[小程序-同步AI] LLM响应成功，长度: {len(full_response)}")

        # 保存到数据库
        if not conversation:
            question_text = question[:50]
            if len(question) > 50:
                question_text += '...'
            conversation = Conv.create_new_conversation(request.user, f"健康咨询: {question_text}")

        from .models import HealthAdvice
        advice = HealthAdvice.objects.create(
            user=request.user,
            conversation=conversation,
            question=question,
            answer=full_response,
            is_generating=False,  # 非流式接口，立即返回完整响应
            prompt_sent=prompt,
            conversation_context=json.dumps(conversation_context, ensure_ascii=False) if conversation_context else None,
            selected_reports=json.dumps(selected_report_ids, ensure_ascii=False) if selected_report_ids else None,
            selected_medications=json.dumps(selected_medication_ids, ensure_ascii=False) if selected_medication_ids else None
        )

        print(f"[小程序-同步AI] 已保存到数据库，advice_id: {advice.id}, conversation_id: {conversation.id}")

        return JsonResponse({
            'success': True,
            'answer': full_response,
            'prompt': prompt,
            'conversation_id': conversation.id,
            'advice_id': advice.id
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }, status=500)


@login_required
def stream_upload_and_process(request):
    """流式上传并处理体检报告（带实时进度反馈）"""
    from django.http import StreamingHttpResponse
    import time

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': '只支持POST请求'
        }, status=405)

    def generate():
        import json
        import os
        import tempfile

        try:
            # 1. 验证文件
            if 'file' not in request.FILES:
                yield f"data: {json.dumps({'error': '没有上传文件'}, ensure_ascii=False)}\n\n"
                return

            file = request.FILES['file']

            # 检查文件类型
            is_pdf = file.name.lower().endswith('.pdf')
            is_image = is_image_file(file.name)

            if not is_pdf and not is_image:
                yield f"data: {json.dumps({'error': '只支持PDF和图片格式的文件'}, ensure_ascii=False)}\n\n"
                return

            # 检查文件大小
            if file.size > 10 * 1024 * 1024:
                yield f"data: {json.dumps({'error': '文件大小不能超过10MB'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'status': 'validating', 'message': '文件验证通过'}, ensure_ascii=False)}\n\n"

            # 获取表单数据
            checkup_date = request.POST.get('checkup_date')
            hospital = request.POST.get('hospital', '未知机构')

            # 根据文件类型自动选择工作流
            from .models import SystemSettings
            workflow_type = request.POST.get('workflow_type', '')
            
            if not workflow_type:
                file_ext = file.name.lower().split('.')[-1] if '.' in file.name else ''
                if file_ext == 'pdf':
                    workflow_type = SystemSettings.get_pdf_ocr_workflow()
                else:
                    workflow_type = 'vl_model'

            if not checkup_date:
                yield f"data: {json.dumps({'error': '请提供体检日期'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'status': 'creating_records', 'message': '创建体检记录...'}, ensure_ascii=False)}\n\n"

            # 获取报告描述
            report_description = request.POST.get('report_description', '') or file.name

            # 创建体检报告记录
            health_checkup = HealthCheckup.objects.create(
                user=request.user,
                checkup_date=checkup_date,
                hospital=hospital,
                report_file=file,
                notes=report_description
            )

            # 创建或更新文档处理记录
            try:
                # 先尝试删除已存在的记录（因为是OneToOneField，避免冲突）
                DocumentProcessing.objects.filter(
                    user=request.user,
                    health_checkup=health_checkup
                ).delete()
            except:
                pass
            
            # 创建新的文档处理记录
            document_processing = DocumentProcessing.objects.create(
                user=request.user,
                health_checkup=health_checkup,
                workflow_type=workflow_type,
                status='pending',
                progress=0
            )

            # 保存文件到临时位置
            import os
            file_extension = os.path.splitext(file.name)[1]

            if is_image:
                if workflow_type == 'vl_model':
                    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                        for chunk in file.chunks():
                            tmp_file.write(chunk)
                        tmp_file_path = tmp_file.name
                else:
                    temp_image_path = None
                    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_image:
                        for chunk in file.chunks():
                            temp_image.write(chunk)
                        temp_image_path = temp_image.name

                    from .utils import convert_image_file_to_pdf
                    pdf_data = convert_image_file_to_pdf(temp_image_path)

                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                        tmp_file.write(pdf_data)
                        tmp_file_path = tmp_file.name

                    try:
                        os.unlink(temp_image_path)
                    except:
                        pass
            else:
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                    for chunk in file.chunks():
                        tmp_file.write(chunk)
                    tmp_file_path = tmp_file.name

            yield f"data: {json.dumps({'status': 'file_saved', 'message': '文件已保存，开始处理...'}, ensure_ascii=False)}\n\n"

            # 根据工作流类型选择处理方式
            if workflow_type == 'vl_model':
                # 多模态大模型工作流
                yield f"data: {json.dumps({'status': 'vlm_start', 'message': '🤖 开始多模态大模型分析...'}, ensure_ascii=False)}\n\n"

                from .services import VisionLanguageModelService
                vlm_service = VisionLanguageModelService(document_processing)

                try:
                    # 执行多模态大模型处理
                    structured_data = vlm_service.process_with_vision_model(tmp_file_path)

                    # 保存数据
                    yield f"data: {json.dumps({'status': 'saving_start', 'message': '💾 正在保存到数据库...'}, ensure_ascii=False)}\n\n"
                    saved_count = vlm_service.save_vision_indicators(structured_data)

                    # 清理临时文件
                    try:
                        os.unlink(tmp_file_path)
                    except:
                        pass

                    # 发送完成消息
                    yield f"data: {json.dumps({'status': 'complete', 'message': f'✅ 处理完成！成功保存 {saved_count} 个指标', 'checkup_id': health_checkup.id, 'indicators_count': saved_count}, ensure_ascii=False)}\n\n"

                except Exception as e:
                    import traceback
                    error_trace = traceback.format_exc()
                    yield f"data: {json.dumps({'error': f'多模态大模型处理失败: {str(e)}', 'trace': error_trace}, ensure_ascii=False)}\n\n"
                    return
            else:
                # OCR+LLM 工作流（传统模式）
                service = DocumentProcessingService(document_processing)

                # 发送OCR开始消息
                yield f"data: {json.dumps({'status': 'ocr_start', 'message': '🔍 开始OCR文字识别...'}, ensure_ascii=False)}\n\n"

                # 在后台线程中执行OCR，主线程定期发送心跳保持SSE连接
                import threading
                import queue
                result_queue = queue.Queue()

                def ocr_worker():
                    """后台线程执行OCR"""
                    try:
                        ocr_text = service.perform_ocr(tmp_file_path)
                        result_queue.put(('success', ocr_text))
                    except Exception as e:
                        result_queue.put(('error', str(e)))

                # 启动OCR后台线程
                ocr_thread = threading.Thread(target=ocr_worker)
                ocr_thread.start()

                # 定期发送心跳保持连接，同时检查OCR是否完成
                import time
                heartbeat_count = 0
                ocr_complete = False
                start_time = time.time()

                print(f"[流式上传] OCR处理开始，将在后台线程执行，主线程每10秒发送心跳")

                while not ocr_complete:
                    try:
                        # 非阻塞检查队列
                        result_type, result_data = result_queue.get(timeout=10)
                        if result_type == 'success':
                            ocr_text = result_data
                            ocr_complete = True
                            elapsed = int(time.time() - start_time)
                            print(f"[流式上传] OCR完成，总耗时: {elapsed}秒")
                            yield f"data: {json.dumps({'status': 'ocr_complete', 'message': f'✅ OCR识别完成，识别了 {len(ocr_text)} 个字符 (耗时{elapsed}秒)'}, ensure_ascii=False)}\n\n"
                        else:
                            # OCR出错
                            raise Exception(result_data)
                    except queue.Empty:
                        # 队列为空，发送心跳继续等待
                        heartbeat_count += 1
                        elapsed = int(time.time() - start_time)
                        heartbeat_messages = [
                            '⏳ OCR正在处理中...',
                            '🔍 正在识别文字...',
                            '📄 正在解析文档...',
                            '⚡ 正在处理表格和图表...'
                        ]
                        message = heartbeat_messages[heartbeat_count % len(heartbeat_messages)]
                        print(f"[流式上传] 发送心跳 #{heartbeat_count}, 已等待 {elapsed}秒")
                        yield f"data: {json.dumps({'status': 'ocr_processing', 'message': f'{message} (已处理 {elapsed}秒)'}, ensure_ascii=False)}\n\n"

                # 等待线程结束
                ocr_thread.join()

                # 发送AI分析开始消息
                yield f"data: {json.dumps({'status': 'ai_start', 'message': '🤖 AI正在分析数据...'}, ensure_ascii=False)}\n\n"

                # 执行AI分析 - 使用流式输出
                try:
                    # 获取LLM配置
                    from .models import SystemSettings
                    llm_config = SystemSettings.get_llm_config()
                    llm_provider = llm_config.get('provider', 'openai')

                    # 构建prompt
                    prompt = service._build_llm_prompt(ocr_text)

                    timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
                    llm_response = ""

                    if llm_provider == 'gemini':
                        # 获取Gemini配置
                        gemini_config = SystemSettings.get_gemini_config()
                        api_key = gemini_config.get('api_key', '')
                        model_name = gemini_config.get('model_name', 'gemini-2.5-flash-exp')

                        if not api_key:
                            raise Exception("Gemini API密钥未配置")

                        # 使用流式调用
                        from langchain_google_genai import ChatGoogleGenerativeAI
                        from langchain_core.messages import HumanMessage

                        llm = ChatGoogleGenerativeAI(
                            model=model_name,
                            google_api_key=api_key,
                            temperature=0.1,
                            timeout=timeout,
                            streaming=True
                        )

                        messages = [HumanMessage(content=prompt)]

                        print(f"[智能上传] 开始流式调用Gemini，prompt长度: {len(prompt)}")

                        # 流式输出token
                        chunk_count = 0
                        for chunk in llm.stream(messages):
                            chunk_count += 1
                            if hasattr(chunk, 'content') and chunk.content:
                                # Gemini 返回的 content 可能是列表或字符串
                                chunk_content = chunk.content

                                # 如果是列表，提取文本内容
                                if isinstance(chunk_content, list):
                                    content_text = ""
                                    for item in chunk_content:
                                        if isinstance(item, str):
                                            content_text += item
                                        elif hasattr(item, 'text'):
                                            content_text += item.text
                                        elif isinstance(item, dict) and 'text' in item:
                                            content_text += item['text']
                                    content = content_text
                                else:
                                    # 如果已经是字符串，直接使用
                                    content = str(chunk_content)

                                llm_response += content

                                if content:
                                    # 实时发送token给前端
                                    yield f"data: {json.dumps({'status': 'llm_token', 'token': content}, ensure_ascii=False)}\n\n"
                                else:
                                    print(f"[智能上传] 第{chunk_count}个chunk的content为空")

                        print(f"[智能上传] 流式调用完成，共处理{chunk_count}个chunk，响应长度: {len(llm_response)}")

                        # 检查响应是否为空
                        if not llm_response or len(llm_response.strip()) == 0:
                            raise Exception("Gemini返回空响应，请检查API配置和网络连接")

                    else:
                        # 获取OpenAI兼容配置
                        api_key = llm_config.get('api_key', '')
                        api_url = llm_config.get('api_url', '')
                        model_name = llm_config.get('model_name', 'gpt-4o-mini')

                        if not api_key or not api_url:
                            raise Exception("OpenAI兼容API配置不完整")

                        # 使用流式调用OpenAI兼容模式
                        from langchain_openai import ChatOpenAI
                        from langchain_core.messages import HumanMessage

                        # 处理 API URL
                        base_url = api_url
                        if '/chat/completions' in base_url:
                            # 如果 URL 已包含 /chat/completions，移除它（包括可能的 /v1 前缀）
                            base_url = base_url.split('/chat/completions')[0].rstrip('/')
                        elif base_url.endswith('/'):
                            base_url = base_url.rstrip('/')

                        llm = ChatOpenAI(
                            model=model_name,
                            api_key=api_key,
                            base_url=base_url,
                            temperature=0.1,
                            timeout=timeout,
                            streaming=True
                        )

                        messages = [HumanMessage(content=prompt)]

                        # 流式输出token
                        for chunk in llm.stream(messages):
                            if hasattr(chunk, 'content') and chunk.content:
                                content = chunk.content
                                llm_response += content
                                # 实时发送token给前端
                                yield f"data: {json.dumps({'status': 'llm_token', 'token': content}, ensure_ascii=False)}\n\n"

                    # 解析LLM响应
                    print(f"[智能上传] LLM响应长度: {len(llm_response)} 字符")
                    print(f"[智能上传] 响应前500字符: {llm_response[:500]}")

                    if not llm_response or len(llm_response.strip()) == 0:
                        raise Exception("LLM返回空响应，请检查API配置和网络连接")

                    # 清理响应中的markdown代码块标记
                    cleaned_response = llm_response.strip()
                    if cleaned_response.startswith('```'):
                        import re
                        cleaned_response = re.sub(r'^```\w*\n?', '', cleaned_response)
                        cleaned_response = re.sub(r'\n?```$', '', cleaned_response)

                    # 解析JSON
                    structured_data = json.loads(cleaned_response)

                    # 保存LLM原始结果用于调试
                    service.document_processing.ai_result = structured_data
                    service.document_processing.save()
                    print(f"LLM结果已保存，包含 {len(structured_data.get('indicators', []))} 个指标")

                    indicators_count = len(structured_data.get('indicators', []))
                    yield f"data: {json.dumps({'status': 'ai_complete', 'message': f'✅ AI分析完成，提取了 {indicators_count} 个指标'}, ensure_ascii=False)}\n\n"

                except Exception as e:
                    import traceback
                    error_trace = traceback.format_exc()
                    response_preview = llm_response[:500] if llm_response else '无响应'
                    yield f"data: {json.dumps({'error': f'AI分析失败: {str(e)}', 'response_preview': response_preview, 'response_length': len(llm_response) if llm_response else 0}, ensure_ascii=False)}\n\n"
                    return

                # 发送保存开始消息
                yield f"data: {json.dumps({'status': 'saving_start', 'message': '💾 正在保存到数据库...'}, ensure_ascii=False)}\n\n"

                # 保存数据
                saved_count = service.save_health_indicators(structured_data)

                # 计算处理时间
                end_time = time.time()

                # 清理临时文件
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass

                # 发送完成消息
                yield f"data: {json.dumps({'status': 'complete', 'message': f'✅ 处理完成！成功保存 {saved_count} 个指标', 'checkup_id': health_checkup.id, 'indicators_count': saved_count}, ensure_ascii=False)}\n\n"
                return  # 明确结束生成器

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            yield f"data: {json.dumps({'error': str(e), 'trace': error_trace}, ensure_ascii=False)}\n\n"
            return  # 明确结束生成器

    response = StreamingHttpResponse(generate(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
def stream_integrate_data(request):
    """流式数据整合（带实时AI思考过程）"""
    from django.http import StreamingHttpResponse
    import time

    if request.method != 'POST':
        return JsonResponse({
            'success': False,
            'error': '只支持POST请求'
        }, status=405)

    def generate():
        try:
            import json
            import re
            from .services import call_llm_for_integration, call_gemini_api
            from .models import SystemSettings

            # 获取请求数据
            data = json.loads(request.body)
            checkup_ids = data.get('checkup_ids', [])
            user_prompt = data.get('user_prompt', '').strip()

            if not checkup_ids:
                yield f"data: {json.dumps({'error': '请选择要整合的体检报告'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'status': 'validating', 'message': '验证报告数据...'}, ensure_ascii=False)}\n\n"

            # 验证报告所有权
            checkups = HealthCheckup.objects.filter(
                id__in=checkup_ids,
                user=request.user
            )

            if checkups.count() != len(checkup_ids):
                yield f"data: {json.dumps({'error': '部分报告不存在或无权访问'}, ensure_ascii=False)}\n\n"
                return

            # 获取所有指标
            indicators = HealthIndicator.objects.filter(
                checkup__in=checkups
            ).select_related('checkup')

            yield f"data: {json.dumps({'status': 'loading_data', 'message': f'加载了 {indicators.count()} 个指标'}, ensure_ascii=False)}\n\n"

            # 按指标名称分组
            indicators_by_name = {}
            for indicator in indicators:
                name_key = indicator.indicator_name.lower().strip()
                if name_key not in indicators_by_name:
                    indicators_by_name[name_key] = []
                indicators_by_name[name_key].append(indicator)

            yield f"data: {json.dumps({'status': 'grouping', 'message': f'分组完成，共 {len(indicators_by_name)} 组指标'}, ensure_ascii=False)}\n\n"

            # 准备发送给LLM的数据
            indicators_summary = []
            for name_key, inds in indicators_by_name.items():
                variants = []
                for ind in inds:
                    variants.append({
                        'id': ind.id,
                        'name': ind.indicator_name,
                        'value': ind.value,
                        'unit': ind.unit,
                        'reference_range': ind.reference_range,
                        'status': ind.status,
                        'type': ind.indicator_type
                    })
                indicators_summary.append({
                    'key': name_key,
                    'variants': variants
                })

            # 构建Prompt，使用统一的提示词配置
            indicators_data_json = json.dumps(indicators_summary, ensure_ascii=False, indent=2)
            system_prompt, user_prompt = build_data_integration_prompt(indicators_data_json, user_prompt)

            yield f"data: {json.dumps({'status': 'prompt_ready', 'message': f'📋 Prompt构建完成，长度: {len(user_prompt)} 字符'}, ensure_ascii=False)}\n\n"

            # 获取LLM提供商配置
            llm_config = SystemSettings.get_llm_config()
            llm_provider = llm_config.get('provider', 'openai')

            yield f"data: {json.dumps({'status': 'calling_llm', 'message': f'🤖 正在调用 {llm_provider.upper()} API...'}, ensure_ascii=False)}\n\n"

            # 调用LLM
            timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))

            try:
                if llm_provider == 'gemini':
                    # 获取Gemini配置
                    gemini_config = SystemSettings.get_gemini_config()
                    api_key = gemini_config.get('api_key', '')
                    model_name = gemini_config.get('model_name', 'gemini-2.5-flash-exp')
                    api_url = gemini_config.get('api_url', '')

                    if not api_key:
                        raise Exception("Gemini API密钥未配置")

                    # 判断是否为百川API
                    is_baichuan = (
                        llm_provider == 'baichuan' or
                        (api_url and 'baichuan' in api_url.lower()) or
                        (model_name and 'Baichuan' in model_name)
                    )

                    yield f"data: {json.dumps({'status': 'llm_thinking', 'message': '💭 Gemini正在分析数据...'}, ensure_ascii=False)}\n\n"

                    # 使用流式调用
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        temperature=0.7,
                        timeout=timeout,
                        streaming=True
                    )

                    # 根据是否为百川API使用不同的消息格式
                    if is_baichuan:
                        messages = [AIMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    else:
                        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    llm_response = ""

                    # 流式输出token
                    for chunk in llm.stream(messages):
                        if hasattr(chunk, 'content') and chunk.content:
                            # Gemini 返回的 content 可能是列表或字符串
                            chunk_content = chunk.content

                            # 如果是列表，提取文本内容
                            if isinstance(chunk_content, list):
                                content_text = ""
                                for item in chunk_content:
                                    if isinstance(item, str):
                                        content_text += item
                                    elif hasattr(item, 'text'):
                                        content_text += item.text
                                    elif isinstance(item, dict) and 'text' in item:
                                        content_text += item['text']
                                content = content_text
                            else:
                                # 如果已经是字符串，直接使用
                                content = str(chunk_content)

                            llm_response += content

                            if content:
                                # 实时发送token给前端
                                yield f"data: {json.dumps({'status': 'llm_token', 'token': content}, ensure_ascii=False)}\n\n"

                    # 检查响应是否为空
                    if not llm_response or len(llm_response.strip()) == 0:
                        raise Exception("Gemini返回空响应，请检查API配置和网络连接")
                else:
                    # 获取OpenAI兼容配置
                    api_key = llm_config.get('api_key', '')
                    api_url = llm_config.get('api_url', '')
                    model_name = llm_config.get('model_name', 'gpt-4o-mini')

                    if not api_key or not api_url:
                        raise Exception("OpenAI兼容API配置不完整")

                    yield f"data: {json.dumps({'status': 'llm_thinking', 'message': '💭 LLM正在分析数据...'}, ensure_ascii=False)}\n\n"

                    # 使用流式调用OpenAI兼容模式
                    from langchain_openai import ChatOpenAI
                    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

                    # 判断是否为百川API
                    is_baichuan = (
                        llm_provider == 'baichuan' or
                        (api_url and 'baichuan' in api_url.lower()) or
                        (model_name and 'Baichuan' in model_name)
                    )

                    # 处理 API URL
                    base_url = api_url
                    if '/chat/completions' in base_url:
                        # 如果 URL 已包含 /chat/completions，移除它（包括可能的 /v1 前缀）
                        base_url = base_url.split('/chat/completions')[0].rstrip('/')
                    elif base_url.endswith('/'):
                        base_url = base_url.rstrip('/')

                    llm = ChatOpenAI(
                        model=model_name,
                        api_key=api_key,
                        base_url=base_url,
                        temperature=0.7,
                        timeout=timeout,
                        streaming=True
                    )

                    # 根据是否为百川API使用不同的消息格式
                    if is_baichuan:
                        messages = [AIMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    else:
                        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                    llm_response = ""

                    # 流式输出token
                    for chunk in llm.stream(messages):
                        if hasattr(chunk, 'content') and chunk.content:
                            content = chunk.content
                            llm_response += content
                            # 实时发送token给前端
                            yield f"data: {json.dumps({'status': 'llm_token', 'token': content}, ensure_ascii=False)}\n\n"

                yield f"data: {json.dumps({'status': 'llm_complete', 'message': f'✅ LLM返回响应，长度: {len(llm_response)} 字符'}, ensure_ascii=False)}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'error': f'调用LLM失败: {str(e)}'}, ensure_ascii=False)}\n\n"
                return

            # 解析LLM响应
            try:
                yield f"data: {json.dumps({'status': 'parsing', 'message': '📊 正在解析LLM响应...'}, ensure_ascii=False)}\n\n"

                cleaned_response = llm_response.strip()
                print(f"[数据整合] 原始响应长度: {len(llm_response)} 字符")
                print(f"[数据整合] 清理后响应长度: {len(cleaned_response)} 字符")
                print(f"[数据整合] 响应前500字符: {cleaned_response[:500]}")

                if not cleaned_response:
                    raise Exception("LLM返回空响应")

                if cleaned_response.startswith('```'):
                    cleaned_response = re.sub(r'^```\w*\n?', '', cleaned_response)
                    cleaned_response = re.sub(r'\n?```$', '', cleaned_response)

                json_match = re.search(r'\{[\s\S]*\}', cleaned_response)
                if json_match:
                    result_json = json.loads(json_match.group())
                else:
                    result_json = json.loads(cleaned_response)

                changes = result_json.get('changes', [])

                yield f"data: {json.dumps({'status': 'parsed', 'message': f'✅ 解析完成，LLM建议更新 {len(changes)} 个指标'}, ensure_ascii=False)}\n\n"

                # 验证变更
                validated_changes = []
                for change in changes:
                    if not isinstance(change, dict):
                        continue

                    indicator_id = change.get('indicator_id')
                    if not indicator_id:
                        continue

                    try:
                        indicator = HealthIndicator.objects.get(id=indicator_id)
                    except HealthIndicator.DoesNotExist:
                        continue

                    original_data = {
                        'indicator_name': indicator.indicator_name,
                        'value': indicator.value,
                        'unit': indicator.unit or '',
                        'reference_range': indicator.reference_range or '',
                        'status': indicator.status,
                        'indicator_type': indicator.indicator_type or ''
                    }

                    actual_changes = {}
                    if 'indicator_name' in change:
                        actual_changes['indicator_name'] = change['indicator_name']
                    if 'value' in change:
                        actual_changes['value'] = str(change['value'])
                    if 'unit' in change:
                        actual_changes['unit'] = change['unit']
                    if 'status' in change:
                        actual_changes['status'] = change['status']
                    if 'indicator_type' in change:
                        actual_changes['indicator_type'] = change['indicator_type']

                    reason = change.get('reason', '')

                    validated_changes.append({
                        'indicator_id': indicator_id,
                        'original': original_data,
                        'changes': actual_changes,
                        'reason': reason
                    })

                # 收集未变更的指标
                changed_indicator_ids = set(change['indicator_id'] for change in validated_changes)
                unchanged_indicators = []
                for indicator in indicators:
                    if indicator.id not in changed_indicator_ids:
                        original_data = {
                            'indicator_name': indicator.indicator_name,
                            'value': indicator.value,
                            'unit': indicator.unit or '',
                            'reference_range': indicator.reference_range or '',
                            'status': indicator.status,
                            'indicator_type': indicator.indicator_type or ''
                        }
                        unchanged_indicators.append({
                            'indicator_id': indicator.id,
                            'original': original_data,
                            'changes': {},
                            'unchanged': True
                        })

                all_indicators = validated_changes + unchanged_indicators

                # 发送最终结果
                yield f"data: {json.dumps({'status': 'done', 'message': '✅ 整合完成！', 'total_indicators': indicators.count(), 'unique_groups': len(indicators_by_name), 'changed_count': len(validated_changes), 'unchanged_count': len(unchanged_indicators), 'changes': validated_changes, 'all_indicators': all_indicators}, ensure_ascii=False)}\n\n"

            except json.JSONDecodeError as e:
                yield f"data: {json.dumps({'error': f'JSON解析错误: {str(e)}', 'response_preview': llm_response[:1000], 'response_length': len(llm_response)}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': f'解析失败: {str(e)}', 'response_preview': llm_response[:500] if llm_response else '无响应'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            yield f"data: {json.dumps({'error': str(e), 'trace': traceback.format_exc()[:1000]}, ensure_ascii=False)}\n\n"

    response = StreamingHttpResponse(generate(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@require_http_methods(["POST"])
@login_required
def update_checkup_notes(request, checkup_id):
    """更新体检报告的描述（notes字段）"""
    try:
        import json

        # 验证报告所有权
        checkup = get_object_or_404(HealthCheckup, id=checkup_id, user=request.user)

        # 获取新的notes内容
        data = json.loads(request.body)
        new_notes = data.get('notes', '').strip()

        # 更新notes
        checkup.notes = new_notes
        checkup.save()

        return JsonResponse({
            'success': True,
            'message': '报告描述已更新',
            'notes': new_notes
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'更新失败: {str(e)}'
        }, status=500)


# ============================================================================
# 后台任务状态API
# ============================================================================

@csrf_exempt
@require_http_methods(["GET"])
@login_required
def api_task_status(request, task_id):
    """
    查询后台任务状态
    
    Args:
        task_id: 任务ID
    """
    try:
        from .background_tasks import task_manager
        
        task = task_manager.get_task_status(task_id)
        
        if not task:
            return JsonResponse({
                'status': 'not_found',
                'message': '任务不存在或已过期'
            }, status=404)
        
        return JsonResponse(task)
    
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"获取任务状态失败: {e}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)


# ============================================================================
# 用户处理模式设置API
# ============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
@login_required
def api_processing_mode(request):
    """
    获取或设置用户的AI处理模式
    
    GET: 获取当前模式
    POST: 设置模式
    
    模式说明：
    - stream: 实时模式（流式响应），需要保持页面打开，可以看到实时输出
    - background: 后台模式（异步任务），可以离开页面，完成后查看结果
    """
    try:
        from .models import UserProfile
        
        # 获取或创建用户配置
        user_profile, created = UserProfile.objects.get_or_create(
            user=request.user
        )
        
        if request.method == 'GET':
            # 获取当前模式
            return JsonResponse({
                'mode': user_profile.processing_mode,
                'mode_display': user_profile.get_processing_mode_display(),
                'description': {
                    'stream': '实时模式：可以看到AI生成的实时过程，但需要保持页面打开',
                    'background': '后台模式：可以在后台处理，完成后查看结果，适合手机用户'
                }.get(user_profile.processing_mode, '')
            })
        
        elif request.method == 'POST':
            # 设置模式
            data = json.loads(request.body)
            new_mode = data.get('mode')
            
            if new_mode not in ['stream', 'background']:
                return JsonResponse({
                    'error': '无效的模式，必须是 stream 或 background'
                }, status=400)
            
            user_profile.processing_mode = new_mode
            user_profile.save()
            
            return JsonResponse({
                'success': True,
                'mode': new_mode,
                'mode_display': user_profile.get_processing_mode_display(),
                'message': '已切换到' + user_profile.get_processing_mode_display()
            })
    
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"处理模式设置失败: {e}")
        return JsonResponse({
            'error': f'操作失败: {str(e)}'
        }, status=500)


# ==================== 药单管理API ====================

@csrf_exempt
@require_http_methods(["GET", "POST"])
@login_required
def api_medications(request):
    """获取或创建药单"""
    if request.method == 'GET':
        # 获取用户的所有药单
        from .models import Medication
        medications = Medication.objects.filter(user=request.user).order_by('-created_at')

        medication_list = []
        for med in medications:
            medication_list.append({
                'id': med.id,
                'medicine_name': med.medicine_name,
                'dosage': med.dosage,
                'start_date': med.start_date.strftime('%Y-%m-%d'),
                'end_date': med.end_date.strftime('%Y-%m-%d'),
                'notes': med.notes,
                'is_active': med.is_active,
                'total_days': med.total_days,
                'days_taken': med.days_taken,
                'progress_percentage': med.progress_percentage,
                'created_at': med.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

        return JsonResponse({
            'success': True,
            'medications': medication_list
        })

    elif request.method == 'POST':
        # 创建新药单
        try:
            data = json.loads(request.body)
            from .models import Medication
            from datetime import datetime

            # 验证必填字段
            if not data.get('medicine_name') or not data.get('dosage'):
                return JsonResponse({
                    'success': False,
                    'error': '药名和服药方式为必填项'
                }, status=400)

            if not data.get('start_date') or not data.get('end_date'):
                return JsonResponse({
                    'success': False,
                    'error': '开始日期和结束日期为必填项'
                }, status=400)

            # 创建药单
            medication = Medication.objects.create(
                user=request.user,
                medicine_name=data['medicine_name'],
                dosage=data['dosage'],
                start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
                notes=data.get('notes', '')
            )

            return JsonResponse({
                'success': True,
                'medication': {
                    'id': medication.id,
                    'medicine_name': medication.medicine_name,
                    'dosage': medication.dosage,
                    'start_date': medication.start_date.strftime('%Y-%m-%d'),
                    'end_date': medication.end_date.strftime('%Y-%m-%d'),
                    'notes': medication.notes,
                    'is_active': medication.is_active,
                    'total_days': medication.total_days,
                    'days_taken': medication.days_taken,
                    'progress_percentage': medication.progress_percentage,
                }
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'创建药单失败: {str(e)}'
            }, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@login_required
def api_medication_detail(request, medication_id):
    """获取、更新或删除单个药单"""
    from .models import Medication

    try:
        medication = get_object_or_404(Medication, id=medication_id, user=request.user)
    except:
        return JsonResponse({
            'success': False,
            'error': '药单不存在或无权访问'
        }, status=404)

    if request.method == 'GET':
        # 获取药单详情及服药记录
        from .models import MedicationRecord
        records = MedicationRecord.objects.filter(medication=medication).order_by('-record_date')

        record_list = []
        for record in records:
            record_list.append({
                'id': record.id,
                'record_date': record.record_date.strftime('%Y-%m-%d'),
                'taken_at': record.taken_at.strftime('%Y-%m-%d %H:%M:%S'),
                'notes': record.notes,
                'frequency': record.frequency,
                'frequency_display': record.get_frequency_display(),
            })

        return JsonResponse({
            'success': True,
            'medication': {
                'id': medication.id,
                'medicine_name': medication.medicine_name,
                'dosage': medication.dosage,
                'start_date': medication.start_date.strftime('%Y-%m-%d'),
                'end_date': medication.end_date.strftime('%Y-%m-%d'),
                'notes': medication.notes,
                'is_active': medication.is_active,
                'total_days': medication.total_days,
                'days_taken': medication.days_taken,
                'progress_percentage': medication.progress_percentage,
            },
            'records': record_list
        })

    elif request.method == 'PUT':
        # 更新药单
        try:
            data = json.loads(request.body)
            from datetime import datetime

            medication.medicine_name = data.get('medicine_name', medication.medicine_name)
            medication.dosage = data.get('dosage', medication.dosage)
            medication.notes = data.get('notes', medication.notes)
            medication.is_active = data.get('is_active', medication.is_active)

            if data.get('start_date'):
                medication.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            if data.get('end_date'):
                medication.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()

            medication.save()

            return JsonResponse({
                'success': True,
                'medication': {
                    'id': medication.id,
                    'medicine_name': medication.medicine_name,
                    'dosage': medication.dosage,
                    'start_date': medication.start_date.strftime('%Y-%m-%d'),
                    'end_date': medication.end_date.strftime('%Y-%m-%d'),
                    'notes': medication.notes,
                    'is_active': medication.is_active,
                    'total_days': medication.total_days,
                    'days_taken': medication.days_taken,
                    'progress_percentage': medication.progress_percentage,
                }
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'更新药单失败: {str(e)}'
            }, status=500)

    elif request.method == 'DELETE':
        # 删除药单
        medication.delete()
        return JsonResponse({
            'success': True,
            'message': '药单已删除'
        })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_medication_checkin(request):
    """服药签到"""
    try:
        data = json.loads(request.body)
        from .models import Medication, MedicationRecord
        from datetime import datetime

        medication_id = data.get('medication_id')
        record_date = data.get('record_date')
        frequency = data.get('frequency', 'daily')
        notes = data.get('notes', '')

        if not medication_id or not record_date:
            return JsonResponse({
                'success': False,
                'error': '缺少必要参数'
            }, status=400)

        # 获取药单
        try:
            medication = Medication.objects.get(id=medication_id, user=request.user)
        except Medication.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': '药单不存在或无权访问'
            }, status=404)

        # 解析日期
        record_date_obj = datetime.strptime(record_date, '%Y-%m-%d').date()

        # 检查是否已签到
        existing_record = MedicationRecord.objects.filter(
            medication=medication,
            record_date=record_date_obj
        ).first()

        if existing_record:
            return JsonResponse({
                'success': False,
                'error': '今日已签到',
                'existing_record': {
                    'id': existing_record.id,
                    'record_date': existing_record.record_date.strftime('%Y-%m-%d'),
                    'taken_at': existing_record.taken_at.strftime('%Y-%m-%d %H:%M:%S'),
                }
            }, status=400)

        # 创建服药记录
        record = MedicationRecord.objects.create(
            medication=medication,
            record_date=record_date_obj,
            frequency=frequency,
            notes=notes
        )

        return JsonResponse({
            'success': True,
            'record': {
                'id': record.id,
                'record_date': record.record_date.strftime('%Y-%m-%d'),
                'taken_at': record.taken_at.strftime('%Y-%m-%d %H:%M:%S'),
                'frequency': record.frequency,
                'frequency_display': record.get_frequency_display(),
            },
            'medication_progress': {
                'total_days': medication.total_days,
                'days_taken': medication.days_taken,
                'progress_percentage': medication.progress_percentage,
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'签到失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def api_medication_records(request, medication_id):
    """获取药单的服药记录"""
    from .models import Medication, MedicationRecord

    try:
        medication = get_object_or_404(Medication, id=medication_id, user=request.user)
    except:
        return JsonResponse({
            'success': False,
            'error': '药单不存在或无权访问'
        }, status=404)

    records = MedicationRecord.objects.filter(medication=medication).order_by('-record_date')

    record_list = []
    for record in records:
        record_list.append({
            'id': record.id,
            'record_date': record.record_date.strftime('%Y-%m-%d'),
            'taken_at': record.taken_at.strftime('%Y-%m-%d %H:%M:%S'),
            'notes': record.notes,
            'frequency': record.frequency,
            'frequency_display': record.get_frequency_display(),
        })

    return JsonResponse({
        'success': True,
        'records': record_list
    })


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def api_conversation_resources(request, conversation_id):
    """获取对话关联的报告和药单信息"""
    from .models import Conversation, HealthAdvice, HealthCheckup, Medication, HealthEvent

    try:
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user, is_active=True)

        # 获取对话中最新的建议
        latest_advice = HealthAdvice.objects.filter(
            conversation=conversation,
            user=request.user
        ).order_by('-created_at').first()

        if not latest_advice:
            return JsonResponse({
                'success': True,
                'reports': [],
                'medications': [],
                'event': None,
                'message': '对话中没有保存的数据'
            })

        reports = []
        medications = []
        event = None

        # 解析选中的报告
        if latest_advice.selected_reports:
            try:
                report_ids = json.loads(latest_advice.selected_reports)
                if report_ids:
                    reports_qs = HealthCheckup.objects.filter(
                        id__in=report_ids,
                        user=request.user
                    )
                    for report in reports_qs:
                        reports.append({
                            'id': report.id,
                            'hospital': report.hospital,
                            'checkup_date': report.checkup_date.strftime('%Y-%m-%d') if report.checkup_date else '',
                        })
            except json.JSONDecodeError:
                pass

        # 解析选中的药单
        if latest_advice.selected_medications:
            try:
                medication_ids = json.loads(latest_advice.selected_medications)
                if medication_ids:
                    medications_qs = Medication.objects.filter(
                        id__in=medication_ids,
                        user=request.user,
                        is_active=True
                    )
                    for med in medications_qs:
                        medications.append({
                            'id': med.id,
                            'medicine_name': med.medicine_name,
                            'start_date': med.start_date.strftime('%Y-%m-%d') if med.start_date else '',
                            'end_date': med.end_date.strftime('%Y-%m-%d') if med.end_date else '',
                            'total_days': med.total_days,
                            'days_taken': med.days_taken,
                            'progress_percentage': med.progress_percentage,
                            'dosage': med.dosage,
                        })
            except json.JSONDecodeError:
                pass

        # 解析选中的事件
        if latest_advice.selected_event:
            try:
                event_obj = HealthEvent.objects.get(id=latest_advice.selected_event, user=request.user)
                event = {
                    'id': event_obj.id,
                    'name': event_obj.name,
                }
            except HealthEvent.DoesNotExist:
                pass

        return JsonResponse({
            'success': True,
            'reports': reports,
            'medications': medications,
            'event': event
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取对话资源失败: {str(e)}'
        }, status=500)

# ============================================================================
# 健康事件聚合 API
# ============================================================================

def _valid_event_statuses():
    return {choice[0] for choice in HealthEvent.EVENT_STATUS_CHOICES}


def _serialize_event(event):
    return {
        'id': event.id,
        'name': event.name,
        'description': event.description,
        'event_type': event.event_type,
        'event_type_display': event.get_event_type_display(),
        'status': event.status,
        'status_display': event.get_status_display(),
        'start_date': event.start_date.strftime('%Y-%m-%d') if event.start_date else None,
        'end_date': event.end_date.strftime('%Y-%m-%d') if event.end_date else None,
        'duration_days': event.duration_days,
        'item_count': event.get_item_count(),
        'is_auto_generated': event.is_auto_generated,
        'created_at': event.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'updated_at': event.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_events(request):
    """
    GET: 获取用户的健康事件列表
    POST: 创建新的健康事件
    """
    if request.method == 'GET':
        # 获取查询参数
        event_type = request.GET.get('event_type')
        status = request.GET.get('status')
        is_auto = request.GET.get('is_auto_generated')
        limit = int(request.GET.get('limit', 50))

        # 构建查询
        events = HealthEvent.objects.filter(user=request.user)

        if event_type:
            events = events.filter(event_type=event_type)
        if status:
            events = events.filter(status=status)
        if is_auto is not None:
            is_auto_bool = is_auto.lower() == 'true'
            events = events.filter(is_auto_generated=is_auto_bool)

        events = events[:limit]

        # 序列化数据
        events_data = []
        for event in events:
            events_data.append(_serialize_event(event))

        return JsonResponse({
            'success': True,
            'events': events_data,
            'count': len(events_data)
        })

    elif request.method == 'POST':
        # 创建新事件
        try:
            data = request.data
            name = data.get('name')
            description = data.get('description', '')
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            event_type = data.get('event_type', 'other')
            status = data.get('status', HealthEvent.STATUS_OBSERVING)

            if not name:
                return JsonResponse({
                    'success': False,
                    'error': '事件名称不能为空'
                }, status=400)

            if not start_date:
                return JsonResponse({
                    'success': False,
                    'error': '开始日期不能为空'
                }, status=400)

            valid_statuses = _valid_event_statuses()
            if status not in valid_statuses:
                return JsonResponse({
                    'success': False,
                    'error': f'无效状态: {status}，支持的状态: {", ".join(sorted(valid_statuses))}'
                }, status=400)

            from datetime import datetime
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            if end_date:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()

            event = HealthEvent.objects.create(
                user=request.user,
                name=name,
                description=description,
                start_date=start_date,
                end_date=end_date,
                event_type=event_type,
                status=status,
                is_auto_generated=False
            )

            return JsonResponse({
                'success': True,
                'event': _serialize_event(event)
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'创建事件失败: {str(e)}'
            }, status=500)


# ============================================================================
# 健康计划 - AI建议行动
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_care_goal_suggest_actions(request, goal_id):
    """为目标生成AI建议行动"""
    goal = get_object_or_404(CareGoal, id=goal_id, plan__user=request.user)
    prompt = (
        f"请为以下健康目标生成3-6条可执行的行动建议，"
        f"每条建议尽量简短明确：\n目标：{goal.title}\n"
        f"如果目标包含数值，请给出可操作的日常建议。"
    )

    answer, error = call_ai_doctor_api(prompt, None, request.user)
    if error:
        return JsonResponse({'success': False, 'error': error}, status=400)

    suggestions = []
    for line in (answer or '').splitlines():
        cleaned = line.strip().lstrip('•-*0123456789.、) ')
        if cleaned:
            suggestions.append(cleaned)

    # 限制数量避免噪音
    suggestions = suggestions[:8]

    return JsonResponse({
        'success': True,
        'suggestions': suggestions,
        'raw': answer
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_care_goal_add_actions(request, goal_id):
    """批量添加行动"""
    goal = get_object_or_404(CareGoal, id=goal_id, plan__user=request.user)
    actions = request.data.get('actions', [])

    if isinstance(actions, str):
        actions = [a.strip() for a in actions.split('\n') if a.strip()]

    if not isinstance(actions, list) or len(actions) == 0:
        return JsonResponse({'success': False, 'error': '未提供行动列表'}, status=400)

    created = 0
    for title in actions:
        if not title:
            continue
        CareAction.objects.create(
            goal=goal,
            title=title[:200],
            suggested_by_ai=True
        )
        created += 1

    goal.recalculate_progress()

    return JsonResponse({'success': True, 'created': created})


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_event_detail(request, event_id):
    """
    GET: 获取事件详情（包含关联的记录）
    PUT: 更新事件
    DELETE: 删除事件
    """
    try:
        event = get_object_or_404(HealthEvent, id=event_id, user=request.user)

        if request.method == 'GET':
            # 获取事件关联的所有项目
            items = event.event_items.all()
            items_data = []

            for item in items:
                items_data.append({
                    'id': item.id,
                    'item_summary': item.item_summary,
                    'content_type': item.content_type.model,
                    'object_id': item.object_id,
                    'notes': item.notes,
                    'added_by': item.added_by,
                    'added_at': item.added_at.strftime('%Y-%m-%d %H:%M:%S'),
                })

            return JsonResponse({
                'success': True,
                'event': _serialize_event(event),
                'items': items_data
            })

        elif request.method == 'PUT':
            # 更新事件
            try:
                data = request.data

                if 'name' in data:
                    event.name = data['name']
                if 'description' in data:
                    event.description = data['description']
                if 'event_type' in data:
                    event.event_type = data['event_type']
                if 'status' in data:
                    new_status = data['status']
                    valid_statuses = _valid_event_statuses()
                    if new_status not in valid_statuses:
                        return JsonResponse({
                            'success': False,
                            'error': f'无效状态: {new_status}，支持的状态: {", ".join(sorted(valid_statuses))}'
                        }, status=400)
                    event.status = new_status
                if 'start_date' in data:
                    from datetime import datetime
                    event.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
                if 'end_date' in data:
                    if data['end_date']:
                        from datetime import datetime
                        event.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
                    else:
                        event.end_date = None

                event.save()

                return JsonResponse({
                    'success': True,
                    'event': _serialize_event(event)
                })

            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': f'更新事件失败: {str(e)}'
                }, status=500)

        elif request.method == 'DELETE':
            # 删除事件
            event.delete()
            return JsonResponse({
                'success': True,
                'message': '事件已删除'
            })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'操作失败: {str(e)}'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_event_add_item(request, event_id):
    """
    向事件添加健康记录
    """
    try:
        event = get_object_or_404(HealthEvent, id=event_id, user=request.user)

        data = request.data
        content_type_str = data.get('content_type')  # 'healthcheckup', 'medication', etc.
        object_id = data.get('object_id')
        notes = data.get('notes', '')

        if not content_type_str or not object_id:
            return JsonResponse({
                'success': False,
                'error': 'content_type 和 object_id 参数必填'
            }, status=400)

        # 获取 ContentType
        try:
            content_type = ContentType.objects.get(model=content_type_str)
        except ContentType.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': f'无效的内容类型: {content_type_str}'
            }, status=400)

        # 检查对象是否存在且属于当前用户
        obj = content_type.get_object_for_this_type(id=object_id)
        if hasattr(obj, 'user') and obj.user != request.user:
            return JsonResponse({
                'success': False,
                'error': '无权添加该记录'
            }, status=403)

        # 检查是否已经添加
        if EventItem.objects.filter(
            event=event,
            content_type=content_type,
            object_id=object_id
        ).exists():
            return JsonResponse({
                'success': False,
                'error': '该记录已添加到此事件'
            }, status=400)

        # 创建 EventItem
        item = EventItem.objects.create(
            event=event,
            content_type=content_type,
            object_id=object_id,
            notes=notes,
            added_by='manual'
        )

        return JsonResponse({
            'success': True,
            'item': {
                'id': item.id,
                'item_summary': item.item_summary,
                'content_type': item.content_type.model,
                'object_id': item.object_id,
                'notes': item.notes,
                'added_by': item.added_by,
                'added_at': item.added_at.strftime('%Y-%m-%d %H:%M:%S'),
            },
            'event_item_count': event.get_item_count()
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'添加记录失败: {str(e)}'
        }, status=500)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def api_event_remove_item(request, event_id, item_id):
    """
    从事件中移除健康记录
    """
    try:
        event = get_object_or_404(HealthEvent, id=event_id, user=request.user)
        item = get_object_or_404(EventItem, id=item_id, event=event)

        item.delete()

        return JsonResponse({
            'success': True,
            'message': '记录已移除',
            'event_item_count': event.get_item_count()
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'移除记录失败: {str(e)}'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_event_auto_cluster(request):
    """
    为当前用户触发自动聚类
    """
    try:
        # Get days_threshold from request.data
        data = request.data if request.data else {}
        days_threshold = int(data.get('days_threshold', 7))

        # 执行自动聚类
        events_created = HealthEvent.auto_cluster_user_records(request.user, days_threshold)

        return JsonResponse({
            'success': True,
            'events_created': events_created,
            'message': f'已自动创建 {events_created} 个事件'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'自动聚类失败: {str(e)}'
        }, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_event_recluster(request):
    """
    重新聚类：删除所有事件并根据新的时间阈值重新聚类
    """
    try:
        data = request.data if request.data else {}
        days_threshold = int(data.get('days_threshold', 7))

        # 删除当前用户的所有事件（会级联删除EventItem）
        deleted_count = HealthEvent.objects.filter(user=request.user).delete()[0]

        # 执行自动聚类
        events_created = HealthEvent.auto_cluster_user_records(request.user, days_threshold)

        return JsonResponse({
            'success': True,
            'events_deleted': deleted_count,
            'events_created': events_created,
            'message': f'已删除 {deleted_count} 个事件，重新创建了 {events_created} 个事件'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'重新聚类失败: {str(e)}'
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_event_available_items(request):
    """
    获取可以添加到事件的记录列表
    """
    try:
        content_type = request.GET.get('content_type', 'all')
        limit = int(request.GET.get('limit', 50))

        items = []

        # 获取体检报告
        if content_type in ['all', 'healthcheckup']:
            checkups = HealthCheckup.objects.filter(user=request.user)[:limit]
            for checkup in checkups:
                items.append({
                    'content_type': 'healthcheckup',
                    'object_id': checkup.id,
                    'summary': f"体检报告: {checkup.checkup_date} - {checkup.hospital}",
                    'date': checkup.checkup_date.strftime('%Y-%m-%d'),
                })

        # 获取药单组
        if content_type in ['all', 'medicationgroup']:
            from .models import MedicationGroup
            groups = MedicationGroup.objects.filter(user=request.user)[:limit]
            for group in groups:
                med_names = ', '.join([m.medicine_name for m in group.medications.all()[:3]])
                if group.medication_count > 3:
                    med_names += f' 等{group.medication_count}个'
                items.append({
                    'content_type': 'medicationgroup',
                    'object_id': group.id,
                    'summary': f"药单组: {group.name} ({med_names})",
                    'date': group.created_at.strftime('%Y-%m-%d'),
                })

        # 获取药单（只获取未分组的）
        if content_type in ['all', 'medication']:
            medications = Medication.objects.filter(user=request.user, is_active=True, group__isnull=True)[:limit]
            for med in medications:
                items.append({
                    'content_type': 'medication',
                    'object_id': med.id,
                    'summary': f"药单: {med.medicine_name} ({med.start_date} 至 {med.end_date})",
                    'date': med.start_date.strftime('%Y-%m-%d'),
                })

        # 获取健康指标
        if content_type in ['all', 'healthindicator']:
            indicators = HealthIndicator.objects.filter(
                checkup__user=request.user
            ).select_related('checkup')[:limit]
            for indicator in indicators:
                items.append({
                    'content_type': 'healthindicator',
                    'object_id': indicator.id,
                    'summary': f"指标: {indicator.indicator_name} = {indicator.value} {indicator.unit or ''}",
                    'date': indicator.checkup.checkup_date.strftime('%Y-%m-%d'),
                })

        # 按日期排序
        items.sort(key=lambda x: x['date'], reverse=True)

        return JsonResponse({
            'success': True,
            'items': items[:limit],
            'count': len(items[:limit])
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取记录列表失败: {str(e)}'
        }, status=500)


@csrf_exempt
@login_required
def upload_avatar(request):
    """上传用户头像"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '只支持 POST 请求'}, status=405)

    try:
        # 获取上传的文件
        if 'avatar' not in request.FILES:
            return JsonResponse({'success': False, 'error': '未找到上传文件'}, status=400)

        avatar_file = request.FILES['avatar']

        # 验证文件类型
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if avatar_file.content_type not in allowed_types:
            return JsonResponse({'success': False, 'error': '只支持 JPG、PNG、GIF、WEBP 格式的图片'}, status=400)

        # 验证文件大小（限制为 5MB）
        max_size = 5 * 1024 * 1024  # 5MB
        if avatar_file.size > max_size:
            return JsonResponse({'success': False, 'error': '图片大小不能超过 5MB'}, status=400)

        # 创建 avatars 目录
        from django.conf import settings
        avatars_dir = os.path.join(settings.MEDIA_ROOT, 'avatars')
        os.makedirs(avatars_dir, exist_ok=True)

        # 生成唯一文件名
        import uuid
        file_ext = os.path.splitext(avatar_file.name)[1]
        unique_filename = f"{request.user.id}_{uuid.uuid4().hex[:8]}{file_ext}"
        file_path = os.path.join(avatars_dir, unique_filename)

        # 保存文件
        with open(file_path, 'wb+') as destination:
            for chunk in avatar_file.chunks():
                destination.write(chunk)

        # 构建 URL
        avatar_url = f"{settings.MEDIA_URL}avatars/{unique_filename}"

        # 更新用户头像
        from .models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.avatar_url = avatar_url
        profile.save(update_fields=['avatar_url'])

        return JsonResponse({
            'success': True,
            'avatar_url': avatar_url,
            'message': '头像上传成功'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'上传失败: {str(e)}'
        }, status=500)


@csrf_exempt
@login_required
def api_medication_recognize_image(request):
    """识别药单图片并创建药单组"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '只支持 POST 请求'}, status=405)

    try:
        if 'image' not in request.FILES:
            return JsonResponse({'success': False, 'error': '未找到上传的图片'}, status=400)

        image_file = request.FILES['image']

        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if image_file.content_type not in allowed_types:
            return JsonResponse({'success': False, 'error': '只支持 JPG、PNG、GIF、WEBP 格式的图片'}, status=400)

        max_size = 10 * 1024 * 1024
        if image_file.size > max_size:
            return JsonResponse({'success': False, 'error': '图片大小不能超过 10MB'}, status=400)

        from django.conf import settings
        import uuid
        import tempfile
        import os

        temp_dir = tempfile.mkdtemp()
        file_ext = os.path.splitext(image_file.name)[1]
        temp_file_path = os.path.join(temp_dir, f"medication_{uuid.uuid4().hex}{file_ext}")

        with open(temp_file_path, 'wb+') as destination:
            for chunk in image_file.chunks():
                destination.write(chunk)

        from .services import MedicationRecognitionService
        from .models import MedicationGroup, Medication

        service = MedicationRecognitionService()
        result = service.recognize_medication_image(temp_file_path)

        try:
            os.unlink(temp_file_path)
            os.rmdir(temp_dir)
        except:
            pass

        medications_data = result.get('medications', [])
        summary = result.get('summary', '')

        if not medications_data:
            return JsonResponse({
                'success': False,
                'error': '未能从图片中识别出药物信息'
            }, status=400)

        group_name = f"药单组 {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        medication_group = MedicationGroup.objects.create(
            user=request.user,
            name=group_name,
            ai_summary=summary,
            raw_result=result
        )

        if image_file:
            medication_group.source_image.save(
                f"medication_{uuid.uuid4().hex}{file_ext}",
                image_file,
                save=True
            )

        created_medications = []
        from datetime import datetime as dt

        for med_data in medications_data:
            medicine_name = med_data.get('medicine_name', '').strip()
            dosage = med_data.get('dosage', '').strip()

            if not medicine_name:
                continue

            start_date_str = med_data.get('start_date')
            end_date_str = med_data.get('end_date')

            try:
                if start_date_str and start_date_str != 'null':
                    start_date = dt.strptime(start_date_str, '%Y-%m-%d').date()
                else:
                    start_date = timezone.now().date()
            except:
                start_date = timezone.now().date()

            try:
                if end_date_str and end_date_str != 'null':
                    end_date = dt.strptime(end_date_str, '%Y-%m-%d').date()
                else:
                    end_date = start_date + timedelta(days=7)
            except:
                end_date = start_date + timedelta(days=7)

            notes = med_data.get('notes', '')
            if notes == 'null':
                notes = ''

            medication = Medication.objects.create(
                user=request.user,
                group=medication_group,
                medicine_name=medicine_name,
                dosage=dosage or '按医嘱服用',
                start_date=start_date,
                end_date=end_date,
                notes=notes
            )

            created_medications.append({
                'id': medication.id,
                'medicine_name': medication.medicine_name,
                'dosage': medication.dosage,
                'start_date': medication.start_date.strftime('%Y-%m-%d'),
                'end_date': medication.end_date.strftime('%Y-%m-%d'),
                'notes': medication.notes,
                'total_days': medication.total_days,
            })

        return JsonResponse({
            'success': True,
            'group': {
                'id': medication_group.id,
                'name': medication_group.name,
                'ai_summary': medication_group.ai_summary,
                'medication_count': len(created_medications),
                'created_at': medication_group.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            },
            'medications': created_medications,
            'raw_result': result
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'识别失败: {str(e)}'
        }, status=500)


@csrf_exempt
@login_required
def api_medication_groups(request):
    """获取用户的药单组列表"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': '只支持 GET 请求'}, status=405)

    from .models import MedicationGroup, Medication

    groups = MedicationGroup.objects.filter(user=request.user).order_by('-created_at')

    group_list = []
    for group in groups:
        medications = Medication.objects.filter(group=group)
        medication_list = []
        for med in medications:
            medication_list.append({
                'id': med.id,
                'medicine_name': med.medicine_name,
                'dosage': med.dosage,
                'start_date': med.start_date.strftime('%Y-%m-%d'),
                'end_date': med.end_date.strftime('%Y-%m-%d'),
                'notes': med.notes,
                'is_active': med.is_active,
                'total_days': med.total_days,
                'days_taken': med.days_taken,
                'progress_percentage': med.progress_percentage,
            })

        group_list.append({
            'id': group.id,
            'name': group.name,
            'ai_summary': group.ai_summary,
            'source_image': group.source_image.url if group.source_image else None,
            'medication_count': group.medication_count,
            'created_at': group.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'medications': medication_list,
        })

    return JsonResponse({
        'success': True,
        'groups': group_list
    })


@csrf_exempt
@login_required
def api_medication_group_detail(request, group_id):
    """获取、更新或删除药单组"""
    from .models import MedicationGroup, Medication

    try:
        group = get_object_or_404(MedicationGroup, id=group_id, user=request.user)
    except:
        return JsonResponse({
            'success': False,
            'error': '药单组不存在或无权访问'
        }, status=404)

    if request.method == 'GET':
        medications = Medication.objects.filter(group=group)
        medication_list = []
        for med in medications:
            medication_list.append({
                'id': med.id,
                'medicine_name': med.medicine_name,
                'dosage': med.dosage,
                'start_date': med.start_date.strftime('%Y-%m-%d'),
                'end_date': med.end_date.strftime('%Y-%m-%d'),
                'notes': med.notes,
                'is_active': med.is_active,
                'total_days': med.total_days,
                'days_taken': med.days_taken,
                'progress_percentage': med.progress_percentage,
            })

        return JsonResponse({
            'success': True,
            'group': {
                'id': group.id,
                'name': group.name,
                'ai_summary': group.ai_summary,
                'source_image': group.source_image.url if group.source_image else None,
                'medication_count': group.medication_count,
                'created_at': group.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            },
            'medications': medication_list
        })

    elif request.method == 'DELETE':
        group.delete()
        return JsonResponse({
            'success': True,
            'message': '药单组已删除'
        })

    return JsonResponse({'success': False, 'error': '不支持的请求方法'}, status=405)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_medication_group_create(request):
    """创建药单组（手动选择药物组成）"""
    from .models import MedicationGroup, Medication

    try:
        data = json.loads(request.body)

        name = data.get('name', '').strip()
        medication_ids = data.get('medication_ids', [])
        notes = data.get('notes', '')

        if not medication_ids:
            return JsonResponse({
                'success': False,
                'error': '请选择要加入药单组的药物'
            }, status=400)

        if not name:
            today_str = datetime.now().strftime('%Y-%m-%d')
            name = f'药单组 {today_str}'

        group = MedicationGroup.objects.create(
            user=request.user,
            name=name,
            ai_summary=notes
        )

        updated_count = Medication.objects.filter(
            id__in=medication_ids,
            user=request.user,
            group__isnull=True
        ).update(group=group)

        return JsonResponse({
            'success': True,
            'message': f'成功创建药单组，包含 {updated_count} 个药物',
            'group': {
                'id': group.id,
                'name': group.name,
                'ai_summary': group.ai_summary,
                'medication_count': updated_count,
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'创建药单组失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_medication_group_checkin(request, group_id):
    """药单组批量签到"""
    from .models import MedicationGroup, Medication, MedicationRecord

    try:
        group = MedicationGroup.objects.get(id=group_id, user=request.user)
    except MedicationGroup.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '药单组不存在或无权访问'
        }, status=404)

    try:
        data = json.loads(request.body)
        record_date = data.get('record_date')
        frequency = data.get('frequency', 'daily')
        notes = data.get('notes', '')

        if not record_date:
            record_date = datetime.now().strftime('%Y-%m-%d')

        record_date_obj = datetime.strptime(record_date, '%Y-%m-%d').date()

        medications = Medication.objects.filter(group=group, is_active=True)

        success_count = 0
        skipped_count = 0

        for med in medications:
            existing = MedicationRecord.objects.filter(
                medication=med,
                record_date=record_date_obj
            ).first()

            if existing:
                skipped_count += 1
            else:
                MedicationRecord.objects.create(
                    medication=med,
                    record_date=record_date_obj,
                    frequency=frequency,
                    notes=notes
                )
                success_count += 1

        return JsonResponse({
            'success': True,
            'message': f'批量签到完成：成功 {success_count} 个，跳过 {skipped_count} 个',
            'success_count': success_count,
            'skipped_count': skipped_count
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'批量签到失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_medication_auto_cluster(request):
    """按时间自动聚类药单"""
    from .models import MedicationGroup, Medication
    from collections import defaultdict

    try:
        data = json.loads(request.body)
        days_threshold = data.get('days_threshold', 3)

        ungrouped_medications = Medication.objects.filter(
            user=request.user,
            group__isnull=True
        ).order_by('start_date')

        if not ungrouped_medications.exists():
            return JsonResponse({
                'success': True,
                'message': '没有需要聚类的药单',
                'groups_created': 0
            })

        clusters = defaultdict(list)
        current_cluster_start = None
        current_cluster_meds = []

        for med in ungrouped_medications:
            if current_cluster_start is None:
                current_cluster_start = med.start_date
                current_cluster_meds = [med]
            else:
                days_diff = (med.start_date - current_cluster_start).days
                if days_diff <= days_threshold:
                    current_cluster_meds.append(med)
                else:
                    if len(current_cluster_meds) > 0:
                        cluster_key = current_cluster_start.strftime('%Y-%m-%d')
                        clusters[cluster_key] = current_cluster_meds
                    current_cluster_start = med.start_date
                    current_cluster_meds = [med]

        if current_cluster_meds:
            cluster_key = current_cluster_start.strftime('%Y-%m-%d')
            clusters[cluster_key] = current_cluster_meds

        groups_created = 0

        for cluster_date, meds in clusters.items():
            if len(meds) < 2:
                continue

            group_name = f'药单组 {cluster_date}'
            group = MedicationGroup.objects.create(
                user=request.user,
                name=group_name,
                ai_summary=f'自动聚类：包含 {len(meds)} 个药物，起始日期接近'
            )

            for med in meds:
                med.group = group
                med.save()

            groups_created += 1

        return JsonResponse({
            'success': True,
            'message': f'自动聚类完成，创建了 {groups_created} 个药单组',
            'groups_created': groups_created
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'自动聚类失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def api_medications_without_group(request):
    """获取未分组的药单列表"""
    from .models import Medication

    medications = Medication.objects.filter(
        user=request.user,
        group__isnull=True
    ).order_by('-created_at')

    medication_list = []
    for med in medications:
        medication_list.append({
            'id': med.id,
            'medicine_name': med.medicine_name,
            'dosage': med.dosage,
            'start_date': med.start_date.strftime('%Y-%m-%d'),
            'end_date': med.end_date.strftime('%Y-%m-%d'),
            'notes': med.notes,
            'is_active': med.is_active,
            'total_days': med.total_days,
            'days_taken': med.days_taken,
            'progress_percentage': med.progress_percentage,
        })

    return JsonResponse({
        'success': True,
        'medications': medication_list,
        'count': len(medication_list)
    })


@csrf_exempt
@require_http_methods(["PUT"])
@login_required
def api_medication_group_update(request, group_id):
    """更新药单组（添加/移除药物）"""
    from .models import MedicationGroup, Medication

    try:
        group = MedicationGroup.objects.get(id=group_id, user=request.user)
    except MedicationGroup.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '药单组不存在或无权访问'
        }, status=404)

    try:
        data = json.loads(request.body)

        if data.get('name'):
            group.name = data['name'].strip()
        if data.get('notes') is not None:
            group.ai_summary = data['notes']
        group.save()

        if data.get('add_medication_ids'):
            Medication.objects.filter(
                id__in=data['add_medication_ids'],
                user=request.user
            ).update(group=group)

        if data.get('remove_medication_ids'):
            Medication.objects.filter(
                id__in=data['remove_medication_ids'],
                user=request.user,
                group=group
            ).update(group=None)

        current_medication_count = Medication.objects.filter(group=group).count()
        if current_medication_count == 0:
            group_name = group.name
            group.delete()
            return JsonResponse({
                'success': True,
                'message': f'药单组"{group_name}"已自动删除（空集合）',
                'medication_count': 0,
                'group_deleted': True
            })

        return JsonResponse({
            'success': True,
            'message': '药单组已更新',
            'medication_count': current_medication_count
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'更新药单组失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_medication_group_dissolve(request, group_id):
    """解散药单组（保留药物，只删除分组）"""
    from .models import MedicationGroup, Medication

    try:
        group = MedicationGroup.objects.get(id=group_id, user=request.user)
    except MedicationGroup.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '药单组不存在或无权访问'
        }, status=404)

    try:
        medication_count = Medication.objects.filter(group=group).count()

        Medication.objects.filter(group=group).update(group=None)

        group_name = group.name
        group.delete()

        return JsonResponse({
            'success': True,
            'message': f'已解散药单组"{group_name}"，{medication_count} 个药物已变为独立药单'
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'解散药单组失败: {str(e)}'
        }, status=500)


# ============================================================================
# 健康日志API (症状日志 & 体征日志)
# ============================================================================

@csrf_exempt
@require_http_methods(["GET", "POST"])
@login_required
def api_symptom_logs(request):
    """
    症状日志API

    GET: 获取症状日志列表
    - 支持查询参数: start_date, end_date, symptom, severity

    POST: 创建新的症状日志
    """
    from .models import SymptomEntry

    if request.method == 'GET':
        # 获取症状日志列表
        queryset = SymptomEntry.objects.filter(user=request.user)

        # 支持日期范围筛选
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(entry_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(entry_date__lte=end_date)

        # 支持症状名称搜索
        symptom = request.GET.get('symptom')
        if symptom:
            queryset = queryset.filter(symptom__icontains=symptom)

        # 支持严重程度筛选
        severity = request.GET.get('severity')
        if severity:
            queryset = queryset.filter(severity=severity)

        queryset = queryset.order_by('-entry_date', '-created_at')

        logs = []
        for log in queryset:
            logs.append({
                'id': log.id,
                'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                'symptom': log.symptom,
                'severity': log.severity,
                'severity_display': log.get_severity_display(),
                'notes': log.notes or '',
                'related_checkup_id': log.related_checkup_id,
                'related_medication_id': log.related_medication_id,
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': log.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

        return JsonResponse({
            'success': True,
            'logs': logs,
            'count': len(logs)
        })

    elif request.method == 'POST':
        # 创建新的症状日志
        try:
            data = json.loads(request.body)

            symptom = data.get('symptom', '').strip()
            if not symptom:
                return JsonResponse({
                    'success': False,
                    'error': '症状名称不能为空'
                }, status=400)

            from datetime import datetime
            entry_date = data.get('entry_date')
            if entry_date:
                entry_date = datetime.strptime(entry_date, '%Y-%m-%d').date()

            log = SymptomEntry.objects.create(
                user=request.user,
                entry_date=entry_date,
                symptom=symptom,
                severity=data.get('severity', 3),
                notes=data.get('notes', '').strip(),
                related_checkup_id=data.get('related_checkup_id'),
                related_medication_id=data.get('related_medication_id'),
            )

            return JsonResponse({
                'success': True,
                'message': '症状日志已创建',
                'log': {
                    'id': log.id,
                    'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                    'symptom': log.symptom,
                    'severity': log.severity,
                    'severity_display': log.get_severity_display(),
                    'notes': log.notes or '',
                }
            }, status=201)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'创建症状日志失败: {str(e)}'
            }, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@login_required
def api_symptom_log_detail(request, log_id):
    """
    症状日志详情API

    GET: 获取单条症状日志详情
    PUT: 更新症状日志
    DELETE: 删除症状日志
    """
    from .models import SymptomEntry

    try:
        log = SymptomEntry.objects.get(id=log_id, user=request.user)
    except SymptomEntry.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '症状日志不存在或无权访问'
        }, status=404)

    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'log': {
                'id': log.id,
                'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                'symptom': log.symptom,
                'severity': log.severity,
                'severity_display': log.get_severity_display(),
                'notes': log.notes or '',
                'related_checkup_id': log.related_checkup_id,
                'related_medication_id': log.related_medication_id,
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': log.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })

    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)

            if data.get('symptom'):
                log.symptom = data['symptom'].strip()
            if data.get('entry_date'):
                from datetime import datetime
                log.entry_date = datetime.strptime(data['entry_date'], '%Y-%m-%d').date()
            if data.get('severity') is not None:
                log.severity = data['severity']
            if data.get('notes') is not None:
                log.notes = data['notes'].strip()
            if data.get('related_checkup_id') is not None:
                log.related_checkup_id = data['related_checkup_id']
            if data.get('related_medication_id') is not None:
                log.related_medication_id = data['related_medication_id']

            log.save()

            return JsonResponse({
                'success': True,
                'message': '症状日志已更新',
                'log': {
                    'id': log.id,
                    'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                    'symptom': log.symptom,
                    'severity': log.severity,
                    'severity_display': log.get_severity_display(),
                    'notes': log.notes or '',
                }
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'更新症状日志失败: {str(e)}'
            }, status=500)

    elif request.method == 'DELETE':
        symptom_name = log.symptom
        log.delete()

        return JsonResponse({
            'success': True,
            'message': f'症状日志"{symptom_name}"已删除'
        })


@csrf_exempt
@require_http_methods(["GET", "POST"])
@login_required
def api_vital_logs(request):
    """
    体征日志API

    GET: 获取体征日志列表
    - 支持查询参数: start_date, end_date, vital_type

    POST: 创建新的体征日志
    """
    from .models import VitalEntry

    if request.method == 'GET':
        # 获取体征日志列表
        queryset = VitalEntry.objects.filter(user=request.user)

        # 支持日期范围筛选
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(entry_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(entry_date__lte=end_date)

        # 支持体征类型筛选
        vital_type = request.GET.get('vital_type')
        if vital_type:
            queryset = queryset.filter(vital_type=vital_type)

        queryset = queryset.order_by('-entry_date', '-created_at')

        logs = []
        for log in queryset:
            logs.append({
                'id': log.id,
                'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                'vital_type': log.vital_type,
                'vital_type_display': log.get_vital_type_display(),
                'value': log.value,
                'unit': log.unit or '',
                'notes': log.notes or '',
                'related_checkup_id': log.related_checkup_id,
                'related_medication_id': log.related_medication_id,
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': log.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

        return JsonResponse({
            'success': True,
            'logs': logs,
            'count': len(logs)
        })

    elif request.method == 'POST':
        # 创建新的体征日志
        try:
            data = json.loads(request.body)

            vital_type = data.get('vital_type', '').strip()
            if not vital_type:
                return JsonResponse({
                    'success': False,
                    'error': '体征类型不能为空'
                }, status=400)

            value = data.get('value', '').strip()
            if not value:
                return JsonResponse({
                    'success': False,
                    'error': '数值不能为空'
                }, status=400)

            from datetime import datetime
            entry_date = data.get('entry_date')
            if entry_date:
                entry_date = datetime.strptime(entry_date, '%Y-%m-%d').date()

            log = VitalEntry.objects.create(
                user=request.user,
                entry_date=entry_date,
                vital_type=vital_type,
                value=value,
                unit=data.get('unit', '').strip(),
                notes=data.get('notes', '').strip(),
                related_checkup_id=data.get('related_checkup_id'),
                related_medication_id=data.get('related_medication_id'),
            )

            return JsonResponse({
                'success': True,
                'message': '体征日志已创建',
                'log': {
                    'id': log.id,
                    'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                    'vital_type': log.vital_type,
                    'vital_type_display': log.get_vital_type_display(),
                    'value': log.value,
                    'unit': log.unit or '',
                    'notes': log.notes or '',
                }
            }, status=201)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'创建体征日志失败: {str(e)}'
            }, status=500)


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@login_required
def api_vital_log_detail(request, log_id):
    """
    体征日志详情API

    GET: 获取单条体征日志详情
    PUT: 更新体征日志
    DELETE: 删除体征日志
    """
    from .models import VitalEntry

    try:
        log = VitalEntry.objects.get(id=log_id, user=request.user)
    except VitalEntry.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': '体征日志不存在或无权访问'
        }, status=404)

    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'log': {
                'id': log.id,
                'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                'vital_type': log.vital_type,
                'vital_type_display': log.get_vital_type_display(),
                'value': log.value,
                'unit': log.unit or '',
                'notes': log.notes or '',
                'related_checkup_id': log.related_checkup_id,
                'related_medication_id': log.related_medication_id,
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': log.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })

    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)

            if data.get('entry_date'):
                from datetime import datetime
                log.entry_date = datetime.strptime(data['entry_date'], '%Y-%m-%d').date()
            if data.get('vital_type'):
                log.vital_type = data['vital_type']
            if data.get('value'):
                log.value = data['value']
            if data.get('unit') is not None:
                log.unit = data['unit'].strip()
            if data.get('notes') is not None:
                log.notes = data['notes'].strip()
            if data.get('related_checkup_id') is not None:
                log.related_checkup_id = data['related_checkup_id']
            if data.get('related_medication_id') is not None:
                log.related_medication_id = data['related_medication_id']

            log.save()

            return JsonResponse({
                'success': True,
                'message': '体征日志已更新',
                'log': {
                    'id': log.id,
                    'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                    'vital_type': log.vital_type,
                    'vital_type_display': log.get_vital_type_display(),
                    'value': log.value,
                    'unit': log.unit or '',
                    'notes': log.notes or '',
                }
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'更新体征日志失败: {str(e)}'
            }, status=500)

    elif request.method == 'DELETE':
        vital_display = log.get_vital_type_display()
        log.delete()

        return JsonResponse({
            'success': True,
            'message': f'体征日志"{vital_display}"已删除'
        })


@csrf_exempt
@require_http_methods(["GET"])
@login_required
def api_vital_types(request):
    """
    获取所有体征类型选项（用于前端下拉框）
    """
    from .models import VitalEntry

    vital_types = []
    for value, label in VitalEntry.VITAL_TYPE_CHOICES:
        vital_types.append({
            'value': value,
            'label': label
        })

    return JsonResponse({
        'success': True,
        'vital_types': vital_types
    })


# ============================================================================
# 健康管理计划 API (CarePlan, CareGoal, CareAction)
# ============================================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_care_plans(request):
    """
    GET: 获取用户的所有健康管理计划
    POST: 创建新的健康管理计划
    """
    if request.method == 'GET':
        plans = CarePlan.objects.filter(user=request.user).order_by('-updated_at')
        plans_list = []
        
        for plan in plans:
            plans_list.append({
                'id': plan.id,
                'title': plan.title,
                'description': plan.description or '',
                'is_active': plan.is_active,
                'goals_count': plan.goals.count(),
                'created_at': plan.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': plan.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        
        return JsonResponse({
            'success': True,
            'plans': plans_list
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            plan = CarePlan.objects.create(
                user=request.user,
                title=data.get('title', '').strip(),
                description=data.get('description', '').strip(),
                is_active=data.get('is_active', True)
            )
            
            return JsonResponse({
                'success': True,
                'message': '健康管理计划已创建',
                'plan': {
                    'id': plan.id,
                    'title': plan.title,
                    'description': plan.description,
                    'is_active': plan.is_active,
                    'created_at': plan.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                }
            }, status=201)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'创建计划失败: {str(e)}'
            }, status=400)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_care_plan_detail(request, plan_id):
    """
    GET: 获取计划详情（包含所有目标和行动）
    PUT: 更新计划
    DELETE: 删除计划
    """
    try:
        plan = get_object_or_404(CarePlan, id=plan_id, user=request.user)
    except:
        return JsonResponse({
            'success': False,
            'error': '计划不存在或无权访问'
        }, status=404)
    
    if request.method == 'GET':
        # 获取所有目标及其行动
        goals_data = []
        for goal in plan.goals.all():
            actions_data = []
            for action in goal.actions.all():
                actions_data.append({
                    'id': action.id,
                    'title': action.title,
                    'frequency': action.frequency or '',
                    'status': action.status,
                    'status_display': action.get_status_display(),
                })
            
            goals_data.append({
                'id': goal.id,
                'title': goal.title,
                'target_value': goal.target_value or '',
                'unit': goal.unit or '',
                'due_date': goal.due_date.strftime('%Y-%m-%d') if goal.due_date else None,
                'status': goal.status,
                'status_display': goal.get_status_display(),
                'progress_percent': goal.progress_percent,
                'actions_count': len(actions_data),
                'actions': actions_data,
            })
        
        return JsonResponse({
            'success': True,
            'plan': {
                'id': plan.id,
                'title': plan.title,
                'description': plan.description or '',
                'is_active': plan.is_active,
                'goals_count': len(goals_data),
                'goals': goals_data,
                'created_at': plan.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': plan.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            
            if data.get('title'):
                plan.title = data['title'].strip()
            if data.get('description') is not None:
                plan.description = data['description'].strip()
            if data.get('is_active') is not None:
                plan.is_active = data['is_active']
            
            plan.save()
            
            return JsonResponse({
                'success': True,
                'message': '计划已更新',
                'plan': {
                    'id': plan.id,
                    'title': plan.title,
                    'description': plan.description,
                    'is_active': plan.is_active,
                    'updated_at': plan.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                }
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'更新计划失败: {str(e)}'
            }, status=400)
    
    elif request.method == 'DELETE':
        plan.delete()
        return JsonResponse({
            'success': True,
            'message': '计划已删除'
        })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_care_goals(request, plan_id):
    """
    GET: 获取计划的所有目标
    POST: 为计划创建新目标
    """
    plan = get_object_or_404(CarePlan, id=plan_id, user=request.user)
    
    if request.method == 'GET':
        goals = plan.goals.all()
        goals_list = []
        
        for goal in goals:
            goals_list.append({
                'id': goal.id,
                'title': goal.title,
                'target_value': goal.target_value or '',
                'unit': goal.unit or '',
                'due_date': goal.due_date.strftime('%Y-%m-%d') if goal.due_date else None,
                'status': goal.status,
                'status_display': goal.get_status_display(),
                'progress_percent': goal.progress_percent,
                'actions_count': goal.actions.count(),
            })
        
        return JsonResponse({
            'success': True,
            'goals': goals_list
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            from datetime import datetime
            goal = CareGoal.objects.create(
                plan=plan,
                title=data.get('title', '').strip(),
                target_value=data.get('target_value', '').strip(),
                unit=data.get('unit', '').strip(),
                due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
                status=data.get('status', 'active'),
            )
            
            return JsonResponse({
                'success': True,
                'message': '目标已创建',
                'goal': {
                    'id': goal.id,
                    'title': goal.title,
                    'target_value': goal.target_value,
                    'unit': goal.unit,
                    'due_date': goal.due_date.strftime('%Y-%m-%d') if goal.due_date else None,
                    'status': goal.status,
                    'created_at': goal.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                }
            }, status=201)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'创建目标失败: {str(e)}'
            }, status=400)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_care_goal_detail(request, goal_id):
    """
    GET: 获取目标详情（包含所有行动）
    PUT: 更新目标
    DELETE: 删除目标
    """
    try:
        goal = get_object_or_404(CareGoal, id=goal_id, plan__user=request.user)
    except:
        return JsonResponse({
            'success': False,
            'error': '目标不存在或无权访问'
        }, status=404)
    
    if request.method == 'GET':
        actions_data = []
        for action in goal.actions.all():
            actions_data.append({
                'id': action.id,
                'title': action.title,
                'frequency': action.frequency or '',
                'status': action.status,
                'status_display': action.get_status_display(),
            })
        
        return JsonResponse({
            'success': True,
            'goal': {
                'id': goal.id,
                'plan_id': goal.plan.id,
                'title': goal.title,
                'target_value': goal.target_value or '',
                'unit': goal.unit or '',
                'due_date': goal.due_date.strftime('%Y-%m-%d') if goal.due_date else None,
                'status': goal.status,
                'status_display': goal.get_status_display(),
                'progress_percent': goal.progress_percent,
                'actions': actions_data,
                'created_at': goal.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': goal.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            
            if data.get('title'):
                goal.title = data['title'].strip()
            if data.get('target_value') is not None:
                goal.target_value = data['target_value'].strip()
            if data.get('unit') is not None:
                goal.unit = data['unit'].strip()
            if data.get('due_date'):
                from datetime import datetime
                goal.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date()
            if data.get('status'):
                goal.status = data['status']
            
            goal.save()
            
            return JsonResponse({
                'success': True,
                'message': '目标已更新',
                'goal': {
                    'id': goal.id,
                    'title': goal.title,
                    'target_value': goal.target_value,
                    'status': goal.status,
                    'updated_at': goal.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                }
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'更新目标失败: {str(e)}'
            }, status=400)
    
    elif request.method == 'DELETE':
        goal.delete()
        return JsonResponse({
            'success': True,
            'message': '目标已删除'
        })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_care_actions(request, goal_id):
    """
    GET: 获取目标的所有行动
    POST: 为目标创建新行动
    """
    goal = get_object_or_404(CareGoal, id=goal_id, plan__user=request.user)
    
    if request.method == 'GET':
        actions = goal.actions.all()
        actions_list = []
        
        for action in actions:
            actions_list.append({
                'id': action.id,
                'title': action.title,
                'frequency': action.frequency or '',
                'status': action.status,
                'status_display': action.get_status_display(),
                'created_at': action.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })
        
        return JsonResponse({
            'success': True,
            'actions': actions_list
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            action = CareAction.objects.create(
                goal=goal,
                title=data.get('title', '').strip(),
                frequency=data.get('frequency', '').strip(),
                status=data.get('status', 'pending'),
            )
            
            # 重新计算目标进度
            goal.recalculate_progress()
            
            return JsonResponse({
                'success': True,
                'message': '行动已创建',
                'action': {
                    'id': action.id,
                    'title': action.title,
                    'frequency': action.frequency,
                    'status': action.status,
                    'created_at': action.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                }
            }, status=201)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'创建行动失败: {str(e)}'
            }, status=400)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_care_action_detail(request, action_id):
    """
    GET: 获取行动详情
    PUT: 更新行动（标记完成）
    DELETE: 删除行动
    """
    try:
        action = get_object_or_404(CareAction, id=action_id, goal__plan__user=request.user)
    except:
        return JsonResponse({
            'success': False,
            'error': '行动不存在或无权访问'
        }, status=404)
    
    goal = action.goal
    
    if request.method == 'GET':
        return JsonResponse({
            'success': True,
            'action': {
                'id': action.id,
                'goal_id': goal.id,
                'title': action.title,
                'frequency': action.frequency or '',
                'status': action.status,
                'status_display': action.get_status_display(),
                'created_at': action.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })
    
    elif request.method == 'PUT':
        try:
            data = json.loads(request.body)
            
            if data.get('title'):
                action.title = data['title'].strip()
            if data.get('frequency') is not None:
                action.frequency = data['frequency'].strip()
            if data.get('status'):
                action.status = data['status']
            
            action.save()
            
            # 重新计算目标进度
            goal.recalculate_progress()
            
            return JsonResponse({
                'success': True,
                'message': '行动已更新',
                'action': {
                    'id': action.id,
                    'title': action.title,
                    'frequency': action.frequency,
                    'status': action.status,
                }
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'success': False,
                'error': f'更新行动失败: {str(e)}'
            }, status=400)
    
    elif request.method == 'DELETE':
        action.delete()
        # 重新计算目标进度
        goal.recalculate_progress()
        
        return JsonResponse({
            'success': True,
            'message': '行动已删除'
        })
