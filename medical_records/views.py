from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Avg
from datetime import datetime, timedelta
from django.utils import timezone
import json
import requests
from .models import HealthCheckup, HealthIndicator, HealthAdvice, SystemSettings, UserProfile
from .forms import HealthCheckupForm, HealthIndicatorForm, ManualIndicatorForm, HealthAdviceForm, SystemSettingsForm, CustomUserCreationForm, UserProfileForm


def register(request):
    """用户注册视图"""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # 自动登录新注册用户
            login(request, user)
            messages.success(request, f'欢迎 {user.first_name}！您已成功注册并登录。')
            return redirect('medical_records:dashboard')
        else:
            messages.error(request, '注册失败，请检查表单信息是否正确。')
    else:
        form = CustomUserCreationForm()

    return render(request, 'registration/register.html', {
        'form': form,
        'title': '用户注册 - 个人健康管理系统'
    })


@login_required
def dashboard(request):
    """首页仪表板 - 显示健康指标图表"""
    user = request.user

    # 获取用户最近的体检报告（侧边栏用）
    recent_checkups = HealthCheckup.objects.filter(user=user).order_by('-checkup_date')[:5]
    
    # 获取所有体检报告（用于我的体检报告卡片）
    all_checkups = HealthCheckup.objects.filter(user=user).order_by('-checkup_date')
    
    # 获取体检记录总数
    total_checkups = all_checkups.count()

    # 获取最近的异常指标（侧边栏用）
    abnormal_indicators = HealthIndicator.objects.filter(
        checkup__user=user,
        status='abnormal'
    ).select_related('checkup').order_by('-checkup__checkup_date')[:5]

    # 优化的图表数据获取
    def prepare_chart_data(indicator_types, limit=20):
        """准备图表数据，支持新的12种指标类型"""
        import re

        # 辅助函数：从字符串中提取数值
        def extract_numeric_value(value_str):
            """从字符串中提取第一个数值（整数或小数）"""
            if not value_str:
                return None
            # 匹配整数或小数（包括负数）
            match = re.search(r'-?\d+\.?\d*', str(value_str))
            if match:
                try:
                    return float(match.group())
                except ValueError:
                    return None
            return None

        # 初始化数据结构，按指标名称组织数据
        all_data = {}

        # 获取最近的数据点，按日期排序（增加到50条以确保包含所有历史数据）
        checkups = HealthCheckup.objects.filter(user=user).order_by('-checkup_date')[:limit]

        # 收集所有唯一的指标名称
        all_indicator_names = set()
        indicators_by_checkup = {}

        for checkup in checkups:
            indicators = HealthIndicator.objects.filter(checkup=checkup)
            indicators_by_checkup[checkup.id] = []

            for indicator in indicators:
                # 只要有value就包含，不过滤indicator_type，确保所有数据都能显示
                if indicator.value:
                    all_indicator_names.add(indicator.indicator_name)
                    indicators_by_checkup[checkup.id].append(indicator)

        # 为每个指标创建数据集
        for indicator_name in all_indicator_names:
            all_data[indicator_name] = []

        # 按时间正序处理数据
        for checkup in reversed(checkups):
            checkup_date = checkup.checkup_date.strftime('%Y-%m-%d')

            for indicator in indicators_by_checkup.get(checkup.id, []):
                # 提取数值用于排序和计算（保留原始value字符串用于显示）
                numeric_value = extract_numeric_value(indicator.value)

                # 保留所有数据，无论是否能提取数值
                all_data[indicator.indicator_name].append({
                    'date': checkup_date,
                    'value': numeric_value,  # 用于计算的数值
                    'value_display': str(indicator.value),  # 用于显示的原始值
                    'unit': indicator.unit or '',
                    'status': indicator.status,
                    'indicator_name': indicator.indicator_name,
                    'indicator_type': indicator.indicator_type
                })

        # 按新类型组织数据
        data = {
            'physical_exam': [],
            'blood_routine': [],
            'biochemistry': [],
            'liver_function': [],
            'kidney_function': [],
            'thyroid_function': [],
            'tumor_markers': [],
            'urine_exam': [],
            'blood_rheology': [],
            'eye_exam': [],
            'other_exam': []
        }

        # 将数据按新分类组织
        for indicator_name, values in all_data.items():
            if values:
                indicator_type = values[0].get('indicator_type', 'other_exam')
                if indicator_type in data:
                    data[indicator_type].extend(values)
                else:
                    data['other_exam'].extend(values)

        # 添加原始数据以便JavaScript灵活处理
        data['raw_data'] = [
            {
                'indicator_name': name,
                'values': [item['value'] for item in values],  # 用于计算的数值
                'values_display': [item['value_display'] for item in values],  # 用于显示的原始值
                'dates': [item['date'] for item in values],
                'units': values[0]['unit'] if values else '',
                'type': values[0]['indicator_type'] if values else 'other_exam',
                'data': values
            }
            for name, values in all_data.items() if values
        ]

        return data

    # 获取数据库中实际存在的指标类型
    existing_indicator_types = HealthIndicator.objects.filter(
        checkup__user=user
    ).values_list('indicator_type', flat=True).distinct()

    # 生成动态的指标分类映射
    indicator_type_mapping = {}
    indicator_type_list = []  # 新增：按顺序的指标类型列表
    for indicator_type, display_name in HealthIndicator.INDICATOR_TYPES:
        if indicator_type in existing_indicator_types:
            # 直接使用indicator_type作为tab_id，不再使用hardcoded映射
            indicator_type_mapping[indicator_type] = {
                'type': indicator_type,
                'display_name': display_name
            }
            # 添加到列表中，保持顺序
            indicator_type_list.append({
                'type': indicator_type,
                'display_name': display_name
            })

    # 获取各类指标数据（增加到50条记录以确保包含所有历史数据）
    chart_data = prepare_chart_data(list(existing_indicator_types), limit=50)

    # 健康统计
    total_checkups = HealthCheckup.objects.filter(user=user).count()
    latest_checkup = HealthCheckup.objects.filter(user=user).order_by('-checkup_date').first()

    # 计算健康评分
    health_score = 85  # 默认分数
    if latest_checkup:
        total_indicators = HealthIndicator.objects.filter(checkup=latest_checkup).count()
        normal_indicators = HealthIndicator.objects.filter(
            checkup=latest_checkup,
            status='normal'
        ).count()
        if total_indicators > 0:
            health_score = int((normal_indicators / total_indicators) * 100)

    context = {
        # 侧边栏数据
        'recent_checkups': recent_checkups,
        'abnormal_indicators': abnormal_indicators,

        # 图表数据
        'chart_data': json.dumps(chart_data),

        # 动态指标分类映射
        'indicator_type_mapping': json.dumps(indicator_type_mapping),
        'indicator_type_list': json.dumps(indicator_type_list),  # 新增：指标类型列表

        # 统计数据
        'total_checkups': total_checkups,
        'health_score': health_score,
        'latest_checkup': latest_checkup,

        # 关键指标概览
        'key_indicators': _get_key_indicators_summary(user),

        # 我的体检报告卡片数据
        'all_checkups': list(all_checkups[:10]),  # 最多传递10条记录用于显示
    }

    return render(request, 'medical_records/dashboard.html', context)


def _get_key_indicators_summary(user):
    """获取关键指标概览"""
    latest_checkup = HealthCheckup.objects.filter(user=user).order_by('-checkup_date').first()
    if not latest_checkup:
        return []

    key_indicators = []
    important_names = ['血压', '心率', '体重', '血糖', '胆固醇']

    for indicator_name in important_names:
        indicator = HealthIndicator.objects.filter(
            checkup=latest_checkup,
            indicator_name__contains=indicator_name
        ).first()

        if indicator:
            key_indicators.append({
                'name': indicator.indicator_name,
                'value': indicator.value,
                'unit': indicator.unit,
                'status': indicator.status,
                'type': indicator.indicator_type
            })

    return key_indicators[:4]  # 只返回前4个重要的指标


@login_required
def upload_report(request):
    """上传体检报告"""
    if request.method == 'POST':
        form = HealthCheckupForm(request.POST, request.FILES)
        if form.is_valid():
            checkup = form.save(commit=False)
            checkup.user = request.user
            checkup.save()

            # 保存健康指标
            indicators_data = [
                ('blood_pressure', '血压', request.POST.get('blood_pressure')),
                ('heart_rate', '心率', request.POST.get('heart_rate')),
                ('weight', '体重', request.POST.get('weight')),
                ('height', '身高', request.POST.get('height')),
                ('blood_sugar', '血糖', request.POST.get('blood_sugar')),
                ('cholesterol', '胆固醇', request.POST.get('cholesterol')),
            ]

            for indicator_type, indicator_name, value in indicators_data:
                try:
                    if value:
                        # 简单的状态判断逻辑
                        status = 'normal'
                        if indicator_type == 'blood_pressure':
                            try:
                                systolic, diastolic = map(int, value.split('/'))
                                if systolic > 140 or diastolic > 90:
                                    status = 'abnormal'
                                elif systolic > 130 or diastolic > 85:
                                    status = 'attention'
                            except:
                                pass
                        elif indicator_type == 'heart_rate':
                            try:
                                hr = int(value)
                                if hr > 100 or hr < 60:
                                    status = 'attention'
                            except:
                                pass
                        elif indicator_type == 'weight':
                            # 体重状态判断可以基于身高计算BMI
                            pass
                        elif indicator_type == 'blood_sugar':
                            try:
                                bs = float(value)
                                if bs > 7.0:
                                    status = 'abnormal'
                                elif bs > 6.1:
                                    status = 'attention'
                            except:
                                pass

                        # 设置单位
                        units = {
                            'blood_pressure': 'mmHg',
                            'heart_rate': 'bpm',
                            'weight': 'kg',
                            'height': 'cm',
                            'blood_sugar': 'mmol/L',
                            'cholesterol': 'mmol/L',
                        }

                        HealthIndicator.objects.create(
                            checkup=checkup,
                            indicator_type=indicator_type,
                            indicator_name=indicator_name,
                            value=value,
                            unit=units.get(indicator_type, ''),
                            status=status
                        )
                except Exception as e:
                    # 单个指标保存失败不影响其他指标
                    print(f"保存指标失败: {indicator_name} - 错误: {str(e)}")
                    continue

            messages.success(request, '体检报告上传成功！')
            return redirect('medical_records:dashboard')
    else:
        form = HealthCheckupForm()

    # 获取系统设置用于服务状态检查
    ocr_service_url = SystemSettings.get_setting('mineru_api_url', 'http://localhost:8000')
    ai_service_url = SystemSettings.get_setting('llm_api_url', 'http://172.25.48.1:1234')

    context = {
        'form': form,
        'ocr_service_url': ocr_service_url,
        'ai_service_url': ai_service_url,
    }

    return render(request, 'medical_records/upload_report_new.html', context)


@login_required
def ai_health_advice(request):
    """AI健康建议页面"""
    if request.method == 'POST':
        form = HealthAdviceForm(request.user, request.POST)
        if form.is_valid():
            try:
                advice = form.save(commit=False)
                advice.user = request.user

                # 处理对话模式
                conversation_mode = request.POST.get('conversation_mode', 'new_conversation')
                conversation = None

                if conversation_mode == 'continue_conversation':
                    # 继续现有对话
                    conversation_id = request.POST.get('conversation_id')
                    if conversation_id:
                        from .models import Conversation
                        try:
                            conversation = Conversation.objects.get(id=conversation_id, user=request.user, is_active=True)
                        except Conversation.DoesNotExist:
                            return JsonResponse({
                                'success': False,
                                'error': '所选对话不存在或已删除'
                            })
                    else:
                        return JsonResponse({
                            'success': False,
                            'error': '请选择要继续的对话'
                        })
                else:
                    # 创建新对话
                    from .models import Conversation
                    # 使用用户问题的前50个字符作为对话标题
                    question_text = advice.question[:50]
                    if len(advice.question) > 50:
                        question_text += '...'
                    conversation = Conversation.create_new_conversation(request.user, f"健康咨询: {question_text}")

                advice.conversation = conversation

                # 获取报告模式
                report_mode = request.POST.get('report_mode', 'select_reports')

                # 获取用户选择的体检报告
                selected_reports = form.cleaned_data.get('selected_reports')

                # 如果选择"不使用任何报告"，则将selected_reports设为None
                if report_mode == 'no_reports':
                    selected_reports = None
                else:
                    # 如果选择"选择特定报告"，验证用户必须选择至少一个报告
                    if not selected_reports or len(selected_reports) == 0:
                        error_msg = "请选择至少一份体检报告，或选择'不使用任何报告'选项"
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'success': False,
                                'error': error_msg,
                                'question': advice.question
                            })
                        messages.error(request, error_msg)
                        return redirect('medical_records:ai_health_advice')

                # 生成AI响应，传入选择的报告和对话上下文
                question = advice.question
                answer, prompt_sent, conversation_context = generate_ai_advice(question, request.user, selected_reports, conversation)

                # 如果AI生成失败，返回错误信息
                if not answer:
                    error_msg = "AI医生服务暂时不可用，请稍后再试"
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': False,
                            'error': error_msg,
                            'prompt': prompt_sent,
                            'question': question
                        })
                    messages.error(request, error_msg)
                    return redirect('medical_records:ai_health_advice')

                advice.answer = answer
                advice.prompt_sent = prompt_sent
                advice.conversation_context = json.dumps(conversation_context, ensure_ascii=False) if conversation_context else None
                advice.save()

                # 如果是AJAX请求，返回JSON响应
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'answer': answer,
                        'prompt': prompt_sent,
                        'question': question,
                        'conversation_context': conversation_context,
                        'created_at': advice.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    })

                messages.success(request, 'AI健康建议已生成！')
                return redirect('medical_records:ai_health_advice')

            except Exception as e:
                # 捕获所有异常并记录详细错误
                error_msg = f"处理请求时发生错误: {str(e)}"
                print(f"AI健康建议生成错误: {error_msg}")

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'error': error_msg,
                        'question': request.POST.get('question', ''),
                        'technical_error': str(e)
                    })

                messages.error(request, error_msg)
                return redirect('medical_records:ai_health_advice')
        else:
            # 如果是AJAX请求，返回表单错误
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': '表单验证失败',
                    'form_errors': dict(form.errors)
                })
    else:
        form = HealthAdviceForm(request.user)

    # 获取用户的历史咨询记录（按对话聚合显示）
    user_advices = []
    from .models import Conversation
    
    # 获取用户的活跃对话
    all_conversations = Conversation.get_user_conversations(request.user)
    
    for conversation in all_conversations:
        message_count = conversation.get_message_count()
        # 只显示有消息的对话（过滤掉空对话，防止显示无消息的对话记录）
        if message_count > 0:
            latest_message = conversation.get_latest_message()
            
            user_advices.append({
                'id': conversation.id,
                'conversation_id': conversation.id,
                'title': conversation.title,
                'message_count': message_count,
                'question': latest_message.question if latest_message else '',
                'latest_question': latest_message.question if latest_message else '',
                'created_at': latest_message.created_at if latest_message else conversation.created_at,
                'updated_at': latest_message.created_at if latest_message else conversation.updated_at,
                'is_conversation': True,
            })
    
    # 如果没有对话，显示旧格式的记录作为备用
    if not user_advices:
        old_advices = HealthAdvice.objects.filter(
            user=request.user, 
            conversation__isnull=True
        ).order_by('-created_at')[:10]
        
        for advice in old_advices:
            user_advices.append({
                'id': advice.id,
                'conversation_id': None,
                'title': advice.question[:30] + '...' if len(advice.question) > 30 else advice.question,
                'message_count': 1,
                'latest_question': advice.question,  # 添加latest_question字段
                'created_at': advice.created_at,
                'updated_at': advice.created_at,
                'question': advice.question,
                'answer': advice.answer,
                'is_conversation': False,
            })

    # 为表单中的报告添加额外信息
    reports_with_info = []
    for report in form.fields['selected_reports'].queryset:
        # 使用HealthIndicator模型的反向查询
        from medical_records.models import HealthIndicator
        reports_with_info.append({
            'report': report,
            'has_abnormal': HealthIndicator.objects.filter(checkup=report, status='abnormal').exists(),
            'has_attention': HealthIndicator.objects.filter(checkup=report, status='attention').exists(),
        })

    context = {
        'form': form,
        'user_advices': user_advices,
        'reports_with_info': reports_with_info,
    }

    return render(request, 'medical_records/ai_advice.html', context)


@login_required
def get_advice_detail(request, advice_id):
    """获取详细建议内容"""
    advice = get_object_or_404(HealthAdvice, id=advice_id, user=request.user)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'question': advice.question,
            'answer': advice.answer,
            'prompt': advice.prompt_sent,
            'created_at': advice.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })

    return redirect('medical_records:ai_health_advice')


def get_user_health_data(user):
    """获取用户的完整健康数据，包括历史趋势"""
    # 获取用户的所有体检报告
    checkups = HealthCheckup.objects.filter(user=user).order_by('-checkup_date')

    if not checkups:
        return None

    health_data = {
        'user_info': {
            'age': (datetime.now().date() - user.date_of_birth).days // 365 if hasattr(user, 'date_of_birth') and user.date_of_birth else None,
            'gender': getattr(user, 'gender', None),
        },
        'checkups': [],
        'summary': {
            'total_checkups': checkups.count(),
            'date_range': {
                'latest': checkups.first().checkup_date.strftime('%Y-%m-%d') if checkups.first() else None,
                'earliest': checkups.last().checkup_date.strftime('%Y-%m-%d') if checkups.last() else None,
            }
        },
        'trends': {}
    }

    # 为每次体检添加详细信息
    for checkup in checkups:
        indicators = HealthIndicator.objects.filter(checkup=checkup)
        checkup_data = {
            'date': checkup.checkup_date.strftime('%Y-%m-%d'),
            'hospital': checkup.hospital,
            'indicators': {}
        }

        # 按类型分组指标，只保留关键字段以节省token
        for indicator in indicators:
            indicator_type = indicator.indicator_type
            if indicator_type not in checkup_data['indicators']:
                checkup_data['indicators'][indicator_type] = []

            # 只包含必要的字段，标记异常指标
            indicator_data = {
                'name': indicator.indicator_name,
                'value': indicator.value,
                'unit': indicator.unit
            }

            # 只有异常指标才添加参考范围和异常标记
            if indicator.status == 'abnormal':
                indicator_data['reference'] = indicator.reference_range
                indicator_data['abnormal'] = True

            checkup_data['indicators'][indicator_type].append(indicator_data)

        health_data['checkups'].append(checkup_data)

    # 分析关键指标趋势
    key_indicators = ['血压', '心率', '血糖', '体重指数', '总胆固醇', '甘油三酯']

    for indicator_name in key_indicators:
        values = []
        dates = []

        for checkup in checkups:
            indicators = HealthIndicator.objects.filter(
                checkup=checkup,
                indicator_name__contains=indicator_name
            )
            for indicator in indicators:
                try:
                    # 处理数值，特别是血压格式 "120/80"
                    if '/' in str(indicator.value):
                        # 血压取收缩压
                        value = float(str(indicator.value).split('/')[0])
                    else:
                        value = float(str(indicator.value))

                    values.append(value)
                    dates.append(checkup.checkup_date.strftime('%Y-%m-%d'))
                except (ValueError, TypeError):
                    continue

        if values:
            health_data['trends'][indicator_name] = {
                'values': values,
                'dates': dates,
                'latest': values[0],
                'earliest': values[-1] if len(values) > 1 else values[0],
                'trend': 'stable'  # 可以进一步计算趋势
            }

            # 计算简单趋势
            if len(values) >= 2:
                if values[0] > values[-1] * 1.1:
                    health_data['trends'][indicator_name]['trend'] = 'increasing'
                elif values[0] < values[-1] * 0.9:
                    health_data['trends'][indicator_name]['trend'] = 'decreasing'

    return health_data


def get_selected_reports_health_data(user, selected_reports):
    """获取用户选择的体检报告的健康数据"""
    # 检查selected_reports是否为空或长度为0
    if not selected_reports or len(selected_reports) == 0:
        return None

    # 转换为查询集并排序
    checkups = HealthCheckup.objects.filter(
        id__in=[report.id for report in selected_reports],
        user=user
    ).order_by('-checkup_date')

    health_data = {
        'user_info': {
            'age': (datetime.now().date() - user.date_of_birth).days // 365 if hasattr(user, 'date_of_birth') and user.date_of_birth else None,
            'gender': getattr(user, 'gender', None),
        },
        'checkups': [],
        'summary': {
            'total_checkups': checkups.count(),
            'date_range': {
                'latest': checkups.first().checkup_date.strftime('%Y-%m-%d') if checkups.first() else None,
                'earliest': checkups.last().checkup_date.strftime('%Y-%m-%d') if checkups.last() else None,
            },
            'selected_reports': True,  # 标记这是基于选择报告的数据
        },
        'trends': {}
    }

    # 为每次体检添加详细信息
    for checkup in checkups:
        indicators = HealthIndicator.objects.filter(checkup=checkup)
        checkup_data = {
            'date': checkup.checkup_date.strftime('%Y-%m-%d'),
            'hospital': checkup.hospital,
            'indicators': {}
        }

        # 按类型分组指标，只保留关键字段以节省token
        for indicator in indicators:
            indicator_type = indicator.indicator_type
            if indicator_type not in checkup_data['indicators']:
                checkup_data['indicators'][indicator_type] = []

            # 只包含必要的字段，标记异常指标
            indicator_data = {
                'name': indicator.indicator_name,
                'value': indicator.value,
                'unit': indicator.unit
            }

            # 只有异常指标才添加参考范围和异常标记
            if indicator.status == 'abnormal':
                indicator_data['reference'] = indicator.reference_range
                indicator_data['abnormal'] = True

            checkup_data['indicators'][indicator_type].append(indicator_data)

        health_data['checkups'].append(checkup_data)

    # 分析关键指标趋势（如果有多份报告）
    if checkups.count() > 1:
        key_indicators = ['血压', '心率', '血糖', '体重指数', '总胆固醇', '甘油三酯']

        for indicator_name in key_indicators:
            values = []
            dates = []

            for checkup in checkups:
                indicators = HealthIndicator.objects.filter(
                    checkup=checkup,
                    indicator_name__contains=indicator_name
                )
                for indicator in indicators:
                    try:
                        # 处理数值，特别是血压格式 "120/80"
                        if '/' in str(indicator.value):
                            # 血压取收缩压
                            value = float(str(indicator.value).split('/')[0])
                        else:
                            value = float(str(indicator.value))

                        values.append(value)
                        dates.append(checkup.checkup_date.strftime('%Y-%m-%d'))
                    except (ValueError, TypeError):
                        continue

            if values:
                health_data['trends'][indicator_name] = {
                    'values': values,
                    'dates': dates,
                    'latest': values[0],
                    'earliest': values[-1] if len(values) > 1 else values[0],
                    'trend': 'stable'  # 可以进一步计算趋势
                }

                # 计算简单趋势
                if len(values) >= 2:
                    if values[0] > values[-1] * 1.1:
                        health_data['trends'][indicator_name]['trend'] = 'increasing'
                    elif values[0] < values[-1] * 0.9:
                        health_data['trends'][indicator_name]['trend'] = 'decreasing'

    return health_data


def get_conversation_context(user, conversation=None, max_conversations=50):  # 增加到50次对话
    """获取用户最近的对话上下文"""
    if conversation:
        # 获取特定对话的上下文
        recent_advices = HealthAdvice.get_conversation_messages(conversation.id)
    else:
        # 获取用户的所有对话上下文（包括没有关联对话的旧数据）
        recent_advices = HealthAdvice.objects.filter(
            user=user
        ).order_by('-created_at')[:max_conversations]

    context = []
    for advice in recent_advices:  # 对于特定对话已经是按时间正序
        if advice.question and advice.answer:
            # 截断过长的回答以节省token
            answer_preview = advice.answer[:200] + "..." if len(advice.answer) > 200 else advice.answer
            context.append({
                'question': advice.question,
                'answer': answer_preview,  # 限制回答长度
                'time': advice.created_at.strftime('%m-%d %H:%M'),  # 简化时间格式
                'created_at': advice.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })

    return context


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
                    status = indicator.get('status', '')

                    # 基础格式：指标名称：数值 单位
                    line = f"    {name}：{value}"
                    if unit:
                        line += f" {unit}"

                    # 添加状态标记
                    if status == 'abnormal':
                        line += " ⚠️异常"
                    elif status == 'attention':
                        line += " ⚡关注"

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


def call_ai_doctor_api(question, health_data, user, conversation_context=None):
    """调用AI医生API"""
    try:
        # 获取AI医生设置
        provider = SystemSettings.get_setting('ai_doctor_provider', 'openai')
        api_url = SystemSettings.get_setting('ai_doctor_api_url')
        api_key = SystemSettings.get_setting('ai_doctor_api_key')
        model_name = SystemSettings.get_setting('ai_doctor_model_name')
        # 使用统一的AI模型超时配置
        timeout = int(SystemSettings.get_setting('ai_model_timeout', '300'))
        # 使用AI医生的max_tokens配置
        max_tokens = int(SystemSettings.get_setting('ai_doctor_max_tokens', '4000'))

        # 根据提供商选择不同的调用方式
        if provider == 'gemini':
            # 使用 Gemini API
            from .services import call_gemini_api

            if not model_name:
                return None, "Gemini模型名称未配置"

            # 构建 prompt
            prompt_parts = []

            # 添加个人信息
            try:
                user_profile = user.userprofile
                if user_profile.birth_date or user_profile.gender:
                    prompt_parts.append("个人信息：")
                    prompt_parts.append(f"性别：{user_profile.get_gender_display()}")
                    if user_profile.age:
                        prompt_parts.append(f"年龄：{user_profile.age}岁")
            except:
                pass

            # 添加对话上下文
            if conversation_context:
                prompt_parts.append("\n对话历史：")
                conversation_history_text = format_conversation_history(conversation_context)
                prompt_parts.append(conversation_history_text)

            # 添加健康数据
            if health_data:
                prompt_parts.append("\n健康数据：")
                
                health_data_text = format_health_data_for_prompt(health_data)
                prompt_parts.append(health_data_text)

            # 添加问题
            prompt_parts.append(f"\n当前问题：{question}")

            # 组合 prompt
            full_prompt = "\n".join(prompt_parts)

            # 系统消息
            system_message = """你是一位专业的AI医生助手，请基于用户的健康数据和问题提供专业建议。

注意事项：
1. 你的建议仅供参考，不能替代专业医生的诊断
2. 对于异常指标，请给出可能的原因和建议
3. 建议用户定期体检，遵医嘱进行复查
4. 强调本建议仅供参考，具体诊疗请咨询专业医生"""

            return call_gemini_api(full_prompt, system_message, timeout), None

        # 使用 OpenAI 兼容格式
        if not api_url or not model_name:
            return None, "AI医生API未配置"

        # 构建AI医生prompt
        prompt_parts = [
            "你是一位专业的AI医生助手，请基于用户的健康数据和问题提供专业建议。",
            f"\n当前问题：{question}"
        ]

        # 添加个人信息
        try:
            user_profile = user.userprofile
            if user_profile.birth_date or user_profile.gender:
                prompt_parts.append("\n个人信息：")
                prompt_parts.append(f"性别：{user_profile.get_gender_display()}")
                if user_profile.age:
                    prompt_parts.append(f"年龄：{user_profile.age}岁")
        except:
            # 如果用户信息不存在，跳过
            pass

        # 添加对话上下文（简化格式以节省token）
        if conversation_context:
            prompt_parts.append("\n对话历史：")
            for i, ctx in enumerate(conversation_context, 1):
                prompt_parts.append(f"{ctx['time']} 问：{ctx['question']}")
                prompt_parts.append(f"答：{ctx['answer']}")

        if health_data is None:
            # 用户选择不使用任何健康数据
            prompt_parts.extend([
                "\n注意：用户选择不提供任何体检报告数据，请仅基于问题提供一般性健康建议。",
                "\n请基于以上问题：",
                "1. 结合对话历史，理解用户的关注点",
                "2. 提供一般性的健康建议和知识",
                "3. 针对用户的具体问题给出专业建议",
                "4. 建议何时需要就医或专业咨询",
                "5. 给出实用的生活方式和预防措施",
                "\n请用中文回答，语气专业但平易近人，建议要具体可行。注意这仅供参考，不能替代面诊。"
            ])
        else:
            # 有健康数据时，使用简化格式
            health_data_text = format_health_data_for_prompt(health_data)
            prompt_parts.extend([
                f"\n用户健康数据：\n{health_data_text}",
                "\n请基于以上信息：",
                "1. 结合对话历史，理解用户的连续关注点",
                "2. 分析用户的健康状况和趋势",
                "3. 针对用户的具体问题提供专业建议",
                "4. 注意观察指标的历史变化趋势",
                "5. 给出实用的生活方式和医疗建议",
                "6. 如有异常指标，请特别说明并建议应对措施",
                "\n请用中文回答，语气专业但平易近人，建议要具体可行。注意这仅供参考，不能替代面诊。"
            ])

        prompt = "".join(prompt_parts)

        # 调用AI医生API
        headers = {
            'Content-Type': 'application/json'
        }

        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        data = {
            'model': model_name,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': max_tokens,  # 使用系统配置的max_tokens
            'temperature': 0.3
        }

        print(f"AI医生API调用，超时设置: {timeout}秒")

        # AI医生API调用直接使用配置的完整地址
        response = requests.post(
            api_url,
            headers=headers,
            json=data,
            timeout=timeout
        )

        if response.status_code == 200:
            result = response.json()
            answer = result['choices'][0]['message']['content']
            print(f"AI医生API调用成功，回答长度: {len(answer)} 字符")
            return answer, None
        else:
            return None, f"AI医生API调用失败: {response.status_code} - {response.text}"

    except requests.exceptions.Timeout:
        return None, "AI医生API请求超时，请稍后再试"
    except requests.exceptions.RequestException as e:
        return None, f"AI医生API请求错误: {str(e)}"
    except Exception as e:
        return None, f"AI医生处理错误: {str(e)}"


def generate_ai_advice(question, user, selected_reports=None, conversation=None):
    """生成AI健康建议，返回answer、prompt和conversation_context"""
    # 检查是否配置了AI医生API
    api_url = SystemSettings.get_setting('ai_doctor_api_url')
    model_name = SystemSettings.get_setting('ai_doctor_model_name')

    prompt_sent = ""
    conversation_context = None

    if api_url and model_name:
        # 使用AI医生API
        if selected_reports is None:
            # 用户选择不使用任何报告
            health_data = None
            data_source_note = "用户选择不使用任何体检报告，仅基于问题提供建议"
        elif selected_reports and len(selected_reports) > 0:
            # 用户选择了特定报告，只获取这些报告的数据
            health_data = get_selected_reports_health_data(user, selected_reports)
            data_source_note = "基于用户选择的特定体检报告进行分析"
        else:
            # 没有选择任何报告的情况（理论上不应该发生）
            health_data = None
            data_source_note = "未选择任何报告"

        if selected_reports is None:
            # 用户选择不使用任何报告，仅基于问题提供一般性建议
            conversation_context = get_conversation_context(user, conversation)
            answer, error = call_ai_doctor_api(question, None, user, conversation_context)

            # 构建用于显示的prompt
            conversation_history_text = format_conversation_history(conversation_context)
            prompt_sent = f"""用户问题：{question}

数据来源：{data_source_note}

对话历史：
{conversation_history_text}

注意：用户选择不使用任何体检报告数据进行分析。"""

            if answer:
                return answer, prompt_sent, conversation_context
            else:
                # API调用失败，返回错误信息加上备用建议
                fallback_answer = f"""很抱歉，AI医生服务暂时不可用。错误信息：{error}

不过，基于您的问题，我可以提供一些一般性健康建议：

1. **定期体检**：建议每年进行一次全面体检，及时了解身体状况
2. **健康生活方式**：保持均衡饮食、规律运动、充足睡眠
3. **症状关注**：如出现身体不适，及时就医
4. **遵医嘱**：按医生建议进行治疗和复查

如果您有具体的健康问题，建议咨询相关专业医生获得准确的诊断和治疗方案。

请稍后再试或联系系统管理员配置AI医生服务。"""
                return fallback_answer, prompt_sent, conversation_context

        elif health_data and health_data['checkups']:
            # 有健康数据时进行分析
            conversation_context = get_conversation_context(user, conversation)

            # 调用AI医生API
            answer, error = call_ai_doctor_api(question, health_data, user, conversation_context)

            # 构建用于显示的prompt（使用简化格式）
            health_data_display = format_health_data_for_prompt(health_data)
            conversation_history_text = format_conversation_history(conversation_context)
            prompt_sent = f"""用户问题：{question}

数据来源：{data_source_note}

对话历史：
{conversation_history_text}

用户健康数据：
{health_data_display}"""

            if answer:
                return answer, prompt_sent, conversation_context
            else:
                # API调用失败，返回错误信息加上备用建议
                fallback_answer = f"""很抱歉，AI医生服务暂时不可用。错误信息：{error}

不过，基于您的问题，我可以提供一些一般性建议：

1. **定期体检**：建议每年进行一次全面体检，及时了解身体状况
2. **健康生活方式**：保持均衡饮食、规律运动、充足睡眠
3. **症状关注**：如出现身体不适，及时就医
4. **遵医嘱**：按医生建议进行治疗和复查

如果您有具体的健康问题，建议咨询相关专业医生获得准确的诊断和治疗方案。

请稍后再试或联系系统管理员配置AI医生服务。"""
                return fallback_answer, prompt_sent, conversation_context
        else:
            no_data_prompt = f"""用户问题：{question}

注意：用户暂无健康数据记录。"""
            return """感谢您的健康咨询！

目前您的健康数据还在收集中。为了给您提供更精准的建议，建议您：

1. **完善健康数据**：上传您的体检报告，系统会自动分析各项指标
2. **定期记录**：持续记录健康数据，帮助分析健康趋势
3. **一般性建议**：
   - 保持均衡饮食，多吃蔬菜水果
   - 规律运动，每周至少150分钟中等强度运动
   - 保证充足睡眠，每天7-9小时
   - 定期体检，及早发现健康问题

如果您有具体的健康问题，建议咨询相关专业医生。""", no_data_prompt, conversation_context

    # 未配置AI医生API，使用原来的模拟响应
    mock_prompt = f"""用户问题：{question}

注意：使用模拟响应模式（AI医生API未配置）。"""

    question_lower = question.lower()

    if '血压' in question_lower:
        return """关于血压的建议：

1. **饮食调整**：
   - 减少钠盐摄入，每日不超过6克
   - 增加富含钾的食物，如香蕉、橙子、菠菜等
   - 控制胆固醇和饱和脂肪的摄入

2. **生活方式**：
   - 保持规律运动，每周至少150分钟中等强度运动
   - 保持健康体重
   - 限制酒精摄入
   - 戒烟

3. **监测建议**：
   - 定期监测血压，做好记录
   - 遵医嘱服药，不要随意停药
   - 定期复查

请咨询您的医生获得个性化的治疗方案。""", mock_prompt, []

    elif '血糖' in question_lower or '糖尿病' in question_lower:
        return """关于血糖管理的建议：

1. **饮食控制**：
   - 控制碳水化合物摄入量
   - 选择低GI（血糖生成指数）食物
   - 少量多餐，避免暴饮暴食
   - 增加膳食纤维摄入

2. **运动管理**：
   - 规律有氧运动，如快走、游泳等
   - 餐后适度运动有助于控制血糖
   - 避免空腹剧烈运动

3. **监测提醒**：
   - 定期监测血糖水平
   - 记录饮食、运动与血糖的关系
   - 遵医嘱用药或胰岛素治疗

建议您咨询内分泌科医生获得专业指导。""", mock_prompt, []

    else:
        return """感谢您的健康咨询！

基于您的健康数据，我为您提供建议：

1. **定期体检**：建议每年进行一次全面体检，及时了解身体状况
2. **健康生活方式**：保持均衡饮食、规律运动、充足睡眠
3. **症状关注**：如出现身体不适，及时就医
4. **遵医嘱**：按医生建议进行治疗和复查

如果您有具体的健康问题，建议咨询相关专业医生。获得准确的诊断和治疗方案。""", mock_prompt, []


@login_required
def checkup_detail(request, checkup_id):
    """体检报告详情"""
    checkup = get_object_or_404(HealthCheckup, id=checkup_id, user=request.user)
    indicators = HealthIndicator.objects.filter(checkup=checkup)

    # 计算指标状态统计
    normal_count = indicators.filter(status='normal').count()
    abnormal_count = indicators.filter(status='abnormal').count()
    attention_count = indicators.filter(status='attention').count()

    context = {
        'checkup': checkup,
        'indicators': indicators,
        'normal_count': normal_count,
        'abnormal_count': abnormal_count,
        'attention_count': attention_count,
    }

    return render(request, 'medical_records/checkup_detail.html', context)


@login_required
def data_integration(request):
    """数据整合页面 - 选择多份报告进行AI智能整合"""
    # 获取用户的所有体检报告，按日期降序排列
    checkups = HealthCheckup.objects.filter(
        user=request.user
    ).prefetch_related('healthindicator_set').order_by('-checkup_date')

    context = {
        'checkups': checkups,
        'page_title': '智能数据整合',
    }

    return render(request, 'medical_records/data_integration.html', context)


@login_required
def system_settings(request):
    """系统设置页面"""
    if request.method == 'POST':
        form = SystemSettingsForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '设置已保存成功！')
            return redirect('medical_records:system_settings')
    else:
        form = SystemSettingsForm()

    # 获取当前设置值用于显示
    current_settings = {
        'mineru_api_url': SystemSettings.get_setting('mineru_api_url', 'http://localhost:8000'),
        'llm_api_url': SystemSettings.get_setting('llm_api_url', 'https://api.siliconflow.cn/v1/chat/completions'),
        'llm_api_key': SystemSettings.get_setting('llm_api_key', 'sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa'),
        'llm_model_name': SystemSettings.get_setting('llm_model_name', 'deepseek-ai/DeepSeek-V3.2'),
        'llm_timeout': SystemSettings.get_setting('llm_timeout', '3600'),
        'ocr_timeout': SystemSettings.get_setting('ocr_timeout', '3600'),
        'llm_provider': SystemSettings.get_setting('llm_provider', 'openai'),
        'ai_doctor_api_url': SystemSettings.get_setting('ai_doctor_api_url', 'https://api.siliconflow.cn/v1/chat/completions'),
        'ai_doctor_api_key': SystemSettings.get_setting('ai_doctor_api_key', 'sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa'),
        'ai_doctor_model_name': SystemSettings.get_setting('ai_doctor_model_name', 'deepseek-ai/DeepSeek-V3.2'),
        'ai_doctor_timeout': SystemSettings.get_setting('ai_doctor_timeout', '3600'),
        'ai_doctor_provider': SystemSettings.get_setting('ai_doctor_provider', 'openai'),
        # Gemini设置
        'gemini_api_key': SystemSettings.get_setting('gemini_api_key', ''),
        'gemini_model_name': SystemSettings.get_setting('gemini_model_name', 'gemini-3.0-flash'),
        'gemini_timeout': SystemSettings.get_setting('gemini_timeout', '300'),
        # 多模态模型设置
        'vl_model_provider': SystemSettings.get_setting('vl_model_provider', 'openai'),
        'vl_model_api_url': SystemSettings.get_setting('vl_model_api_url', 'https://api.siliconflow.cn/v1/chat/completions'),
        'vl_model_api_key': SystemSettings.get_setting('vl_model_api_key', 'sk-zgjlsnpadljnnoustkxwfpmugagfsigzdthtwfgvcptblbxa'),
        'vl_model_name': SystemSettings.get_setting('vl_model_name', 'zai-org/GLM-4.6V'),
        'vl_model_timeout': SystemSettings.get_setting('vl_model_timeout', '300'),
        'vl_model_max_tokens': SystemSettings.get_setting('vl_model_max_tokens', '4000'),
        'default_workflow': SystemSettings.get_setting('default_workflow', 'ocr_llm'),
    }

    context = {
        'form': form,
        'current_settings': current_settings,
        'page_title': '系统设置',
    }

    return render(request, 'medical_records/system_settings.html', context)


@login_required
def check_services_status(request):
    """检查OCR和AI服务状态"""
    import requests

    # 获取系统设置中的服务URL
    ocr_service_url = SystemSettings.get_setting('mineru_api_url', 'http://localhost:8000')
    ai_service_url = SystemSettings.get_setting('llm_api_url', 'http://172.25.48.1:1234')

    # 详细调试信息
    all_settings = SystemSettings.objects.all()
    print(f"[DEBUG] 数据库中所有系统设置:")
    for setting in all_settings:
        print(f"  {setting.key}: {setting.value}")
    print(f"[DEBUG] 最终OCR服务地址: {ocr_service_url}")
    print(f"[DEBUG] 最终AI服务地址: {ai_service_url}")

    result = {
        'ocr_status': 'offline',
        'ocr_error': None,
        'ai_status': 'offline',
        'ai_error': None
    }

    # 检查OCR服务
    try:
        ocr_check_url = f"{ocr_service_url.rstrip('/')}/docs"
        response = requests.get(ocr_check_url, timeout=5)
        if response.status_code == 200:
            result['ocr_status'] = 'online'
        else:
            result['ocr_error'] = f"HTTP {response.status_code}"
    except requests.exceptions.RequestException as e:
        result['ocr_error'] = str(e)

    # 检查AI服务
    try:
        ai_check_url = f"{ai_service_url.rstrip('/')}/v1/models"
        ai_api_key = SystemSettings.get_setting('llm_api_key', '')

        headers = {}
        if ai_api_key:
            headers['Authorization'] = f'Bearer {ai_api_key}'

        response = requests.get(ai_check_url, headers=headers, timeout=5)
        if response.status_code == 200:
            result['ai_status'] = 'online'
        else:
            result['ai_error'] = f"HTTP {response.status_code}"
    except requests.exceptions.RequestException as e:
        result['ai_error'] = str(e)

    return JsonResponse(result)


@login_required
def delete_advice(request, advice_id):
    """删除健康咨询记录"""
    if request.method != 'DELETE':
        return JsonResponse({'success': False, 'error': '不支持的请求方法'})

    try:
        # 获取要删除的咨询记录
        advice = get_object_or_404(HealthAdvice, id=advice_id, user=request.user)

        # 记录删除信息用于日志
        advice_text = advice.question[:50] + '...' if len(advice.question) > 50 else advice.question
        conversation = advice.conversation

        # 删除HealthAdvice记录
        advice.delete()

        # 如果该记录有关联的对话，且这是对话中的最后一条消息，则删除整个对话
        if conversation:
            remaining_messages = HealthAdvice.objects.filter(conversation=conversation).count()
            if remaining_messages == 0:
                conversation.delete()

        return JsonResponse({
            'success': True,
            'message': f'咨询记录"{advice_text}"已删除'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'删除失败: {str(e)}'
        })


@login_required
def manual_input(request):
    """手动输入健康指标"""
    if request.method == 'POST':
        form = ManualIndicatorForm(request.POST)
        report_mode = request.POST.get('report_mode', 'new')  # 获取报告模式

        # 验证表单
        if not form.is_valid():
            context = {
                'form': form,
                'recent_indicators': _get_recent_indicators(request.user),
                'page_title': '手动输入健康指标',
            }
            return render(request, 'medical_records/manual_input.html', context)

        # 根据模式处理
        if report_mode == 'new':
            # 新建体检报告模式
            checkup_date = request.POST.get('checkup_date')
            hospital = request.POST.get('hospital', '手动录入')

            # 验证必填字段
            if not checkup_date:
                form.add_error(None, '请选择体检日期')
                context = {
                    'form': form,
                    'recent_indicators': _get_recent_indicators(request.user),
                    'page_title': '手动输入健康指标',
                }
                return render(request, 'medical_records/manual_input.html', context)

            # 创建新的体检报告
            checkup = HealthCheckup.objects.create(
                user=request.user,
                checkup_date=checkup_date,
                hospital=hospital
            )

        elif report_mode == 'existing':
            # 添加到已有报告模式
            existing_checkup_id = request.POST.get('existing_checkup')

            if not existing_checkup_id:
                form.add_error(None, '请选择要添加的体检报告')
                context = {
                    'form': form,
                    'recent_indicators': _get_recent_indicators(request.user),
                    'page_title': '手动输入健康指标',
                }
                return render(request, 'medical_records/manual_input.html', context)

            # 获取已有的体检报告
            try:
                checkup = HealthCheckup.objects.get(id=existing_checkup_id, user=request.user)
            except HealthCheckup.DoesNotExist:
                form.add_error(None, '选择的体检报告不存在')
                context = {
                    'form': form,
                    'recent_indicators': _get_recent_indicators(request.user),
                    'page_title': '手动输入健康指标',
                }
                return render(request, 'medical_records/manual_input.html', context)

        # 保存健康指标
        indicator = form.save(commit=False)
        indicator.checkup = checkup
        indicator.save()

        messages.success(request, f'健康指标 "{indicator.indicator_name}" 已成功保存！')
        return redirect('medical_records:manual_input')
    else:
        form = ManualIndicatorForm()

    context = {
        'form': form,
        'recent_indicators': _get_recent_indicators(request.user),
        'page_title': '手动输入健康指标',
    }

    return render(request, 'medical_records/manual_input.html', context)


def _get_recent_indicators(user):
    """获取用户最近手动录入的指标"""
    return HealthIndicator.objects.filter(
        checkup__user=user
    ).order_by('-checkup__checkup_date', '-id')[:10]


@login_required
def user_profile(request):
    """用户信息管理"""
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, '个人信息已更新！')
            return redirect('medical_records:user_profile')
    else:
        form = UserProfileForm(instance=profile)

    context = {
        'form': form,
        'profile': profile,
        'page_title': '个人信息',
    }
    return render(request, 'medical_records/user_profile.html', context)


@login_required
def all_checkups(request):
    """所有体检报告列表页面"""
    user = request.user
    checkups = HealthCheckup.objects.filter(user=user).order_by('-checkup_date')
    
    # 分页：每页显示10条记录
    from django.core.paginator import Paginator
    paginator = Paginator(checkups, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'medical_records/all_checkups.html', {
        'page_obj': page_obj,
        'total_checkups': checkups.count(),
        'title': '我的所有体检报告'
    })


@login_required
def delete_checkup(request, checkup_id):
    """删除体检报告"""
    if request.method == 'POST':
        checkup = get_object_or_404(HealthCheckup, id=checkup_id, user=request.user)
        checkup.delete()
        messages.success(request, '体检报告已成功删除。')
        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': '无效的请求方法'}, status=400)


@login_required
def update_indicator(request, indicator_id):
    """更新健康指标"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '不支持的请求方法'}, status=405)

    try:
        # 获取要更新的指标并验证所有权
        indicator = get_object_or_404(HealthIndicator, id=indicator_id, checkup__user=request.user)

        # 获取POST数据
        data = json.loads(request.body)

        # 更新指标字段
        indicator.indicator_type = data.get('indicator_type', indicator.indicator_type)
        indicator.indicator_name = data.get('indicator_name', indicator.indicator_name)
        indicator.value = data.get('value', indicator.value)
        indicator.unit = data.get('unit', indicator.unit)
        indicator.reference_range = data.get('reference_range', indicator.reference_range)
        indicator.status = data.get('status', indicator.status)

        # 保存更改
        indicator.save()

        return JsonResponse({
            'success': True,
            'message': '指标已成功更新'
        })

    except HealthIndicator.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': '指标不存在或无权访问'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'message': '无效的JSON数据'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'更新失败: {str(e)}'
        }, status=500)


# ==================== 导出对话为PDF/Word ====================
@login_required
def export_conversation_pdf(request, conversation_id):
    """导出对话为PDF"""
    try:
        from .export_utils import ConversationExporter
        from .models import Conversation

        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            user=request.user
        )

        exporter = ConversationExporter(conversation_id)
        return exporter.export_to_pdf()

    except Exception as e:
        messages.error(request, f'导出PDF失败: {str(e)}')
        return redirect('medical_records:ai_health_advice')


@login_required
def export_conversation_word(request, conversation_id):
    """导出对话为Word"""
    try:
        from .export_utils import ConversationExporter
        from .models import Conversation

        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            user=request.user
        )

        exporter = ConversationExporter(conversation_id)
        return exporter.export_to_word()

    except Exception as e:
        messages.error(request, f'导出Word失败: {str(e)}')
        return redirect('medical_records:ai_health_advice')

# ==================== 导出健康趋势为PDF/Word ====================
@login_required
def export_health_trends_pdf(request):
    """导出健康趋势为PDF"""
    try:
        from .export_utils import HealthTrendsExporter

        exporter = HealthTrendsExporter(request.user)
        return exporter.export_to_pdf()

    except Exception as e:
        messages.error(request, f'导出PDF失败: {str(e)}')
        return redirect('medical_records:dashboard')


@login_required
def export_health_trends_word(request):
    """导出健康趋势为Word"""
    try:
        from .export_utils import HealthTrendsExporter

        exporter = HealthTrendsExporter(request.user)
        return exporter.export_to_word()

    except Exception as e:
        messages.error(request, f'导出Word失败: {str(e)}')
        return redirect('medical_records:dashboard')


@login_required
def export_checkups_pdf(request):
    """批量导出体检报告为PDF"""
    from .export_utils import CheckupReportsExporter

    try:
        # 获取请求中的报告ID列表
        checkup_ids = request.GET.get('checkup_ids', '')
        if not checkup_ids:
            messages.error(request, '未选择任何报告')
            return redirect('medical_records:data_integration')

        # 解析报告ID
        checkup_id_list = [int(id.strip()) for id in checkup_ids.split(',') if id.strip().isdigit()]

        if not checkup_id_list:
            messages.error(request, '无效的报告ID')
            return redirect('medical_records:data_integration')

        # 获取体检报告
        checkups = HealthCheckup.objects.filter(
            user=request.user,
            id__in=checkup_id_list
        ).order_by('-checkup_date')

        if not checkups.exists():
            messages.error(request, '未找到指定的报告')
            return redirect('medical_records:data_integration')

        # 导出
        exporter = CheckupReportsExporter(checkups)
        return exporter.export_to_pdf()

    except Exception as e:
        messages.error(request, f'导出PDF失败: {str(e)}')
        return redirect('medical_records:data_integration')


@login_required
def export_checkups_word(request):
    """批量导出体检报告为Word"""
    from .export_utils import CheckupReportsExporter

    try:
        # 获取请求中的报告ID列表
        checkup_ids = request.GET.get('checkup_ids', '')
        if not checkup_ids:
            messages.error(request, '未选择任何报告')
            return redirect('medical_records:data_integration')

        # 解析报告ID
        checkup_id_list = [int(id.strip()) for id in checkup_ids.split(',') if id.strip().isdigit()]

        if not checkup_id_list:
            messages.error(request, '无效的报告ID')
            return redirect('medical_records:data_integration')

        # 获取体检报告
        checkups = HealthCheckup.objects.filter(
            user=request.user,
            id__in=checkup_id_list
        ).order_by('-checkup_date')

        if not checkups.exists():
            messages.error(request, '未找到指定的报告')
            return redirect('medical_records:data_integration')

        # 导出
        exporter = CheckupReportsExporter(checkups)
        return exporter.export_to_word()

    except Exception as e:
        messages.error(request, f'导出Word失败: {str(e)}')
        return redirect('medical_records:data_integration')
