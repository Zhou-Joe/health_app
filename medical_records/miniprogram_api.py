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
import threading
from datetime import datetime, timedelta

from .models import HealthCheckup, HealthIndicator, HealthAdvice, SystemSettings, DocumentProcessing, Conversation
from .services import DocumentProcessingService, VisionLanguageModelService, AIService
from .miniprogram_serializers import (
    UserSerializer, HealthCheckupSerializer, HealthIndicatorSerializer,
    HealthAdviceSerializer, DocumentProcessingSerializer,
    MiniProgramCheckupListSerializer
)


def _get_request_data(request):
    """兼容 DRF Request 与原生 HttpRequest 的请求数据解析。"""
    if hasattr(request, 'data'):
        data = request.data
        if isinstance(data, dict):
            return data
        if hasattr(data, 'dict'):
            try:
                return data.dict()
            except Exception:
                pass

    try:
        raw = request.body
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        return json.loads(raw) if raw else {}
    except Exception:
        return {}

@api_view(['POST'])
@permission_classes([])  # Disable CSRF for login
def miniprogram_login(request):
    """小程序登录API - 支持微信登录"""
    try:
        data = _get_request_data(request)

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

            # 保存微信头像（优先使用最新授权头像）
            if avatar_url:
                user_profile.avatar_url = avatar_url
                user_profile.save(update_fields=['avatar_url', 'updated_at'])

            # 首次登录或昵称为空时，用微信昵称补全
            if nickname and (created or not user.first_name or user.first_name == '微信用户'):
                user.first_name = nickname
                user.save(update_fields=['first_name'])

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


@api_view(['POST'])
@permission_classes([])  # 注册不需要登录
def miniprogram_register(request):
    """
    跨端应用注册API

    请求参数：
    - username: 用户名（必填）
    - password: 密码（必填，最少6位）
    - nickname: 昵称（可选，不填则使用用户名）
    """
    try:
        data = _get_request_data(request)

        username = data.get('username', '').strip()
        password = data.get('password', '')
        nickname = data.get('nickname', '').strip()

        # 验证必填字段
        if not username:
            return Response({
                'success': False,
                'message': '用户名不能为空'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not password:
            return Response({
                'success': False,
                'message': '密码不能为空'
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(password) < 6:
            return Response({
                'success': False,
                'message': '密码长度不能少于6位'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 检查用户名是否已存在
        if User.objects.filter(username=username).exists():
            return Response({
                'success': False,
                'message': '该用户名已被注册，请使用其他用户名'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 创建用户
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=nickname or username,
            is_active=True
        )

        print(f"[跨端注册] 新用户注册成功: {username}")

        # 创建UserProfile
        from .models import UserProfile
        UserProfile.objects.get_or_create(user=user)

        # 生成Token
        token = get_or_create_token(user)

        return Response({
            'success': True,
            'message': '注册成功',
            'token': token,
            'user': {
                'id': user.id,
                'username': user.username,
                'nickname': user.first_name,
                'is_new_user': True
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'message': f'注册失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
        
        # 根据文件类型自动选择工作流
        workflow_type = request.POST.get('workflow_type', '')
        if not workflow_type:
            file_ext = file.name.lower().split('.')[-1] if '.' in file.name else ''
            if file_ext == 'pdf':
                workflow_type = SystemSettings.get_pdf_ocr_workflow()
            else:
                workflow_type = 'vl_model'

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

@csrf_exempt
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
                is_generating=False,  # 已完成生成
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
            'pdf_ocr_workflow': SystemSettings.get_pdf_ocr_workflow()
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
            'pdf_ocr_workflow': SystemSettings.get_pdf_ocr_workflow(),
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

        # 临时测试：强制同步执行（阻塞）
        force_sync = data.get('force_sync', False)  # 如果请求中包含force_sync=true，则同步执行

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
            is_generating=True,  # 标记为正在生成中
            conversation=conversation,
            selected_reports=selected_reports_json
        )

        print(f"[小程序] 创建对话成功，conversation_id: {conversation.id}, advice_id: {health_advice.id}, force_sync: {force_sync}")

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

        # 在后台线程中异步生成AI响应（使用与网页版一致的Agent模式）
        def generate_ai_response_stream():
            from .models import HealthAdvice as HA  # Import locally to avoid closure issues
            from django.db import connection
            from .models import SystemSettings

            print(f"[小程序后台线程] 线程启动，advice_id: {health_advice.id}")
            from django.db import connection
            from .llm_prompts import AI_DOCTOR_SYSTEM_PROMPT
            from .views import get_conversation_context, format_health_data_for_prompt, get_selected_reports_health_data
            # 保存ID，避免闭包问题
            advice_id = health_advice.id
            conversation_id = conversation.id
            user_id = request.user.id
            question_text = question
            report_mode_data = data.get('report_mode', 'none')

            print(f"[小程序后台线程] 开始生成AI响应（Agent模式），advice_id: {advice_id}, question: {question_text[:30]}...")

            # 关闭旧的数据库连接，避免线程间共享连接
            connection.close()

            try:
                # 在新线程中重新获取对象
                from django.contrib.auth import get_user_model
                User = get_user_model()

                print(f"[小程序后台线程] 重新获取数据库对象...")
                health_advice = HA.objects.get(id=advice_id)
                conv = Conversation.objects.get(id=conversation_id)
                user = User.objects.get(id=user_id)

                print(f"[小程序后台线程] 数据库对象获取成功")

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

                print(f"[小程序后台线程] 报告模式: {report_mode_data}, 报告数量: {len(selected_reports) if selected_reports else 0}")

                # 处理药单选择
                selected_medications = None
                if selected_medications_ids:
                    from .models import Medication
                    selected_medications = Medication.objects.filter(
                        id__in=selected_medications_ids,
                        user=user
                    )
                    print(f"[小程序后台线程] 药单数量: {len(selected_medications)}")

                # 检查AI医生配置
                api_url = SystemSettings.get_setting('ai_doctor_api_url')
                api_key = SystemSettings.get_setting('ai_doctor_api_key')
                model_name = SystemSettings.get_setting('ai_doctor_model_name')

                print(f"[小程序后台线程] AI医生配置 - URL: {api_url}, Model: {model_name}, API Key: {'已配置' if api_key else '未配置'}")

                if not api_url or not api_key or not model_name:
                    raise Exception("AI医生未配置，请在系统设置中配置API URL、API Key和模型名称")

                # ========== 使用与网页版一致的Agent模式 ==========
                print(f"[小程序后台线程] 开始创建Agent...")
                from .ai_doctor_agent_v2 import create_real_ai_doctor_agent

                try:
                    # 创建Agent
                    agent = create_real_ai_doctor_agent(user, conv)
                    print(f"[小程序后台线程] Agent创建成功，开始执行ask_question...")

                    # 执行Agent（ask_question会自动构建prompt并返回conversation_context）
                    result = agent.ask_question(question_text, selected_reports, selected_medications)

                    print(f"[小程序后台线程] Agent执行完成，result keys: {list(result.keys())}")

                    if result.get('success') and result.get('answer'):
                        answer = result['answer']
                        prompt_sent = result.get('prompt', '')
                        conversation_context = result.get('conversation_context')
                        print(f"[小程序后台线程] ✓ Agent响应生成成功，长度: {len(answer)} 字符")
                    else:
                        # Agent失败，尝试回退到简化模式
                        error_msg = result.get('error', '未知错误')
                        print(f"[小程序后台线程] ⚠ Agent执行失败: {error_msg}，尝试回退到简化模式...")
                        raise Exception(f"Agent执行失败: {error_msg}")

                except Exception as agent_error:
                    print(f"[小程序后台线程] ⚠ Agent异常: {str(agent_error)}")
                    print(f"[小程序后台线程] 尝试使用views.generate_ai_advice作为回退...")

                    import traceback
                    traceback.print_exc()

                    # 回退到原来的generate_ai_advice函数
                    try:
                        from .views import generate_ai_advice
                        answer, prompt_sent, conversation_context = generate_ai_advice(
                            question_text,
                            user,
                            selected_reports,
                            conv,
                            selected_medications
                        )
                        print(f"[小程序后台线程] ✓ 回退模式响应生成成功，长度: {len(answer)} 字符")
                    except Exception as fallback_error:
                        print(f"[小程序后台线程] ✗ 回退模式也失败: {str(fallback_error)}")
                        traceback.print_exc()
                        raise fallback_error

                # 更新HealthAdvice记录
                print(f"[小程序后台线程] 开始更新数据库...")
                health_advice.answer = answer
                health_advice.prompt_sent = prompt_sent
                health_advice.conversation_context = json.dumps(conversation_context, ensure_ascii=False) if conversation_context else None
                health_advice.save()

                print(f"[小程序后台线程] ✓ 数据库更新完成，advice_id: {advice_id}, answer长度: {len(answer)}")
            except Exception as e:
                import traceback
                print(f"[小程序后台线程] ✗ AI响应生成失败: {str(e)}")
                print(f"[小程序后台线程] 错误类型: {type(e).__name__}")
                traceback.print_exc()

                # 即使失败也更新状态，记录错误信息
                try:
                    health_advice = HA.objects.get(id=advice_id)
                    health_advice.answer = f"抱歉，生成回复时出现错误：{str(e)}"
                    health_advice.save()
                    print(f"[小程序后台线程] 已将错误信息保存到数据库")
                except Exception as save_error:
                    print(f"[小程序后台线程] ✗ 保存失败信息时出错: {str(save_error)}")
                    traceback.print_exc()
            finally:
                # 确保关闭数据库连接
                try:
                    connection.close()
                except:
                    pass

        # 启动后台线程（非daemon，确保线程能完成）
        print(f"[小程序] 准备启动后台线程，advice_id: {health_advice.id}, force_sync: {force_sync}")

        if force_sync:
            # 同步执行（用于测试）
            print(f"[小程序] 使用同步模式执行AI生成")
            try:
                generate_ai_response_stream()
                # 等待一下确保保存完成
                import time
                time.sleep(1)
                # 重新获取health_advice，确认answer已保存
                health_advice.refresh_from_db()
                if health_advice.answer:
                    print(f"[小程序] ✓ 同步模式执行成功，answer长度: {len(health_advice.answer)}")
                else:
                    print(f"[小程序] ⚠ 同步模式执行完成但answer为空")
            except Exception as e:
                print(f"[小程序] ✗ 同步模式执行失败: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            # 异步执行（后台线程）
            thread = threading.Thread(target=generate_ai_response_stream)
            thread.daemon = False  # ← 改为非daemon，确保线程能完成
            thread.start()
            print(f"[小程序] ✓ 后台线程已启动，advice_id: {health_advice.id}, thread_id: {thread.ident}, is_alive: {thread.is_alive()}")

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

        print(f"[小程序对话详情] 查询对话, conversation_id: {conversation_id}, user: {request.user.username}")

        conversation = Conversation.objects.get(
            id=conversation_id,
            user=request.user
        )

        print(f"[小程序对话详情] 找到对话: {conversation.title}")

        # 获取对话中的所有消息
        messages = HealthAdvice.get_conversation_messages(conversation_id)

        print(f"[小程序对话详情] 获取到 {len(messages)} 条消息")

        message_list = []
        last_selected_reports = []
        last_selected_medications = []

        for index, msg in enumerate(messages):
            # 解析 selected_reports
            msg_selected_reports = []
            if msg.selected_reports:
                try:
                    msg_selected_reports = json.loads(msg.selected_reports)
                except:
                    pass

            # 解析 selected_medications
            msg_selected_medications = []
            if msg.selected_medications:
                try:
                    msg_selected_medications = json.loads(msg.selected_medications)
                except:
                    pass

            print(f"[小程序对话详情] 消息 {index + 1}: question={msg.question[:30] if msg.question else 'None'}..., answer长度={len(msg.answer) if msg.answer else 0}")

            message_list.append({
                'id': msg.id,
                'question': msg.question,
                'answer': msg.answer or '',
                'created_at': msg.created_at.isoformat(),
                'selected_reports': msg_selected_reports,
                'selected_medications': msg_selected_medications
            })

            # 保存最后一条消息的选择
            if msg_selected_reports:
                last_selected_reports = msg_selected_reports
            if msg_selected_medications:
                last_selected_medications = msg_selected_medications

        return Response({
            'success': True,
            'data': {
                'id': conversation.id,
                'title': conversation.title,
                'created_at': conversation.created_at.isoformat(),
                'updated_at': conversation.updated_at.isoformat(),
                'messages': message_list,
                'message_count': len(message_list),
                'last_selected_reports': last_selected_reports,
                'last_selected_medications': last_selected_medications
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_indicator_trends(request):
    """获取用户的健康指标趋势数据（按类型分组）"""
    try:
        import re
        from collections import defaultdict
        from django.db.models import Count, Q

        user = request.user

        def extract_numeric_value(value_str):
            if not value_str:
                return None
            match = re.search(r'-?\d+\.?\d*', str(value_str))
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
            return None

        indicator_type = request.query_params.get('type', None)

        indicators_query = HealthIndicator.objects.filter(
            checkup__user=user
        ).select_related('checkup').order_by('-checkup__checkup_date')

        if indicator_type:
            indicators_query = indicators_query.filter(indicator_type=indicator_type)

        indicators_by_name = defaultdict(list)
        for indicator in indicators_query:
            indicators_by_name[indicator.indicator_name].append({
                'date': indicator.checkup.checkup_date.strftime('%Y-%m-%d'),
                'value': str(indicator.value) if indicator.value else '',
                'unit': indicator.unit or '',
                'reference_range': indicator.reference_range or '',
                'status': indicator.status,
                'checkup_id': indicator.checkup.id,
                'hospital': indicator.checkup.hospital,
            })

        type_names = dict(HealthIndicator.INDICATOR_TYPES)

        trends_by_type = defaultdict(list)
        for name, records in indicators_by_name.items():
            if records:
                indicator_type_key = HealthIndicator.objects.filter(
                    indicator_name=name
                ).first()
                type_key = indicator_type_key.indicator_type if indicator_type_key else 'other'
                
                numeric_values = [extract_numeric_value(r['value']) for r in records]
                numeric_values = [v for v in numeric_values if v is not None]
                
                trend = 'stable'
                if len(numeric_values) >= 2:
                    if numeric_values[0] > numeric_values[1]:
                        trend = 'up'
                    elif numeric_values[0] < numeric_values[1]:
                        trend = 'down'

                indicator_data = {
                    'name': name,
                    'type': type_key,
                    'type_name': type_names.get(type_key, type_key),
                    'records': records,
                    'latest_value': records[0]['value'] if records else '',
                    'latest_unit': records[0]['unit'] if records else '',
                    'latest_status': records[0]['status'] if records else '',
                    'latest_reference': records[0]['reference_range'] if records else '',
                    'trend': trend,
                    'record_count': len(records),
                }
                trends_by_type[type_key].append(indicator_data)

        result = []
        for type_key, indicators in trends_by_type.items():
            result.append({
                'type': type_key,
                'type_name': type_names.get(type_key, type_key),
                'indicators': sorted(indicators, key=lambda x: x['record_count'], reverse=True),
                'count': len(indicators),
            })

        result.sort(key=lambda x: x['count'], reverse=True)

        return Response({
            'success': True,
            'data': result,
            'total': len(result)
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'获取指标趋势失败: {str(e)}'
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
        import os
        import zipfile
        import io
        from django.core.files.base import ContentFile

        data = request.data
        target_checkup_id = data.get('target_checkup_id')
        source_checkup_ids = data.get('source_checkup_ids', [])

        if not target_checkup_id or not source_checkup_ids:
            return Response({
                'success': False,
                'message': '缺少必要参数'
            }, status=status.HTTP_400_BAD_REQUEST)

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
        source_checkup_list = list(source_checkups)
        zip_created = False

        with transaction.atomic():
            source_files = []
            
            if target_checkup.report_file:
                source_files.append({
                    'file': target_checkup.report_file,
                    'name': f"{target_checkup.checkup_date}_{target_checkup.hospital or '未知机构'}_{os.path.basename(target_checkup.report_file.name)}"
                })
            
            for source_checkup in source_checkup_list:
                try:
                    if source_checkup.report_file:
                        source_files.append({
                            'file': source_checkup.report_file,
                            'name': f"{source_checkup.checkup_date}_{source_checkup.hospital or '未知机构'}_{os.path.basename(source_checkup.report_file.name)}"
                        })
                    
                    if source_checkup.notes:
                        if target_checkup.notes:
                            target_checkup.notes = f"{target_checkup.notes}\n[来自合并] {source_checkup.notes}"
                        else:
                            target_checkup.notes = f"[来自合并] {source_checkup.notes}"

                    indicators_moved = source_checkup.indicators.all().update(
                        checkup=target_checkup
                    )

                    source_checkup.delete()
                    merged_count += 1

                except Exception as e:
                    error_messages.append(f"合并报告 {source_checkup.id} 失败: {str(e)}")

            if source_files:
                try:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for sf in source_files:
                            try:
                                file_content = sf['file'].read()
                                safe_name = "".join(c for c in sf['name'] if c.isalnum() or c in '._- ')
                                zip_file.writestr(safe_name, file_content)
                            except Exception as e:
                                error_messages.append(f"读取文件失败: {str(e)}")
                    
                    zip_buffer.seek(0)
                    zip_content = zip_buffer.read()
                    zip_filename = f"merged_{target_checkup.checkup_date}_{target_checkup.hospital or '整合报告'}.zip"
                    zip_filename = "".join(c for c in zip_filename if c.isalnum() or c in '._- ')
                    
                    target_checkup.report_file.save(
                        zip_filename,
                        ContentFile(zip_content),
                        save=False
                    )
                    zip_created = True
                except Exception as e:
                    error_messages.append(f"创建ZIP失败: {str(e)}")

            target_checkup.save()

        return Response({
            'success': True,
            'message': f'成功合并 {merged_count} 份报告' + ('，源文件已打包' if zip_created else ''),
            'merged_count': merged_count,
            'zip_created': zip_created,
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

        data = _get_request_data(request)
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

        if 'avatar_url' in data:
            user_profile.avatar_url = data['avatar_url']
            print(f"[调试] 头像URL已更新: {data['avatar_url']}")

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
    from .models import Medication, MedicationRecord, MedicationGroup

    if request.method == 'GET':
        from .models import MedicationGroup
        
        groups = MedicationGroup.objects.filter(user=request.user).order_by('-created_at')
        group_list = []
        for group in groups:
            medications_in_group = group.medications.all()
            med_list = []
            for med in medications_in_group:
                med_list.append({
                    'id': med.id,
                    'group': group.id,
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
            group_list.append({
                'id': group.id,
                'name': group.name,
                'source_image': group.source_image.url if group.source_image else None,
                'ai_summary': group.ai_summary,
                'created_at': group.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'medication_count': group.medication_count,
                'medications': med_list,
            })
        
        standalone_medications = Medication.objects.filter(user=request.user, group__isnull=True).order_by('-created_at')
        standalone_list = []
        for med in standalone_medications:
            standalone_list.append({
                'id': med.id,
                'group': None,
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
            'groups': group_list,
            'standalone_medications': standalone_list,
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


# ==================== 头像管理API ====================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_upload_avatar(request):
    """小程序上传用户头像"""
    try:
        # 获取上传的文件
        if 'avatar' not in request.FILES:
            return Response({
                'success': False,
                'message': '未找到上传文件'
            }, status=status.HTTP_400_BAD_REQUEST)

        avatar_file = request.FILES['avatar']

        # 验证文件类型
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if avatar_file.content_type not in allowed_types:
            return Response({
                'success': False,
                'message': '只支持 JPG、PNG、GIF、WEBP 格式的图片'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 验证文件大小（限制为 5MB）
        max_size = 5 * 1024 * 1024  # 5MB
        if avatar_file.size > max_size:
            return Response({
                'success': False,
                'message': '图片大小不能超过 5MB'
            }, status=status.HTTP_400_BAD_REQUEST)

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

        return Response({
            'success': True,
            'avatar_url': avatar_url,
            'message': '头像上传成功',
            'user': UserSerializer(request.user).data
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'message': f'上传失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def miniprogram_get_avatar(request):
    """小程序获取用户头像"""
    try:
        from .models import UserProfile
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        
        avatar_url = profile.avatar_url if profile.avatar_url else None
        
        return Response({
            'success': True,
            'avatar_url': avatar_url,
            'user': UserSerializer(request.user).data
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'success': False,
            'message': f'获取头像失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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


# ==================== 修改密码 ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_change_password(request):
    """修改密码API"""
    try:
        data = _get_request_data(request)

        old_password = data.get('old_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')

        # 参数验证
        if not old_password or not new_password or not confirm_password:
            return Response({
                'success': False,
                'message': '请提供完整参数'
            }, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({
                'success': False,
                'message': '两次输入的新密码不一致'
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 6:
            return Response({
                'success': False,
                'message': '新密码长度不能少于6位'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 验证旧密码
        user = request.user
        if not user.check_password(old_password):
            return Response({
                'success': False,
                'message': '原密码错误'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 修改密码
        user.set_password(new_password)
        user.save()

        # 删除旧的Token，重新生成（可选）
        try:
            token = Token.objects.get(user=user)
            token.delete()
            new_token = Token.objects.create(user=user)
        except Token.DoesNotExist:
            new_token = Token.objects.create(user=user)

        return Response({
            'success': True,
            'message': '密码修改成功',
            'token': new_token.key
        })

    except Exception as e:
        return Response({
            'success': False,
            'message': f'修改密码失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ==================== 药单识别 ====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def miniprogram_recognize_medication_image(request):
    """小程序识别药单图片并创建药单组"""
    try:
        if 'image' not in request.FILES:
            return Response({
                'success': False,
                'error': '未找到上传的图片'
            }, status=status.HTTP_400_BAD_REQUEST)

        image_file = request.FILES['image']

        # 验证文件类型
        allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        if image_file.content_type not in allowed_types:
            return Response({
                'success': False,
                'error': '只支持 JPG、PNG、GIF、WEBP 格式的图片'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 验证文件大小（限制为 10MB）
        max_size = 10 * 1024 * 1024
        if image_file.size > max_size:
            return Response({
                'success': False,
                'error': '图片大小不能超过 10MB'
            }, status=status.HTTP_400_BAD_REQUEST)

        from django.conf import settings
        from datetime import timedelta
        import uuid
        import tempfile
        import os

        # 创建临时文件
        temp_dir = tempfile.mkdtemp()
        file_ext = os.path.splitext(image_file.name)[1]
        temp_file_path = os.path.join(temp_dir, f"medication_{uuid.uuid4().hex}{file_ext}")

        # 保存上传的图片到临时文件
        with open(temp_file_path, 'wb+') as destination:
            for chunk in image_file.chunks():
                destination.write(chunk)

        print(f"[小程序药单识别] 图片已保存到临时文件: {temp_file_path}")

        # 调用药单识别服务
        from .services import MedicationRecognitionService
        from .models import MedicationGroup, Medication

        service = MedicationRecognitionService()
        result = service.recognize_medication_image(temp_file_path)

        # 清理临时文件
        try:
            os.unlink(temp_file_path)
            os.rmdir(temp_dir)
        except:
            pass

        medications_data = result.get('medications', [])
        summary = result.get('summary', '')

        if not medications_data:
            return Response({
                'success': False,
                'error': '未能从图片中识别出药物信息'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 创建药单组
        from django.utils import timezone
        group_name = f"药单组 {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        medication_group = MedicationGroup.objects.create(
            user=request.user,
            name=group_name,
            ai_summary=summary,
            raw_result=result
        )

        # 保存原始图片
        if image_file:
            medication_group.source_image.save(
                f"medication_{uuid.uuid4().hex}{file_ext}",
                image_file,
                save=True
            )

        created_medications = []

        for med_data in medications_data:
            medicine_name = med_data.get('medicine_name', '').strip()
            dosage = med_data.get('dosage', '').strip()

            if not medicine_name:
                continue

            # 解析开始日期
            start_date_str = med_data.get('start_date')
            end_date_str = med_data.get('end_date')

            try:
                if start_date_str and start_date_str != 'null':
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                else:
                    start_date = timezone.now().date()
            except:
                start_date = timezone.now().date()

            try:
                if end_date_str and end_date_str != 'null':
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
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

        print(f"[小程序药单识别] ✓ 识别成功，创建了 {len(created_medications)} 个药单")

        return Response({
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
        print(f"[小程序药单识别] ✗ 识别失败: {str(e)}")
        traceback.print_exc()
        return Response({
            'success': False,
            'error': f'识别失败: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# 小程序健康日志API (症状日志 & 体征日志)
# ============================================================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def mp_symptom_logs(request):
    """
    小程序症状日志API

    GET: 获取症状日志列表
    POST: 创建新的症状日志
    """
    from .models import SymptomEntry

    if request.method == 'GET':
        queryset = SymptomEntry.objects.filter(user=request.user)

        # 支持日期范围筛选
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(entry_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(entry_date__lte=end_date)

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
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

        return Response({
            'success': True,
            'logs': logs,
            'count': len(logs)
        })

    elif request.method == 'POST':
        data = _get_request_data(request)

        symptom = data.get('symptom', '').strip()
        if not symptom:
            return Response({
                'success': False,
                'error': '症状名称不能为空'
            }, status=status.HTTP_400_BAD_REQUEST)

        entry_date = data.get('entry_date')
        if entry_date:
            entry_date = datetime.strptime(entry_date, '%Y-%m-%d').date()

        log = SymptomEntry.objects.create(
            user=request.user,
            entry_date=entry_date,
            symptom=symptom,
            severity=data.get('severity', 3),
            notes=data.get('notes', '').strip(),
        )

        return Response({
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
        }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def mp_symptom_log_detail(request, log_id):
    """
    小程序症状日志详情API

    GET: 获取单条症状日志详情
    PUT: 更新症状日志
    DELETE: 删除症状日志
    """
    from .models import SymptomEntry

    try:
        log = SymptomEntry.objects.get(id=log_id, user=request.user)
    except SymptomEntry.DoesNotExist:
        return Response({
            'success': False,
            'error': '症状日志不存在或无权访问'
        }, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response({
            'success': True,
            'log': {
                'id': log.id,
                'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                'symptom': log.symptom,
                'severity': log.severity,
                'severity_display': log.get_severity_display(),
                'notes': log.notes or '',
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })

    elif request.method == 'PUT':
        data = _get_request_data(request)

        if data.get('symptom'):
            log.symptom = data['symptom'].strip()
        if data.get('entry_date'):
            log.entry_date = datetime.strptime(data['entry_date'], '%Y-%m-%d').date()
        if data.get('severity') is not None:
            log.severity = data['severity']
        if data.get('notes') is not None:
            log.notes = data['notes'].strip()

        log.save()

        return Response({
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

    elif request.method == 'DELETE':
        log.delete()
        return Response({
            'success': True,
            'message': '症状日志已删除'
        })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def mp_vital_logs(request):
    """
    小程序体征日志API

    GET: 获取体征日志列表
    POST: 创建新的体征日志
    """
    from .models import VitalEntry

    if request.method == 'GET':
        queryset = VitalEntry.objects.filter(user=request.user)

        # 支持日期范围筛选
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(entry_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(entry_date__lte=end_date)

        # 支持体征类型筛选
        vital_type = request.query_params.get('vital_type')
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
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            })

        return Response({
            'success': True,
            'logs': logs,
            'count': len(logs)
        })

    elif request.method == 'POST':
        data = _get_request_data(request)

        vital_type = data.get('vital_type', '').strip()
        if not vital_type:
            return Response({
                'success': False,
                'error': '体征类型不能为空'
            }, status=status.HTTP_400_BAD_REQUEST)

        value = data.get('value', '').strip()
        if not value:
            return Response({
                'success': False,
                'error': '数值不能为空'
            }, status=status.HTTP_400_BAD_REQUEST)

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
        )

        return Response({
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
        }, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def mp_vital_log_detail(request, log_id):
    """
    小程序体征日志详情API

    GET: 获取单条体征日志详情
    PUT: 更新体征日志
    DELETE: 删除体征日志
    """
    from .models import VitalEntry

    try:
        log = VitalEntry.objects.get(id=log_id, user=request.user)
    except VitalEntry.DoesNotExist:
        return Response({
            'success': False,
            'error': '体征日志不存在或无权访问'
        }, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response({
            'success': True,
            'log': {
                'id': log.id,
                'entry_date': log.entry_date.strftime('%Y-%m-%d'),
                'vital_type': log.vital_type,
                'vital_type_display': log.get_vital_type_display(),
                'value': log.value,
                'unit': log.unit or '',
                'notes': log.notes or '',
                'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            }
        })

    elif request.method == 'PUT':
        data = _get_request_data(request)

        if data.get('entry_date'):
            log.entry_date = datetime.strptime(data['entry_date'], '%Y-%m-%d').date()
        if data.get('vital_type'):
            log.vital_type = data['vital_type']
        if data.get('value'):
            log.value = data['value']
        if data.get('unit') is not None:
            log.unit = data['unit'].strip()
        if data.get('notes') is not None:
            log.notes = data['notes'].strip()

        log.save()

        return Response({
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

    elif request.method == 'DELETE':
        log.delete()
        return Response({
            'success': True,
            'message': '体征日志已删除'
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def mp_vital_types(request):
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

    return Response({
        'success': True,
        'vital_types': vital_types
    })
