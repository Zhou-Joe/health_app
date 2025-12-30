import json
import os
import tempfile
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from .models import HealthCheckup, DocumentProcessing, HealthIndicator, Conversation, HealthAdvice, SystemSettings
from .forms import HealthCheckupForm
from .services import DocumentProcessingService
from .utils import convert_image_to_pdf, is_image_file


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

        # 从系统设置获取默认工作流
        from .models import SystemSettings
        default_workflow = SystemSettings.get_default_workflow()
        workflow_type = request.POST.get('workflow_type', default_workflow)

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

        # 创建文档处理记录
        document_processing = DocumentProcessing.objects.create(
            user=request.user,
            health_checkup=health_checkup,
            workflow_type=workflow_type,
            status='pending',
            progress=0
        )

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

        # 获取默认工作流
        from .models import SystemSettings
        default_workflow = SystemSettings.get_default_workflow()

        response_data = {
            'ocr_status': 'online' if ocr_status else 'offline',
            'llm_status': 'online' if llm_status else 'offline',
            'vl_model_status': 'online' if vl_status else 'offline',
            'default_workflow': default_workflow,
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
            indicator_count=Count('healthindicator')
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

        # 构建Prompt，强制JSON格式输出
        prompt = f"""分析{len(indicators_by_name)}组健康指标，只处理需要更正的指标：

【首要任务：对齐命名】
命名统一是最重要的任务！必须仔细检查相同指标是否有不同名称，将所有变体名称对齐到其中一个已有名称，不要创造新名称。
示例：
- "身高"和"身长"同时存在 → 统一为"身高"（选其中一个已有的）
- "血红蛋白"和"HGB"同时存在 → 统一为"血红蛋白"（选其中一个已有的）
- "空腹血糖"和"血糖"同时存在 → 统一为其中任意一个

【其他需要更正的情况】
1.单位缺失或不统一（如"kg"和"公斤"）→统一标准单位
2.状态错误：必须仔细检查！特别注意描述性的指标值
   - 如果value是描述性文字（如"未见异常"、"正常"、"阳性"等）→ status应设为对应状态
   - 如果value明显超出参考范围 → status应为"abnormal"或"attention"
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
每个变更都必须包含"reason"字段，用简洁的中文说明修改的理由（1-2句话）。

数据：
{json.dumps(indicators_summary, ensure_ascii=False, indent=2)}

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
            "indicator_id": 789,
            "status": "normal",
            "reason": "数值120在参考范围90-120内，状态应修正为正常"
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
4.reason字段必须用简洁的中文说明修改理由
5.绝对不要返回reference_range字段
6.纯JSON格式，无markdown"""

        # 如果用户提供了自定义提示词，添加到prompt中
        if user_prompt:
            prompt += f"""

【用户特别要求】
{user_prompt}

请严格按照上述用户要求进行数据整合。"""

        logger.info(f"[数据整合] Prompt构建完成，长度: {len(prompt)} 字符")
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
                llm_response = call_gemini_api(prompt, timeout=timeout)
            else:
                # 使用 OpenAI 兼容格式
                logger.info(f"[数据整合] 使用 OpenAI 兼容格式")
                # 使用统一的AI模型超时配置
                timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
                llm_response = call_llm_for_integration(prompt, timeout=timeout)

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

            # 尝试从响应中提取JSON
            # 移除可能的markdown标记
            cleaned_response = llm_response.strip()
            if cleaned_response.startswith('```'):
                logger.info(f"[数据整合] 检测到markdown标记，正在清理...")
                # 移除markdown代码块标记
                cleaned_response = re.sub(r'^```\w*\n?', '', cleaned_response)
                cleaned_response = re.sub(r'\n?```$', '', cleaned_response)
                logger.info(f"[数据整合] Markdown清理完成")

            # 尝试提取JSON对象
            json_match = re.search(r'\{[\s\S]*\}', cleaned_response)
            if json_match:
                result_json = json.loads(json_match.group())
                logger.info(f"[数据整合] ✓ JSON提取成功（使用正则匹配）")
            else:
                result_json = json.loads(cleaned_response)
                logger.info(f"[数据整合] ✓ JSON解析成功（直接解析）")

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
    """应用数据整合结果到数据库"""
    try:
        from django.db import transaction
        import time

        print(f"\n{'='*80}")
        print(f"[应用更新] 开始")
        print(f"[应用更新] 用户: {request.user.username}")

        # 获取请求数据
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

        # 使用事务确保数据一致性
        with transaction.atomic():
            print(f"[应用更新] 开始事务处理...")
            start_time = time.time()

            for idx, change in enumerate(changes, 1):
                indicator_id = change.get('indicator_id')
                change_data = change.get('changes', {})

                print(f"[应用更新] {idx}/{len(changes)} 处理指标 {indicator_id}...")

                # 验证所有权
                try:
                    indicator = HealthIndicator.objects.get(
                        id=indicator_id,
                        checkup__user=request.user
                    )
                except HealthIndicator.DoesNotExist:
                    print(f"[应用更新]   ✗ 跳过（指标不存在）")
                    skipped_count += 1
                    continue

                # 记录更新前的状态
                before_state = {
                    'indicator_name': indicator.indicator_name,
                    'value': indicator.value,
                    'unit': indicator.unit,
                    'reference_range': indicator.reference_range,
                    'status': indicator.status,
                    'indicator_type': indicator.indicator_type
                }

                print(f"[应用更新]   原始: {indicator.indicator_name} = {indicator.value} {indicator.unit or ''}")

                # 应用更改
                if change_data.get('indicator_name'):
                    print(f"[应用更新]   -> 名称: {indicator.indicator_name} -> {change_data['indicator_name']}")
                    indicator.indicator_name = change_data['indicator_name']

                if change_data.get('value'):
                    print(f"[应用更新]   -> 值: {indicator.value} -> {change_data['value']}")
                    indicator.value = change_data['value']

                if change_data.get('unit') is not None:  # 允许空字符串
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

                # 记录更新详情（用于展示对比）
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

        end_time = time.time()
        duration = end_time - start_time

        print(f"[应用更新] ✓ 所有更新完成")
        print(f"[应用更新] 成功更新: {updated_count} 个，跳过: {skipped_count} 个")
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