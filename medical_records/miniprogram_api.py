from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.core.files.storage import default_storage
import json
import uuid
import os
from datetime import datetime, timedelta

from .models import HealthCheckup, HealthIndicator, HealthAdvice, SystemSettings, DocumentProcessing
from .services import DocumentProcessingService, VisionLanguageModelService, AIService
from .miniprogram_serializers import (
    UserSerializer, HealthCheckupSerializer, HealthIndicatorSerializer,
    HealthAdviceSerializer, DocumentProcessingSerializer,
    MiniProgramCheckupListSerializer
)

@api_view(['POST'])
@permission_classes([])  # Disable CSRF for login
def miniprogram_login(request):
    """小程序登录API - 支持微信登录"""
    try:
        data = json.loads(request.body)

        # 支持两种登录方式：
        # 1. 微信小程序登录（需要微信code）
        # 2. 用户名密码登录（测试用）

        if 'code' in data:
            # 微信小程序登录（这里需要实际的微信API集成）
            # 目前先创建或获取用户
            openid = data.get('openid', f"wx_{uuid.uuid4().hex[:16]}")
            nickname = data.get('nickname', '微信用户')

            user, created = User.objects.get_or_create(
                username=openid,
                defaults={
                    'first_name': nickname,
                    'email': f"{openid}@wechat.com",
                    'is_active': True
                }
            )

            if created:
                # 为新用户创建默认设置
                pass

            login(request, user)

            return Response({
                'success': True,
                'message': '登录成功',
                'user': UserSerializer(user).data,
                'token': get_or_create_token(user)
            })

        elif 'username' in data and 'password' in data:
            # 用户名密码登录
            username = data['username']
            password = data['password']

            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return Response({
                    'success': True,
                    'message': '登录成功',
                    'user': UserSerializer(user).data,
                    'token': get_or_create_token(user)
                })
            else:
                return Response({
                    'success': False,
                    'message': '用户名或密码错误'
                }, status=status.HTTP_401_UNAUTHORIZED)
        else:
            return Response({
                'success': False,
                'message': '请提供登录信息'
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'登录失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def get_or_create_token(user):
    """创建或获取用户token"""
    # 这里可以使用JWT或其他token方案
    # 目前返回简单的用户信息作为token
    return str(user.id)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_user_info(request):
    """获取用户信息"""
    serializer = UserSerializer(request.user)
    return Response({
        'success': True,
        'user': serializer.data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_upload_report(request):
    """小程序上传体检报告"""
    try:
        if 'file' not in request.FILES:
            return Response({
                'success': False,
                'message': '请上传文件'
            }, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES['file']
        checkup_date = request.POST.get('checkup_date', datetime.now().strftime('%Y-%m-%d'))
        hospital = request.POST.get('hospital', '')
        department = request.POST.get('department', '')
        workflow_type = request.POST.get('workflow_type', 'vl_model')  # 默认使用多模态模型

        # 保存文件
        file_name = f"miniprogram_{uuid.uuid4().hex[:8]}_{file.name}"
        file_path = default_storage.save(f'reports/miniprogram/{file_name}', file)

        # 创建体检记录
        health_checkup = HealthCheckup.objects.create(
            user=request.user,
            checkup_date=checkup_date,
            hospital=hospital,
            department=department,
            report_file=file_path,
            status='pending'
        )

        # 创建文档处理记录
        document_processing = DocumentProcessing.objects.create(
            health_checkup=health_checkup,
            workflow_type=workflow_type,
            status='pending',
            progress=0
        )

        # 启动后台处理
        import threading
        processing_thread = threading.Thread(
            target=process_document_background,
            args=(document_processing.id, file_path),
            name=f"MiniProgram-DocumentProcessing-{document_processing.id}"
        )
        processing_thread.daemon = False
        processing_thread.start()

        return Response({
            'success': True,
            'message': '上传成功，正在处理...',
            'processing_id': document_processing.id,
            'checkup_id': health_checkup.id
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'上传失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_processing_status(request, processing_id):
    """获取处理状态"""
    try:
        document_processing = DocumentProcessing.objects.get(
            id=processing_id,
            health_checkup__user=request.user
        )

        # 构建响应数据
        response_data = {
            'success': True,
            'status': document_processing.status,
            'progress': document_processing.progress,
            'error_message': document_processing.error_message,
            'workflow_type': document_processing.workflow_type,
            'created_at': document_processing.created_at.isoformat(),
            'updated_at': document_processing.updated_at.isoformat()
        }

        # 添加指标数量
        indicators_count = HealthIndicator.objects.filter(
            checkup=document_processing.health_checkup
        ).count()
        response_data['indicators_count'] = indicators_count

        # 添加OCR结果
        if document_processing.ocr_result:
            response_data['ocr_result'] = document_processing.ocr_result
            response_data['has_ocr_result'] = True
        else:
            response_data['ocr_result'] = None
            response_data['has_ocr_result'] = False

        # 添加AI结果
        if document_processing.ai_result:
            response_data['ai_result'] = document_processing.ai_result
            response_data['has_ai_result'] = True
            response_data['ai_indicators_count'] = len(document_processing.ai_result.get('indicators', []))
        else:
            response_data['ai_result'] = None
            response_data['has_ai_result'] = False
            response_data['ai_indicators_count'] = 0

        # 添加多模态模型结果
        if document_processing.vl_model_result:
            response_data['vl_model_result'] = document_processing.vl_model_result
            response_data['has_vl_model_result'] = True
            if isinstance(document_processing.vl_model_result, dict) and 'indicators' in document_processing.vl_model_result:
                response_data['vl_indicators_count'] = len(document_processing.vl_model_result['indicators'])
            else:
                response_data['vl_indicators_count'] = 0
        else:
            response_data['vl_model_result'] = None
            response_data['has_vl_model_result'] = False
            response_data['vl_indicators_count'] = 0

        return Response(response_data)

    except DocumentProcessing.DoesNotExist:
        return Response({
            'success': False,
            'message': '处理记录不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取状态失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_checkup_list(request):
    """获取体检记录列表"""
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))

        checkups = HealthCheckup.objects.filter(
            user=request.user
        ).order_by('-created_at')

        # 分页
        start = (page - 1) * page_size
        end = start + page_size
        checkups_page = checkups[start:end]

        serializer = MiniProgramCheckupListSerializer(checkups_page, many=True)

        return Response({
            'success': True,
            'data': serializer.data,
            'total': checkups.count(),
            'page': page,
            'page_size': page_size,
            'has_more': end < checkups.count()
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取记录失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_checkup_detail(request, checkup_id):
    """获取体检记录详情"""
    try:
        checkup = HealthCheckup.objects.get(
            id=checkup_id,
            user=request.user
        )

        serializer = HealthCheckupSerializer(checkup)

        return Response({
            'success': True,
            'data': serializer.data
        })

    except HealthCheckup.DoesNotExist:
        return Response({
            'success': False,
            'message': '体检记录不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取详情失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_indicators(request, checkup_id=None):
    """获取健康指标列表"""
    try:
        # 从查询参数获取checkup_id（如果URL路径参数没有提供的话）
        query_checkup_id = request.GET.get('checkup_id', None)

        if query_checkup_id:
            checkup_id = int(query_checkup_id)

        if checkup_id:
            # 获取特定体检记录的指标
            checkup = HealthCheckup.objects.get(
                id=checkup_id,
                user=request.user
            )
            indicators = HealthIndicator.objects.filter(
                checkup=checkup
            ).order_by('-id')
        else:
            # 获取用户所有指标
            indicators = HealthIndicator.objects.filter(
                checkup__user=request.user
            ).order_by('-id')

        # 分页
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))

        start = (page - 1) * page_size
        end = start + page_size
        indicators_page = indicators[start:end]

        serializer = HealthIndicatorSerializer(indicators_page, many=True)

        return Response({
            'success': True,
            'data': serializer.data,
            'total': indicators.count(),
            'page': page,
            'page_size': page_size,
            'has_more': end < indicators.count()
        })

    except HealthCheckup.DoesNotExist:
        return Response({
            'success': False,
            'message': '体检记录不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取指标失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_get_advice(request):
    """获取AI健康建议"""
    try:
        data = json.loads(request.body)
        checkup_id = data.get('checkup_id')

        if not checkup_id:
            return Response({
                'success': False,
                'message': '请提供体检记录ID'
            }, status=status.HTTP_400_BAD_REQUEST)

        checkup = HealthCheckup.objects.get(
            id=checkup_id,
            user=request.user
        )

        # 获取健康指标
        indicators = HealthIndicator.objects.filter(checkup=checkup)

        # 生成AI建议
        ai_service = AIService()
        advice = ai_service.get_health_advice(indicators)

        # 保存建议
        health_advice = HealthAdvice.objects.create(
            user=request.user,
            checkup=checkup,
            advice_type='ai_analysis',
            advice_content=advice
        )

        serializer = HealthAdviceSerializer(health_advice)

        return Response({
            'success': True,
            'message': 'AI建议生成成功',
            'data': serializer.data
        })

    except HealthCheckup.DoesNotExist:
        return Response({
            'success': False,
            'message': '体检记录不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取建议失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([])  # No authentication required for services status
def miniprogram_services_status(request):
    """获取系统服务状态"""
    try:
        services = {
            'mineru': {
                'status': 'unknown',
                'api_url': SystemSettings.get_setting('mineru_api_url', ''),
                'last_check': None
            },
            'llm': {
                'status': 'unknown',
                'api_url': SystemSettings.get_setting('llm_api_url', ''),
                'last_check': None
            },
            'ai_doctor': {
                'status': 'unknown',
                'api_url': SystemSettings.get_setting('ai_doctor_api_url', ''),
                'last_check': None
            },
            'vl_model': {
                'status': 'unknown',
                'api_url': SystemSettings.get_setting('vl_model_api_url', ''),
                'last_check': None
            }
        }

        # 检查各个服务状态（这里简化处理）
        services_status = []

        for service_name, service_info in services.items():
            # 实际实现中应该调用相应的健康检查API
            status = 'healthy' if service_info['api_url'] else 'disabled'
            services_status.append({
                'name': service_name,
                'status': status,
                'api_url': service_info['api_url']
            })

        return Response({
            'success': True,
            'services': services_status,
            'default_workflow': SystemSettings.get_default_workflow()
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取服务状态失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([])  # No authentication required for system settings
def miniprogram_system_settings(request):
    """获取系统设置"""
    try:
        # 获取主要系统设置
        settings = {
            'mineru_api_url': SystemSettings.get_setting('mineru_api_url', ''),
            'llm_api_url': SystemSettings.get_setting('llm_api_url', ''),
            'llm_model_name': SystemSettings.get_setting('llm_model_name', 'qwen3-4b-instruct'),
            'vl_model_api_url': SystemSettings.get_setting('vl_model_api_url', ''),
            'vl_model_name': SystemSettings.get_setting('vl_model_name', 'gpt-4-vision-preview'),
            'default_workflow': SystemSettings.get_default_workflow(),
            'ocr_timeout': SystemSettings.get_setting('ocr_timeout', '300'),
            'llm_timeout': SystemSettings.get_setting('llm_timeout', '600'),
            'vl_model_timeout': SystemSettings.get_setting('vl_model_timeout', '300'),
            'vl_model_max_tokens': SystemSettings.get_setting('vl_model_max_tokens', '4000'),
        }

        return Response({
            'success': True,
            'settings': settings
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取设置失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 删除体检报告 ====================
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def miniprogram_delete_checkup(request, checkup_id):
    """删除体检报告"""
    try:
        checkup = HealthCheckup.objects.get(
            id=checkup_id,
            user=request.user
        )

        checkup.delete()

        return Response({
            'success': True,
            'message': '体检报告已删除'
        })

    except HealthCheckup.DoesNotExist:
        return Response({
            'success': False,
            'message': '体检报告不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'删除失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 创建健康指标 ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_create_indicator(request):
    """手动创建健康指标"""
    try:
        data = json.loads(request.body)

        # 获取体检报告
        checkup_id = data.get('checkup_id')
        if not checkup_id:
            return Response({
                'success': False,
                'message': '请提供体检报告ID'
            }, status=status.HTTP_400_BAD_REQUEST)

        checkup = HealthCheckup.objects.get(
            id=checkup_id,
            user=request.user
        )

        # 创建指标
        indicator = HealthIndicator.objects.create(
            checkup=checkup,
            indicator_type=data.get('indicator_type', 'other_exam'),
            indicator_name=data.get('indicator_name'),
            value=data.get('value'),
            unit=data.get('unit', ''),
            reference_range=data.get('reference_range', ''),
            status=data.get('status', 'normal')
        )

        serializer = HealthIndicatorSerializer(indicator)

        return Response({
            'success': True,
            'message': '指标添加成功',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)

    except HealthCheckup.DoesNotExist:
        return Response({
            'success': False,
            'message': '体检报告不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'创建失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 更新健康指标 ====================
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def miniprogram_update_indicator(request, indicator_id):
    """更新健康指标"""
    try:
        indicator = HealthIndicator.objects.get(
            id=indicator_id,
            checkup__user=request.user
        )

        data = json.loads(request.body)

        # 更新字段
        if 'indicator_name' in data:
            indicator.indicator_name = data['indicator_name']
        if 'value' in data:
            indicator.value = data['value']
        if 'unit' in data:
            indicator.unit = data['unit']
        if 'reference_range' in data:
            indicator.reference_range = data['reference_range']
        if 'status' in data:
            indicator.status = data['status']
        if 'indicator_type' in data:
            indicator.indicator_type = data['indicator_type']

        indicator.save()

        serializer = HealthIndicatorSerializer(indicator)

        return Response({
            'success': True,
            'message': '指标更新成功',
            'data': serializer.data
        })

    except HealthIndicator.DoesNotExist:
        return Response({
            'success': False,
            'message': '指标不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'更新失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 删除健康指标 ====================
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def miniprogram_delete_indicator(request, indicator_id):
    """删除健康指标"""
    try:
        indicator = HealthIndicator.objects.get(
            id=indicator_id,
            checkup__user=request.user
        )

        indicator.delete()

        return Response({
            'success': True,
            'message': '指标已删除'
        })

    except HealthIndicator.DoesNotExist:
        return Response({
            'success': False,
            'message': '指标不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'删除失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== AI对话列表 ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_conversations(request):
    """获取用户的对话列表"""
    try:
        from .models import Conversation

        conversations = Conversation.get_user_conversations(request.user, limit=20)

        conversation_list = []
        for conv in conversations:
            latest_message = conv.get_latest_message()
            message_count = conv.get_message_count()

            if message_count > 0:
                conversation_list.append({
                    'id': conv.id,
                    'title': conv.title,
                    'created_at': conv.created_at.isoformat(),
                    'updated_at': conv.updated_at.isoformat(),
                    'message_count': message_count,
                    'latest_question': latest_message.question[:100] if latest_message else ''
                })

        return Response({
            'success': True,
            'data': conversation_list,
            'total': len(conversation_list)
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取对话列表失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 创建对话 ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_create_conversation(request):
    """创建新的AI对话"""
    try:
        from .models import Conversation

        data = json.loads(request.body)
        title = data.get('title', f"对话 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        conversation = Conversation.create_new_conversation(request.user, title)

        return Response({
            'success': True,
            'message': '对话创建成功',
            'data': {
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at.isoformat()
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'创建对话失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 对话详情 ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_conversation_detail(request, conversation_id):
    """获取对话详情和所有消息"""
    try:
        from .models import Conversation, HealthAdvice

        conversation = Conversation.objects.get(
            id=conversation_id,
            user=request.user
        )

        # 获取对话中的所有消息
        messages = HealthAdvice.get_conversation_messages(conversation_id)

        message_list = []
        for msg in messages:
            message_list.append({
                'id': msg.id,
                'question': msg.question,
                'answer': msg.answer,
                'created_at': msg.created_at.isoformat()
            })

        return Response({
            'success': True,
            'data': {
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at.isoformat(),
                'updated_at': conversation.updated_at.isoformat(),
                'messages': message_list,
                'message_count': len(message_list)
            }
        })

    except Conversation.DoesNotExist:
        return Response({
            'success': False,
            'message': '对话不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取对话详情失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 删除对话 ====================
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def miniprogram_delete_conversation(request, conversation_id):
    """删除对话"""
    try:
        from .models import Conversation

        conversation = Conversation.objects.get(
            id=conversation_id,
            user=request.user
        )

        conversation.delete()

        return Response({
            'success': True,
            'message': '对话已删除'
        })

    except Conversation.DoesNotExist:
        return Response({
            'success': False,
            'message': '对话不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'删除失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 数据整合 ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_integrate_data(request):
    """AI智能整合多份体检报告的数据"""
    try:
        from .api_views import integrate_data

        # 复用现有的数据整合逻辑
        result = integrate_data(request)

        return result

    except Exception as e:
        return Response({
            'success': False,
            'message': f'数据整合失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 常用医院列表 ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_common_hospitals(request):
    """获取用户常用体检机构列表"""
    try:
        from django.db.models import Q, Count, Max

        user_hospitals = HealthCheckup.objects.filter(
            user=request.user
        ).exclude(
            Q(hospital__isnull=True) | Q(hospital='')
        ).exclude(
            hospital='未知机构'
        ).values('hospital').annotate(
            usage_count=Count('id'),
            last_used=Max('checkup_date')
        ).order_by('-usage_count', 'hospital')[:10]

        hospitals_data = []
        for item in user_hospitals:
            hospitals_data.append({
                'name': item['hospital'],
                'usage_count': item['usage_count'],
                'last_used': item['last_used'].strftime('%Y-%m-%d') if item['last_used'] else None
            })

        return Response({
            'success': True,
            'data': hospitals_data,
            'total': len(hospitals_data)
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取医院列表失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 后台处理函数（复用现有的）====================
def process_document_background(document_processing_id, file_path):
    """后台处理文档（复用现有逻辑）"""
    try:
        document_processing = DocumentProcessing.objects.get(id=document_processing_id)
        service = DocumentProcessingService(document_processing)
        result = service.process_document(file_path)
        print(f"[MiniProgram-{document_processing_id}] 处理完成，结果: {result}")
    except Exception as e:
        print(f"[MiniProgram-{document_processing_id}] 处理失败: {str(e)}")
        # 更新错误状态
        document_processing = DocumentProcessing.objects.get(id=document_processing_id)
        document_processing.status = 'failed'
        document_processing.error_message = str(e)
        document_processing.save()