from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authtoken.models import Token
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

from .models import HealthCheckup, HealthIndicator, HealthAdvice, SystemSettings, DocumentProcessing, Conversation
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
            # 微信小程序登录
            code = data['code']
            nickname = data.get('nickname', '微信用户')
            avatar_url = data.get('avatarUrl', '')

            # 调用微信API获取openid
            from .wechat_config import WECHAT_APPID, WECHAT_APP_SECRET, WECHAT_CODE2SESSION_URL

            if not WECHAT_APPID or not WECHAT_APP_SECRET:
                # 如果未配置AppID和AppSecret，使用开发模式（使用code作为临时openid）
                import warnings
                warnings.warn("微信小程序AppID或AppSecret未配置，使用开发模式（每次登录创建新用户）")
                openid = f"dev_wx_{code[:16]}"
            else:
                # 调用微信code2Session API获取openid
                import requests
                params = {
                    'appid': WECHAT_APPID,
                    'secret': WECHAT_APP_SECRET,
                    'js_code': code,
                    'grant_type': 'authorization_code'
                }

                print(f"[微信登录] 调用code2Session API，code: {code[:10]}...")
                response = requests.get(WECHAT_CODE2SESSION_URL, params=params, timeout=5)
                result = response.json()

                if 'errcode' in result:
                    print(f"[微信登录] API错误: {result}")
                    return Response({
                        'success': False,
                        'message': f'微信登录失败: {result.get("errmsg", "未知错误")}'
                    }, status=status.HTTP_400_BAD_REQUEST)

                openid = result.get('openid')
                session_key = result.get('session_key')

                if not openid:
                    return Response({
                        'success': False,
                        'message': '无法获取用户openid'
                    }, status=status.HTTP_400_BAD_REQUEST)

                print(f"[微信登录] 获取openid成功: {openid[:10]}...")

            # 查找或创建用户
            user, created = User.objects.get_or_create(
                username=openid,
                defaults={
                    'first_name': nickname,
                    'email': '',
                    'is_active': True
                }
            )

            if created:
                print(f"[微信登录] 创建新用户: {openid[:10]}...")
            else:
                print(f"[微信登录] 用户已存在: {openid[:10]}...")

            # 检查是否有UserProfile
            from .models import UserProfile
            user_profile, profile_created = UserProfile.objects.get_or_create(user=user)

            # 判断是否首次登录（没有设置个人信息）
            is_first_login = not (user_profile.birth_date or user_profile.gender)

            login(request, user)

            return Response({
                'success': True,
                'message': '登录成功',
                'user': UserSerializer(user).data,
                'token': get_or_create_token(user),
                'is_first_login': is_first_login,
                'need_complete_profile': is_first_login
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
    token, created = Token.objects.get_or_create(user=user)
    return token.key

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
        notes = request.POST.get('notes', '')
        workflow_type = request.POST.get('workflow_type', 'vl_model')  # 图片默认使用多模态模型

        # 保存文件
        file_name = f"miniprogram_{uuid.uuid4().hex[:8]}_{file.name}"
        file_path = default_storage.save(f'reports/miniprogram/{file_name}', file)

        # 获取文件的完整路径供后台处理使用
        from django.conf import settings
        if default_storage.exists(file_path):
            full_file_path = default_storage.path(file_path)
        else:
            # 如果是云存储，使用URL或临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as tmp:
                for chunk in file.chunks():
                    tmp.write(chunk)
                full_file_path = tmp.name

        # 创建体检记录（如果已存在相同日期和机构的报告，则合并）
        from django.db.models import Q

        # 检查是否存在相同日期和机构的报告
        existing_checkup = HealthCheckup.objects.filter(
            user=request.user,
            checkup_date=checkup_date,
            hospital=hospital
        ).first()

        if existing_checkup:
            # 存在相同报告，合并到现有报告中
            health_checkup = existing_checkup

            # 如果新上传的文件不为空，更新文件（保留原文件或追加）
            if file and not health_checkup.report_file:
                health_checkup.report_file = file_path
                health_checkup.save()

            # 如果有新的备注，追加到原备注
            if notes and notes.strip():
                if health_checkup.notes:
                    health_checkup.notes = f"{health_checkup.notes}\n{notes}"
                else:
                    health_checkup.notes = notes
                health_checkup.save()

            is_merged = True
            merge_message = f'已合并到已有的 {checkup_date} {hospital} 报告'
        else:
            # 创建新报告
            health_checkup = HealthCheckup.objects.create(
                user=request.user,
                checkup_date=checkup_date,
                hospital=hospital,
                notes=notes,
                report_file=file_path
            )
            is_merged = False
            merge_message = ''

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

        # 启动后台处理
        import threading
        processing_thread = threading.Thread(
            target=process_document_background,
            args=(document_processing.id, full_file_path),
            name=f"MiniProgram-DocumentProcessing-{document_processing.id}"
        )
        processing_thread.daemon = False
        processing_thread.start()

        return Response({
            'success': True,
            'message': merge_message if is_merged else '上传成功，正在处理...',
            'processing_id': document_processing.id,
            'checkup_id': health_checkup.id,
            'is_merged': is_merged,
            'merged_into_existing': is_merged
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
        indicator_type = request.GET.get('type', None)  # 获取指标类型参数

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
            )
        else:
            # 获取用户所有指标
            indicators = HealthIndicator.objects.filter(
                checkup__user=request.user
            )

        # 根据指标类型过滤
        if indicator_type:
            indicators = indicators.filter(indicator_type=indicator_type)

        # 处理排序参数
        ordering = request.GET.get('ordering', '-checkup__checkup_date')
        indicators = indicators.order_by(ordering)

        # 分页
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))

        start = (page - 1) * page_size
        end = start + page_size
        indicators_page = indicators[start:end]

        serializer = HealthIndicatorSerializer(indicators_page, many=True)

        # 调试：打印前3个指标数据
        print(f"[小程序指标API] 返回 {len(serializer.data)} 个指标")
        for i, indicator in enumerate(serializer.data[:3]):
            print(f"  指标{i+1}: indicator_name='{indicator.get('indicator_name')}', value='{indicator.get('value')}', unit='{indicator.get('unit')}'")

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
    """获取AI健康建议 - 支持对话模式和报告分析"""
    try:
        data = json.loads(request.body)

        # 支持两种模式：
        # 1. 旧模式：checkup_id（单份报告分析）
        # 2. 新模式：question + selected_reports + conversation_id + selected_medications（对话模式）

        checkup_id = data.get('checkup_id')
        question = data.get('question')
        selected_reports_ids = data.get('selected_reports', [])
        selected_medications_ids = data.get('selected_medications', [])
        conversation_id = data.get('conversation_id')

        # 对话模式（新）
        if question:
            from .views import generate_ai_advice
            from .models import Conversation, Medication

            # 处理对话
            if conversation_id:
                try:
                    conversation = Conversation.objects.get(
                        id=conversation_id,
                        user=request.user,
                        is_active=True
                    )
                except Conversation.DoesNotExist:
                    return Response({
                        'success': False,
                        'message': '对话不存在或已删除'
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
                # 创建新对话
                question_text = question[:50]
                if len(question) > 50:
                    question_text += '...'
                conversation = Conversation.create_new_conversation(
                    request.user,
                    f"健康咨询: {question_text}"
                )

            # 处理报告选择
            selected_reports = None
            if selected_reports_ids and len(selected_reports_ids) > 0:
                selected_reports = HealthCheckup.objects.filter(
                    id__in=selected_reports_ids,
                    user=request.user
                )

            # 处理药单选择
            selected_medications = None
            if selected_medications_ids and len(selected_medications_ids) > 0:
                selected_medications = Medication.objects.filter(
                    id__in=selected_medications_ids,
                    user=request.user
                )
                print(f"[小程序AI] 本次对话将引用 {len(selected_medications)} 份药单")

            # 生成AI响应（传递药单信息）
            answer, prompt_sent, conversation_context = generate_ai_advice(
                question,
                request.user,
                selected_reports,
                conversation,
                selected_medications
            )

            # 保存对话记录
            selected_reports_json = json.dumps(selected_reports_ids) if selected_reports_ids else None
            selected_medications_json = json.dumps(selected_medications_ids) if selected_medications_ids else None
            health_advice = HealthAdvice.objects.create(
                user=request.user,
                question=question,
                answer=answer,
                prompt_sent=prompt_sent,
                conversation_context=json.dumps(conversation_context, ensure_ascii=False) if conversation_context else None,
                conversation=conversation,
                selected_reports=selected_reports_json
            )

            return Response({
                'success': True,
                'answer': answer,
                'prompt': prompt_sent,
                'conversation_id': conversation.id
            })

        # 旧模式：单份报告分析
        elif checkup_id:
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

        else:
            return Response({
                'success': False,
                'message': '请提供question或checkup_id参数'
            }, status=status.HTTP_400_BAD_REQUEST)

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

# ==================== 创建对话并发送消息（异步流式）====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_create_conversation(request):
    """创建新的AI对话并发送第一条消息（流式处理）"""
    try:
        from .models import Conversation
        import threading

        data = json.loads(request.body)
        question = data.get('question', '').strip()
        selected_reports_ids = data.get('selected_reports', [])
        selected_medications_ids = data.get('selected_medications', [])
        conversation_id = data.get('conversation_id')

        # 验证问题
        if not question:
            return Response({
                'success': False,
                'message': '请输入问题'
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(question) < 5:
            return Response({
                'success': False,
                'message': '请详细描述您的问题，至少5个字符'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 处理对话
        if conversation_id:
            # 继续已有对话
            try:
                conversation = Conversation.objects.get(
                    id=conversation_id,
                    user=request.user,
                    is_active=True
                )
            except Conversation.DoesNotExist:
                return Response({
                    'success': False,
                    'message': '对话不存在或已删除'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            # 创建新对话，使用问题前50个字符作为标题
            question_text = question[:50]
            if len(question) > 50:
                question_text += '...'
            conversation = Conversation.create_new_conversation(
                request.user,
                f"健康咨询: {question_text}"
            )

        # 立即创建一个空的HealthAdvice记录，用于存储流式生成的内容
        # 保存选中的报告ID列表
        selected_reports_json = json.dumps(selected_reports_ids) if selected_reports_ids else None
        health_advice = HealthAdvice.objects.create(
            user=request.user,
            question=question,
            answer='',  # 初始为空，后续更新
            conversation=conversation,
            selected_reports=selected_reports_json
        )

        print(f"[小程序] 创建对话成功，conversation_id: {conversation.id}, advice_id: {health_advice.id}")

        # 立即返回对话ID和消息ID
        response_data = {
            'success': True,
            'message': '对话创建成功',
            'conversation_id': conversation.id,
            'advice_id': health_advice.id,
            'data': {
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at.isoformat()
            }
        }

        # 在后台线程中异步生成AI响应（流式更新）
        def generate_ai_response_stream():
            from .views import generate_ai_advice
            from .models import HealthAdvice as HA  # Import locally to avoid closure issues
            from django.db import connection
            # 保存ID，避免闭包问题
            advice_id = health_advice.id
            conversation_id = conversation.id
            user_id = request.user.id
            question_text = question
            report_mode_data = data.get('report_mode', 'none')

            print(f"[后台线程] 开始生成AI响应，advice_id: {advice_id}")

            # 关闭旧的数据库连接，避免线程间共享连接
            connection.close()

            try:
                # 在新线程中重新获取对象
                from django.contrib.auth import get_user_model
                User = get_user_model()
                health_advice = HA.objects.get(id=advice_id)
                conv = Conversation.objects.get(id=conversation_id)
                user = User.objects.get(id=user_id)

                # 处理报告选择
                if report_mode_data == 'none':
                    selected_reports = None
                elif report_mode_data == 'select' and len(selected_reports_ids) > 0:
                    selected_reports = HealthCheckup.objects.filter(
                        id__in=selected_reports_ids,
                        user=user
                    )
                else:
                    selected_reports = None

                print(f"[后台线程] 报告模式: {report_mode_data}, 报告数量: {len(selected_reports) if selected_reports else 0}")

                # 处理药单选择
                selected_medications = None
                if selected_medications_ids:
                    from .models import Medication
                    selected_medications = Medication.objects.filter(
                        id__in=selected_medications_ids,
                        user=user
                    )
                    print(f"[后台线程] 药单数量: {len(selected_medications)}")

                # 生成AI响应
                answer, prompt_sent, conversation_context = generate_ai_advice(
                    question_text,
                    user,
                    selected_reports,
                    conv,
                    selected_medications
                )

                print(f"[后台线程] AI响应生成成功，长度: {len(answer)} 字符")

                # 更新HealthAdvice记录
                health_advice.answer = answer
                health_advice.prompt_sent = prompt_sent
                health_advice.conversation_context = json.dumps(conversation_context, ensure_ascii=False) if conversation_context else None
                health_advice.save()

                print(f"[后台线程] 数据库更新完成，advice_id: {advice_id}")
            except Exception as e:
                import traceback
                print(f"[后台线程] AI响应生成失败: {str(e)}")
                traceback.print_exc()
                # 即使失败也更新状态
                try:
                    health_advice = HA.objects.get(id=advice_id)
                    health_advice.answer = f"抱歉，生成回复时出现错误：{str(e)}"
                    health_advice.save()
                except Exception as save_error:
                    print(f"[后台线程] 保存失败信息时出错: {str(save_error)}")
            finally:
                # 确保关闭数据库连接
                try:
                    connection.close()
                except:
                    pass

        # 启动后台线程（非daemon，确保线程能完成）
        thread = threading.Thread(target=generate_ai_response_stream)
        thread.daemon = False  # ← 改为非daemon，确保线程能完成
        thread.start()
        print(f"[小程序] 后台线程已启动，advice_id: {health_advice.id}")

        return Response(response_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'message': f'创建对话失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 获取单个消息状态（用于流式轮询）====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_advice_message_status(request, advice_id):
    """获取单个AI建议消息的当前状态（用于流式轮询）"""
    try:
        advice = HealthAdvice.objects.get(
            id=advice_id,
            user=request.user
        )

        # 判断是否正在生成中：answer为空字符串表示还在生成
        is_generating = len(advice.answer.strip()) == 0

        return Response({
            'success': True,
            'data': {
                'id': advice.id,
                'question': advice.question,
                'answer': advice.answer,
                'is_generating': is_generating,
                'answer_length': len(advice.answer),
                'created_at': advice.created_at.isoformat()
            }
        })

    except HealthAdvice.DoesNotExist:
        return Response({
            'success': False,
            'message': '消息不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取消息状态失败: {str(e)}'
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
        last_selected_reports = []

        for msg in messages:
            # 解析selected_reports
            msg_selected_reports = []
            if msg.selected_reports:
                try:
                    msg_selected_reports = json.loads(msg.selected_reports)
                except:
                    pass

            message_list.append({
                'id': msg.id,
                'question': msg.question,
                'answer': msg.answer,
                'created_at': msg.created_at.isoformat(),
                'selected_reports': msg_selected_reports
            })

            # 保存最后一条消息的selected_reports
            if msg_selected_reports:
                last_selected_reports = msg_selected_reports

        return Response({
            'success': True,
            'data': {
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at.isoformat(),
                'updated_at': conversation.updated_at.isoformat(),
                'messages': message_list,
                'message_count': len(message_list),
                'last_selected_reports': last_selected_reports
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


# ==================== 应用数据整合结果 ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_apply_integration(request):
    """应用数据整合结果到数据库（小程序专用）"""
    try:
        from .api_views import apply_integration

        # 复用现有的应用逻辑
        result = apply_integration(request)

        return result

    except Exception as e:
        return Response({
            'success': False,
            'message': f'应用更新失败: {str(e)}'
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


# ==================== 指标类型统计 ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_indicator_types(request):
    """获取用户的指标类型统计（用于动态显示趋势分类）"""
    try:
        from django.db.models import Count, Q

        # 统计用户各类型的指标数量
        type_stats = HealthIndicator.objects.filter(
            checkup__user=request.user
        ).values('indicator_type').annotate(
            count=Count('id')
        ).order_by('-count')

        # 直接使用模型中的choices映射，确保中文名称一致
        type_names = dict(HealthIndicator.INDICATOR_TYPES)

        # 添加旧类型代码的支持（兼容历史数据）
        # 参考 migration 0003 的映射关系
        legacy_type_mapping = {
            'physical_exam': 'general_exam',      # 体格检查 → 一般检查
            'ultrasound_exam': 'ultrasound',      # 超声检查 → 超声检查
            'urine_exam': 'urine',                # 尿液检查 → 尿液检查
            'eye_exam': 'special_organs',         # 眼科检查 → 专科检查
            'imaging_exam': 'other',              # 影像学检查 → 其他检查
            'thyroid_function': 'thyroid',        # 甲状腺功能 → 甲状腺
            'diagnosis': 'pathology',             # 病症诊断 → 病理检查
            'symptoms': 'other',                  # 症状描述 → 其他检查
            'other_exam': 'other',                # 其他检查 → 其他检查
        }

        # 合并映射：优先使用新定义，然后查找旧代码映射
        all_type_names = {
            **type_names,
            **{k: type_names.get(v, '其他检查') for k, v in legacy_type_mapping.items()}
        }

        types_data = []
        for item in type_stats:
            type_key = item['indicator_type']
            types_data.append({
                'type': type_key,
                'name': all_type_names.get(type_key, type_key),
                'count': item['count']
            })

        return Response({
            'success': True,
            'data': types_data,
            'total': len(types_data)
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取指标类型失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== 检测和合并重复报告 ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_detect_duplicate_checkups(request):
    """检测重复的体检报告（相同日期和机构）"""
    try:
        from django.db.models import Count, Q
        from collections import defaultdict

        # 获取用户所有体检报告
        user_checkups = HealthCheckup.objects.filter(
            user=request.user
        ).order_by('-checkup_date', '-created_at')

        # 按日期和机构分组
        groups = defaultdict(list)
        for checkup in user_checkups:
            key = (checkup.checkup_date, checkup.hospital)
            groups[key].append({
                'id': checkup.id,
                'checkup_date': checkup.checkup_date.strftime('%Y-%m-%d'),
                'hospital': checkup.hospital,
                'notes': checkup.notes,
                'indicators_count': checkup.indicators.count(),
                'created_at': checkup.created_at.strftime('%Y-%m-%d %H:%M')
            })

        # 找出重复的报告组（每组超过1个报告）
        duplicate_groups = []
        for (date, hospital), checkups_list in groups.items():
            if len(checkups_list) > 1:
                duplicate_groups.append({
                    'date': date,
                    'hospital': hospital,
                    'checkups': checkups_list,
                    'count': len(checkups_list)
                })

        return Response({
            'success': True,
            'data': duplicate_groups,
            'total': len(duplicate_groups),
            'has_duplicates': len(duplicate_groups) > 0
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'检测重复报告失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_merge_duplicate_checkups(request):
    """合并重复的体检报告"""
    try:
        from django.db import transaction

        # 使用 request.data 而不是 json.loads(request.body)
        # request.data 可以多次访问，而 request.body 只能读取一次
        data = request.data
        target_checkup_id = data.get('target_checkup_id')
        source_checkup_ids = data.get('source_checkup_ids', [])

        if not target_checkup_id or not source_checkup_ids:
            return Response({
                'success': False,
                'message': '缺少必要参数'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 获取目标报告
        try:
            target_checkup = HealthCheckup.objects.get(
                id=target_checkup_id,
                user=request.user
            )
        except HealthCheckup.DoesNotExist:
            return Response({
                'success': False,
                'message': '目标报告不存在'
            }, status=status.HTTP_404_NOT_FOUND)

        # 获取要合并的源报告
        source_checkups = HealthCheckup.objects.filter(
            id__in=source_checkup_ids,
            user=request.user
        )

        if not source_checkups.exists():
            return Response({
                'success': False,
                'message': '没有找到要合并的源报告'
            }, status=status.HTTP_400_BAD_REQUEST)

        merged_count = 0
        error_messages = []
        source_checkup_list = list(source_checkups)  # 转换为列表避免迭代时修改QuerySet

        # 使用事务进行合并
        with transaction.atomic():
            for source_checkup in source_checkup_list:
                try:
                    # 追加备注
                    if source_checkup.notes:
                        if target_checkup.notes:
                            target_checkup.notes = f"{target_checkup.notes}\n[来自合并] {source_checkup.notes}"
                        else:
                            target_checkup.notes = f"[来自合并] {source_checkup.notes}"

                    # 迁移指标到目标报告
                    indicators_moved = source_checkup.indicators.all().update(
                        checkup=target_checkup
                    )

                    # 删除源报告
                    source_checkup.delete()

                    merged_count += 1

                except Exception as e:
                    error_messages.append(f"合并报告 {source_checkup.id} 失败: {str(e)}")

            # 保存目标报告的备注更新
            if source_checkup_list:
                target_checkup.save()

        return Response({
            'success': True,
            'message': f'成功合并 {merged_count} 份报告',
            'merged_count': merged_count,
            'errors': error_messages
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'合并报告失败: {str(e)}'
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

# ==================== 测试导出接口 ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def test_export_conversation(request, conversation_id):
    """测试导出接口，返回诊断信息"""
    try:
        # 验证对话归属
        conversation = Conversation.objects.get(
            id=conversation_id,
            user=request.user
        )

        # 检查对话是否有消息
        messages = HealthAdvice.objects.filter(conversation_id=conversation_id).order_by('created_at')

        result = {
            'success': True,
            'conversation_id': conversation_id,
            'title': conversation.title,
            'message_count': messages.count(),
            'messages': []
        }

        for msg in messages[:5]:  # 只返回前5条消息的信息
            result['messages'].append({
                'id': msg.id,
                'question_length': len(msg.question) if msg.question else 0,
                'answer_length': len(msg.answer) if msg.answer else 0,
                'question_preview': (msg.question or '')[:50] if msg.question else None,
                'created_at': msg.created_at.isoformat() if msg.created_at else None
            })

        return Response(result)

    except Conversation.DoesNotExist:
        return Response({
            'success': False,
            'message': '对话不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        import traceback
        return Response({
            'success': False,
            'message': str(e),
            'traceback': traceback.format_exc()
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 导出对话为PDF/Word ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_export_conversation_pdf(request, conversation_id):
    """导出对话为PDF"""
    try:
        from .export_utils import ConversationExporter

        # 验证对话归属
        conversation = Conversation.objects.get(
            id=conversation_id,
            user=request.user
        )

        # 检查对话是否有消息
        message_count = HealthAdvice.objects.filter(conversation_id=conversation_id).count()
        if message_count == 0:
            return Response({
                'success': False,
                'message': '该对话暂无消息内容'
            }, status=status.HTTP_400_BAD_REQUEST)

        exporter = ConversationExporter(conversation_id)
        return exporter.export_to_pdf()

    except Conversation.DoesNotExist:
        return Response({
            'success': False,
            'message': '对话不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f'[导出PDF] conversation_id={conversation_id}, error: {str(e)}')
        print(f'[导出PDF] traceback: {error_details}')
        return Response({
            'success': False,
            'message': f'导出PDF失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_export_conversation_word(request, conversation_id):
    """导出对话为Word"""
    try:
        from .export_utils import ConversationExporter

        # 验证对话归属
        conversation = Conversation.objects.get(
            id=conversation_id,
            user=request.user
        )

        # 检查对话是否有消息
        message_count = HealthAdvice.objects.filter(conversation_id=conversation_id).count()
        if message_count == 0:
            return Response({
                'success': False,
                'message': '该对话暂无消息内容'
            }, status=status.HTTP_400_BAD_REQUEST)

        exporter = ConversationExporter(conversation_id)
        return exporter.export_to_word()

    except Conversation.DoesNotExist:
        return Response({
            'success': False,
            'message': '对话不存在'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f'[导出Word] conversation_id={conversation_id}, error: {str(e)}')
        print(f'[导出Word] traceback: {error_details}')
        return Response({
            'success': False,
            'message': f'导出Word失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 导出体检报告为PDF/Word ====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_export_checkups_pdf(request):
    """小程序专用：批量导出体检报告为PDF"""
    try:
        from .export_utils import CheckupReportsExporter
        from .models import HealthCheckup

        # 获取请求中的报告ID列表
        checkup_ids = request.GET.get('checkup_ids', '')
        if not checkup_ids:
            return Response({
                'success': False,
                'message': '未选择任何报告'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 解析报告ID
        checkup_id_list = [int(id.strip()) for id in checkup_ids.split(',') if id.strip().isdigit()]

        if not checkup_id_list:
            return Response({
                'success': False,
                'message': '无效的报告ID'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 获取用户自己的报告
        checkups = HealthCheckup.objects.filter(
            user=request.user,
            id__in=checkup_id_list
        ).order_by('-checkup_date')

        if not checkups.exists():
            return Response({
                'success': False,
                'message': '未找到指定的报告'
            }, status=status.HTTP_404_NOT_FOUND)

        # 导出
        exporter = CheckupReportsExporter(checkups)
        return exporter.export_to_pdf()

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f'[导出PDF] user={request.user.username}, error: {str(e)}')
        print(f'[导出PDF] traceback: {error_details}')
        return Response({
            'success': False,
            'message': f'导出PDF失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_export_checkups_word(request):
    """小程序专用：批量导出体检报告为Word"""
    try:
        from .export_utils import CheckupReportsExporter
        from .models import HealthCheckup

        # 获取请求中的报告ID列表
        checkup_ids = request.GET.get('checkup_ids', '')
        if not checkup_ids:
            return Response({
                'success': False,
                'message': '未选择任何报告'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 解析报告ID
        checkup_id_list = [int(id.strip()) for id in checkup_ids.split(',') if id.strip().isdigit()]

        if not checkup_id_list:
            return Response({
                'success': False,
                'message': '无效的报告ID'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 获取用户自己的报告
        checkups = HealthCheckup.objects.filter(
            user=request.user,
            id__in=checkup_id_list
        ).order_by('-checkup_date')

        if not checkups.exists():
            return Response({
                'success': False,
                'message': '未找到指定的报告'
            }, status=status.HTTP_404_NOT_FOUND)

        # 导出
        exporter = CheckupReportsExporter(checkups)
        return exporter.export_to_word()

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f'[导出Word] user={request.user.username}, error: {str(e)}')
        print(f'[导出Word] traceback: {error_details}')
        return Response({
            'success': False,
            'message': f'导出Word失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ==================== 完善个人信息 ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_complete_profile(request):
    """完善用户个人信息"""
    try:
        from .models import UserProfile

        data = json.loads(request.body)
        print(f"[调试] 接收到的数据: {data}")

        # 获取或创建UserProfile
        user_profile, created = UserProfile.objects.get_or_create(user=request.user)
        print(f"[调试] UserProfile {'创建' if created else '获取'}成功")

        # 更新用户信息
        if 'nickname' in data:
            request.user.first_name = data['nickname']
            request.user.save()
            print(f"[调试] 昵称已更新: {data['nickname']}")

        # 更新UserProfile
        if 'birth_date' in data:
            from datetime import datetime
            try:
                birth_date = datetime.strptime(data['birth_date'], '%Y-%m-%d').date()

                # 验证出生日期不能是未来日期
                from datetime import date
                if birth_date > date.today():
                    return Response({
                        'success': False,
                        'message': '出生日期不能是未来日期'
                    }, status=status.HTTP_400_BAD_REQUEST)

                user_profile.birth_date = birth_date
                print(f"[调试] 出生日期已更新: {birth_date}")
            except Exception as e:
                print(f"[调试] 出生日期解析失败: {e}")

        if 'gender' in data:
            user_profile.gender = data['gender']
            print(f"[调试] 性别已更新: {data['gender']}")

        user_profile.save()
        print(f"[调试] UserProfile已保存")

        return Response({
            'success': True,
            'message': '个人信息保存成功',
            'user': UserSerializer(request.user).data
        })
    except Exception as e:
        print(f"[调试] 保存失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'message': f'保存失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== 药单管理API ====================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def miniprogram_medications(request):
    """获取或创建药单"""
    from .models import Medication, MedicationRecord

    if request.method == 'GET':
        # 获取用户的所有药单
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

        return Response({
            'success': True,
            'medications': medication_list
        })

    elif request.method == 'POST':
        # 创建新药单
        try:
            data = json.loads(request.body)

            # 验证必填字段
            if not data.get('medicine_name') or not data.get('dosage'):
                return Response({
                    'success': False,
                    'message': '药名和服药方式为必填项'
                }, status=status.HTTP_400_BAD_REQUEST)

            if not data.get('start_date') or not data.get('end_date'):
                return Response({
                    'success': False,
                    'message': '开始日期和结束日期为必填项'
                }, status=status.HTTP_400_BAD_REQUEST)

            # 创建药单
            medication = Medication.objects.create(
                user=request.user,
                medicine_name=data['medicine_name'],
                dosage=data['dosage'],
                start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
                end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
                notes=data.get('notes', '')
            )

            return Response({
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
            return Response({
                'success': False,
                'message': f'创建药单失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def miniprogram_medication_detail(request, medication_id):
    """获取、更新或删除单个药单"""
    from .models import Medication, MedicationRecord

    try:
        medication = Medication.objects.get(id=medication_id, user=request.user)
    except Medication.DoesNotExist:
        return Response({
            'success': False,
            'message': '药单不存在或无权访问'
        }, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        # 获取药单详情及服药记录
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

        return Response({
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

            medication.medicine_name = data.get('medicine_name', medication.medicine_name)
            medication.dosage = data.get('dosage', medication.dosage)
            medication.notes = data.get('notes', medication.notes)
            medication.is_active = data.get('is_active', medication.is_active)

            if data.get('start_date'):
                medication.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            if data.get('end_date'):
                medication.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()

            medication.save()

            return Response({
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
            return Response({
                'success': False,
                'message': f'更新药单失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    elif request.method == 'DELETE':
        # 删除药单
        medication.delete()
        return Response({
            'success': True,
            'message': '药单已删除'
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_medication_checkin(request):
    """服药签到"""
    from .models import Medication, MedicationRecord

    try:
        data = json.loads(request.body)

        medication_id = data.get('medication_id')
        record_date = data.get('record_date')
        frequency = data.get('frequency', 'daily')
        notes = data.get('notes', '')

        if not medication_id or not record_date:
            return Response({
                'success': False,
                'message': '缺少必要参数'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 获取药单
        try:
            medication = Medication.objects.get(id=medication_id, user=request.user)
        except Medication.DoesNotExist:
            return Response({
                'success': False,
                'message': '药单不存在或无权访问'
            }, status=status.HTTP_404_NOT_FOUND)

        # 解析日期
        record_date_obj = datetime.strptime(record_date, '%Y-%m-%d').date()

        # 检查是否已签到
        existing_record = MedicationRecord.objects.filter(
            medication=medication,
            record_date=record_date_obj
        ).first()

        if existing_record:
            return Response({
                'success': False,
                'message': '今日已签到',
                'existing_record': {
                    'id': existing_record.id,
                    'record_date': existing_record.record_date.strftime('%Y-%m-%d'),
                    'taken_at': existing_record.taken_at.strftime('%Y-%m-%d %H:%M:%S'),
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        # 创建服药记录
        record = MedicationRecord.objects.create(
            medication=medication,
            record_date=record_date_obj,
            frequency=frequency,
            notes=notes
        )

        return Response({
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
        return Response({
            'success': False,
            'message': f'签到失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_medication_records(request, medication_id):
    """获取药单的服药记录"""
    from .models import Medication, MedicationRecord

    try:
        medication = Medication.objects.get(id=medication_id, user=request.user)
    except Medication.DoesNotExist:
        return Response({
            'success': False,
            'message': '药单不存在或无权访问'
        }, status=status.HTTP_404_NOT_FOUND)

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

    return Response({
        'success': True,
        'records': record_list
    })

