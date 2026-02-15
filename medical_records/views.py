from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Avg
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
import json
import requests
from .models import (
    HealthCheckup,
    HealthIndicator,
    HealthAdvice,
    SystemSettings,
    UserProfile,
    Medication,
    MedicationRecord,
    MedicationGroup,
    HealthEvent,
    EventItem,
    SymptomEntry,
    VitalEntry,
    CarePlan,
    CareGoal,
    CareAction,
    CaregiverAccess,
)
from .forms import (
    HealthCheckupForm,
    HealthIndicatorForm,
    ManualIndicatorForm,
    HealthAdviceForm,
    SystemSettingsForm,
    CustomUserCreationForm,
    UserProfileForm,
    SymptomEntryForm,
    VitalEntryForm,
    CarePlanForm,
    CareGoalForm,
    CareActionForm,
    CaregiverAccessForm,
)
from .llm_prompts import AI_DOCTOR_SYSTEM_PROMPT


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

    # 为每个checkup添加指标状态统计
    from django.db.models import Count, Q
    checkups_with_stats = []
    for checkup in list(all_checkups[:10]):
        indicators = HealthIndicator.objects.filter(checkup=checkup)
        stats = indicators.aggregate(
            normal_count=Count('id', filter=Q(status='normal')),
            attention_count=Count('id', filter=Q(status='attention')),
            abnormal_count=Count('id', filter=Q(status='abnormal'))
        )
        checkups_with_stats.append({
            'checkup': checkup,
            'normal_count': stats['normal_count'] or 0,
            'attention_count': stats['attention_count'] or 0,
            'abnormal_count': stats['abnormal_count'] or 0,
            'total_count': indicators.count()
        })

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

    # 用药提醒 - 获取当前需要服药的药单
    today = timezone.now().date()
    medication_reminders = Medication.objects.filter(
        user=user,
        is_active=True,
        start_date__lte=today,
        end_date__gte=today
    ).order_by('start_date')

    # 为每个药单检查今天是否已服药
    medication_reminders_with_status = []
    for med in medication_reminders:
        # 检查今天是否已有服药记录
        taken_today = MedicationRecord.objects.filter(
            medication=med,
            record_date=today
        ).exists()

        medication_reminders_with_status.append({
            'medication': med,
            'taken_today': taken_today,
            'days_remaining': (med.end_date - today).days + 1,
            'progress_percentage': med.progress_percentage
        })

    # 计算健康评分和统计数据
    health_score = 85  # 默认分数
    total_indicators = 0
    normal_indicators_count = 0
    warning_indicators_count = 0
    
    if latest_checkup:
        total_indicators = HealthIndicator.objects.filter(checkup=latest_checkup).count()
        normal_indicators_count = HealthIndicator.objects.filter(
            checkup=latest_checkup,
            status='normal'
        ).count()
        warning_indicators_count = HealthIndicator.objects.filter(
            checkup=latest_checkup,
            status__in=['attention', 'abnormal']
        ).count()
        if total_indicators > 0:
            health_score = int((normal_indicators_count / total_indicators) * 100)

    # 计算本月新增记录数
    today = timezone.now().date()
    first_day_of_month = today.replace(day=1)
    monthly_records = HealthCheckup.objects.filter(
        user=user,
        checkup_date__gte=first_day_of_month
    ).count()

    # 计算距上次记录天数
    days_since_last_record = 999
    if latest_checkup:
        days_since_last_record = (today - latest_checkup.checkup_date).days

    # 计算正常指标百分比
    normal_percentage = 0
    if total_indicators > 0:
        normal_percentage = int((normal_indicators_count / total_indicators) * 100)

    # 最近健康事件（用于首页整合展示）
    recent_events = HealthEvent.objects.filter(user=user).annotate(
        item_count=Count('event_items')
    ).order_by('-start_date')[:10]
    total_events = HealthEvent.objects.filter(user=user).count()

    # 准备健康事件数据（用于S型时间轴）
    health_events = []
    for event in recent_events:
        event_items = event.event_items.all()[:5]
        items_summary = []
        for item in event_items:
            items_summary.append({
                'summary': item.item_summary,
                'added_by': item.added_by
            })
        
        health_events.append({
            'id': event.id,
            'date': event.start_date,
            'end_date': event.end_date,
            'title': event.name,
            'description': event.description or '',
            'type': event.event_type,
            'status': event.status,
            'item_count': event.item_count,
            'items': items_summary,
            'duration_days': event.duration_days,
            'is_auto_generated': event.is_auto_generated
        })

    # 准备健康指标趋势数据 - 按大类分组，每个指标单独一个表格
    indicator_trends = []

    # 定义指标分类映射
    category_mapping = {
        'blood_pressure': '血压指标',
        'heart_rate': '心率指标',
        'blood_sugar': '血糖指标',
        'weight': '体重指标',
        'height': '身高指标',
        'temperature': '体温指标',
        'oxygen': '血氧指标',
        'cholesterol': '胆固醇指标',
        'liver_function': '肝功能指标',
        'kidney_function': '肾功能指标',
        'blood_routine': '血常规指标',
        'urine_routine': '尿常规指标',
        'other_exam': '其他检查',
    }

    # 获取所有指标类型
    all_indicator_types = HealthIndicator.objects.filter(
        checkup__user=user
    ).values_list('indicator_type', flat=True).distinct()

    for indicator_type in all_indicator_types:
        # 获取该类型下所有不同的指标名称
        indicator_names = HealthIndicator.objects.filter(
            checkup__user=user,
            indicator_type=indicator_type
        ).values_list('indicator_name', flat=True).distinct()

        if indicator_names:
            category_name = category_mapping.get(indicator_type, indicator_type)
            indicators_list = []

            for indicator_name in indicator_names:
                # 获取该指标的所有历史记录
                records = HealthIndicator.objects.filter(
                    checkup__user=user,
                    indicator_type=indicator_type,
                    indicator_name=indicator_name
                ).select_related('checkup').order_by('-checkup__checkup_date')[:20]

                if records:
                    records_list = []
                    for record in records:
                        records_list.append({
                            'date': record.checkup.checkup_date,
                            'value': record.value,
                            'unit': record.unit,
                            'reference_range': record.reference_range,
                            'status': record.status,
                        })

                    # 计算趋势：比较最新值和上一次的值
                    trend = None
                    if len(records_list) >= 2:
                        try:
                            # 尝试提取数值进行比较
                            import re
                            
                            def extract_number(value_str):
                                """从字符串中提取数值"""
                                if not value_str:
                                    return None
                                # 处理血压格式如 "120/80"
                                if '/' in str(value_str):
                                    parts = str(value_str).split('/')
                                    if len(parts) == 2:
                                        try:
                                            return float(parts[0].strip())
                                        except:
                                            return None
                                # 提取普通数值
                                match = re.search(r'-?\d+\.?\d*', str(value_str))
                                if match:
                                    return float(match.group())
                                return None
                            
                            latest_val = extract_number(records_list[0]['value'])
                            prev_val = extract_number(records_list[1]['value'])
                            
                            if latest_val is not None and prev_val is not None:
                                diff = latest_val - prev_val
                                if diff > 0:
                                    trend = 'up'
                                elif diff < 0:
                                    trend = 'down'
                                else:
                                    trend = 'stable'
                        except Exception:
                            trend = None

                    indicators_list.append({
                        'name': indicator_name,
                        'records': records_list,
                        'trend': trend
                    })

            if indicators_list:
                indicator_trends.append({
                    'category_name': category_name,
                    'indicator_type': indicator_type,
                    'indicators': indicators_list
                })

    # 获取AI建议摘要
    ai_advice = None
    latest_advice = HealthAdvice.objects.filter(user=user).order_by('-created_at').first()
    if latest_advice:
        ai_advice = {
            'summary': latest_advice.answer[:200] + '...' if len(latest_advice.answer) > 200 else latest_advice.answer,
            'tips': latest_advice.answer.split('\n')[:3] if '\n' in latest_advice.answer else [latest_advice.answer[:100]]
        }

    context = {
        # 侧边栏数据
        'recent_checkups': recent_checkups,
        'abnormal_indicators': abnormal_indicators,

        # 图表数据
        'chart_data': json.dumps(chart_data),

        # 动态指标分类映射
        'indicator_type_mapping': json.dumps(indicator_type_mapping),
        'indicator_type_list': json.dumps(indicator_type_list),

        # 统计数据 - 用于统计卡片
        'total_records': total_checkups,
        'monthly_records': monthly_records,
        'normal_indicators': normal_indicators_count,
        'warning_indicators': warning_indicators_count,
        'days_since_last_record': days_since_last_record,
        'normal_percentage': normal_percentage,
        
        # 原有统计数据
        'total_checkups': total_checkups,
        'health_score': health_score,
        'latest_checkup': latest_checkup,

        # 图表数据（兼容旧模板）
        'chart_labels': json.dumps([]),
        'systolic_data': json.dumps([]),
        'diastolic_data': json.dumps([]),

        # 关键指标概览
        'key_indicators': _get_key_indicators_summary(user),

        # 我的体检报告卡片数据
        'all_checkups': checkups_with_stats,

        # 用药提醒
        'medication_reminders': medication_reminders_with_status,
        'has_medication_reminders': len(medication_reminders_with_status) > 0,

        # 健康事件
        'recent_events': recent_events,
        'total_events': total_events,
        'health_events': health_events,

        # 健康指标趋势数据（按大类分组）
        'indicator_trends': indicator_trends,

        # AI建议
        'ai_advice': ai_advice,
    }

    return render(request, 'medical_records/dashboard.html', context)


def attach_entry_to_daily_event(user, entry_date, entry_obj):
    """将症状/体征日志挂接到当天的自动事件，便于时间线展示"""
    event, _ = HealthEvent.objects.get_or_create(
        user=user,
        start_date=entry_date,
        end_date=entry_date,
        event_type='wellness',
        is_auto_generated=True,
        defaults={
            'name': f"{entry_date} 日志",
            'description': '自动创建：症状/体征日志'
        }
    )

    EventItem.objects.get_or_create(
        event=event,
        content_type=ContentType.objects.get_for_model(entry_obj),
        object_id=entry_obj.id,
        defaults={'added_by': 'auto'}
    )


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
                    # 继续现有对话（包含历史对话上下文）
                    conversation_id = request.POST.get('conversation_id')
                    if conversation_id:
                        from .models import Conversation
                        try:
                            conversation = Conversation.objects.get(id=conversation_id, user=request.user, is_active=True)
                            conversation_for_context = conversation  # 继续对话时，传递 conversation 以包含历史上下文
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
                    # 创建新对话（不包含历史对话上下文）
                    from .models import Conversation
                    # 使用用户问题的前50个字符作为对话标题
                    question_text = advice.question[:50]
                    if len(advice.question) > 50:
                        question_text += '...'
                    conversation = Conversation.create_new_conversation(request.user, f"健康咨询: {question_text}")
                    # 创建新对话时，设置为 None 以便后续判断不包含历史上下文
                    conversation_for_context = None

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

                # 获取药单模式
                medication_mode = request.POST.get('medication_mode', 'no_medications')

                # 获取用户选择的药单
                selected_medications = None
                if medication_mode == 'select_medications':
                    medication_ids = request.POST.getlist('selected_medications')
                    if medication_ids:
                        from .models import Medication
                        selected_medications = Medication.objects.filter(
                            id__in=medication_ids,
                            user=request.user,
                            is_active=True
                        )

                # 生成AI响应，传入选择的报告、药单和对话上下文
                # 注意：conversation 用于关联消息到对话，conversation_for_context 用于决定是否包含历史上下文
                question = advice.question
                print(f"[Web AI] 开始生成AI响应，问题: {question[:50]}...")
                answer, prompt_sent, conversation_context = generate_ai_advice(question, request.user, selected_reports, conversation_for_context, selected_medications)

                print(f"[Web AI] AI响应生成完成，长度: {len(answer) if answer else 0}")

                # 如果AI生成失败，返回错误信息
                if not answer:
                    error_msg = "AI医生服务暂时不可用，请稍后再试"
                    print(f"[Web AI] AI生成失败或返回空")
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

                # 保存选中的报告ID列表
                if selected_reports:
                    report_ids = [str(r.id) for r in selected_reports]
                    advice.selected_reports = json.dumps(report_ids, ensure_ascii=False)

                # 保存选中的药单ID列表
                if selected_medications:
                    medication_ids = [str(m.id) for m in selected_medications]
                    advice.selected_medications = json.dumps(medication_ids, ensure_ascii=False)

                print(f"[Web AI] 准备保存HealthAdvice到数据库...")
                print(f"[Web AI] advice.id: {advice.id if advice.id else 'None (尚未保存)'}")
                print(f"[Web AI] answer长度: {len(advice.answer)}")
                print(f"[Web AI] conversation: {advice.conversation}")

                advice.save()

                print(f"[Web AI] HealthAdvice保存成功，ID: {advice.id}")

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

    # 获取用户的药单
    from .models import Medication
    medications = Medication.objects.filter(user=request.user, is_active=True).order_by('-created_at')

    context = {
        'form': form,
        'user_advices': user_advices,
        'reports_with_info': reports_with_info,
        'medications': medications,
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
            'age': user.userprofile.age if hasattr(user, 'userprofile') and user.userprofile else None,
            'gender': user.userprofile.get_gender_display() if hasattr(user, 'userprofile') and user.userprofile else None,
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
            'age': user.userprofile.age if hasattr(user, 'userprofile') and user.userprofile else None,
            'gender': user.userprofile.get_gender_display() if hasattr(user, 'userprofile') and user.userprofile else None,
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
    """获取用户最近的对话上下文

    Args:
        user: 用户对象
        conversation: 对话对象，如果为 None 则返回空列表（新对话）
        max_conversations: 最大对话数量（仅在 conversation 为 None 时有效，目前该参数已废弃）
    """
    if conversation:
        # 获取特定对话的上下文（继续对话模式）
        recent_advices = HealthAdvice.get_conversation_messages(conversation.id)
    else:
        # 创建新对话，不包含任何历史对话上下文
        recent_advices = []

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

                    # 确保 value 是字符串
                    if not isinstance(value, str):
                        value = str(value) if value is not None else ''

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


def call_ai_doctor_api(question, health_data, user, conversation_context=None, medications=None):
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
            except UserProfile.DoesNotExist:
                # 用户没有个人信息记录，跳过
                pass
            except Exception as e:
                # 其他异常也跳过，但记录日志
                print(f"[警告] 获取用户个人信息时出错: {e}")
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
            system_message = AI_DOCTOR_SYSTEM_PROMPT

            return call_gemini_api(full_prompt, system_message, timeout), None

        # 使用 OpenAI 兼容格式
        if not api_url or not model_name:
            return None, "AI医生API未配置"

        # 判断是否为百川API（支持system角色）
        is_baichuan = (
            provider == 'baichuan' or
            'baichuan' in api_url.lower() or
            'Baichuan' in model_name
        )

        # 构建系统提示词（使用统一的prompt配置）
        system_prompt = AI_DOCTOR_SYSTEM_PROMPT

        # 构建用户消息
        user_message_parts = [f"当前问题：{question}"]

        # 添加个人信息
        try:
            user_profile = user.userprofile
            if user_profile.birth_date or user_profile.gender:
                user_message_parts.append("\n个人信息：")
                user_message_parts.append(f"性别：{user_profile.get_gender_display()}")
                if user_profile.age:
                    user_message_parts.append(f"年龄：{user_profile.age}岁")
        except UserProfile.DoesNotExist:
            # 用户没有个人信息记录，跳过
            pass
        except Exception as e:
            # 其他异常也跳过，但记录日志
            print(f"[警告] 获取用户个人信息时出错: {e}")
            pass

        # 添加对话上下文（简化格式以节省token）
        if conversation_context:
            user_message_parts.append("\n对话历史：")
            for i, ctx in enumerate(conversation_context, 1):
                user_message_parts.append(f"{ctx['time']} 问：{ctx['question']}")
                user_message_parts.append(f"答：{ctx['answer']}")

        if health_data is None:
            # 用户选择不使用任何健康数据
            user_message_parts.extend([
                "\n注意：用户选择不提供任何体检报告数据，请仅基于问题提供一般性健康建议。"
            ])

        # 添加药单数据
        if medications and len(medications) > 0:
            user_message_parts.append("\n用户正在服用的药物：")
            for med in medications:
                user_message_parts.append(f"- {med.medicine_name}")
                user_message_parts.append(f"  服药方式：{med.dosage}")
                user_message_parts.append(f"  服用周期：{med.start_date} 至 {med.end_date}")
                if med.notes:
                    user_message_parts.append(f"  备注：{med.notes}")
                # 获取服药记录
                records = med.medicationrecord_set.all().order_by('-record_date')[:7]  # 最近7次
                if records:
                    user_message_parts.append(f"  最近服药记录：")
                    for record in records:
                        user_message_parts.append(f"    {record.record_date} (已服用)")

        if health_data is None:
            # 用户选择不使用任何健康数据，继续提供一般性建议
            user_message_parts.extend([
                "\n请基于以上问题：",
                "1. 结合对话历史，理解用户的关注点",
                "2. 提供一般性的健康建议和知识",
                "3. 针对用户的具体问题给出专业建议",
                "4. 建议何时需要就医或专业咨询",
                "5. 给出实用的生活方式和预防措施"
            ])
        else:
            # 有健康数据时，使用简化格式
            health_data_text = format_health_data_for_prompt(health_data)
            user_message_parts.extend([
                f"\n用户健康数据：\n{health_data_text}",
                "\n请基于以上信息：",
                "1. 结合对话历史，理解用户的连续关注点",
                "2. 分析用户的健康状况和趋势",
                "3. 针对用户的具体问题提供专业建议",
                "4. 注意观察指标的历史变化趋势",
                "5. 给出实用的生活方式和医疗建议",
                "6. 如有异常指标，请特别说明并建议应对措施"
            ])

        user_message = "\n".join(user_message_parts)

        # 调用AI医生API
        headers = {
            'Content-Type': 'application/json'
        }

        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'

        # 构建消息列表
        messages = []

        # 如果是百川API，添加assistant角色消息
        if is_baichuan:
            messages.append({'role': 'assistant', 'content': system_prompt})
            print(f"[AI医生] 使用百川API模式，已添加assistant角色")

        # 添加用户消息
        messages.append({'role': 'user', 'content': user_message})

        data = {
            'model': model_name,
            'messages': messages,
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
            
            # 清理thinking标签和思考过程
            import re
            cleaned_answer = answer.strip()
            
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
                old_text = cleaned_answer
                cleaned_answer = re.sub(pattern, replacement, cleaned_answer, flags=flags)
            
            print(f"AI医生API调用成功，回答长度: {len(cleaned_answer)} 字符")
            return cleaned_answer, None
        else:
            return None, f"AI医生API调用失败: {response.status_code} - {response.text}"

    except requests.exceptions.Timeout:
        return None, "AI医生API请求超时，请稍后再试"
    except requests.exceptions.RequestException as e:
        return None, f"AI医生API请求错误: {str(e)}"
    except Exception as e:
        return None, f"AI医生处理错误: {str(e)}"


def generate_ai_advice(question, user, selected_reports=None, conversation=None, selected_medications=None):
    """生成AI健康建议，返回answer、prompt和conversation_context"""
    # 检查是否配置了AI医生API
    api_url = SystemSettings.get_setting('ai_doctor_api_url')
    model_name = SystemSettings.get_setting('ai_doctor_model_name')

    prompt_sent = ""
    conversation_context = None

    # 优先使用真正的Agent模式（v2 - 真正的LangChain Agent）
    if api_url and model_name:
        try:
            from .ai_doctor_agent_v2 import create_real_ai_doctor_agent

            print(f"[AI建议] 使用真正的LangChain Agent模式")

            # 创建真正的Agent
            agent = create_real_ai_doctor_agent(user, conversation)

            # 执行Agent
            result = agent.ask_question(question, selected_reports, selected_medications)

            if result.get('success') and result.get('answer'):
                print(f"[AI建议] 真正的Agent回答生成成功")
                return result['answer'], result.get('prompt', ''), result.get('conversation_context')
            else:
                print(f"[AI建议] 真正的Agent执行失败，回退到简化模式: {result.get('error')}")
                # 继续使用简化模式

        except ImportError as e:
            print(f"[AI建议] Agent模块导入失败，使用简化模式: {e}")
        except Exception as e:
            print(f"[AI建议] 真正的Agent执行异常，使用简化模式: {e}")
            import traceback
            traceback.print_exc()

    # 尝试使用简化的Agent模式
    if api_url and model_name:
        try:
            from .ai_doctor_agent import create_ai_doctor_agent

            print(f"[AI建议] 使用简化Agent模式生成建议")

            # 创建Agent
            agent = create_ai_doctor_agent(user, conversation)

            # 执行Agent
            result = agent.ask_question(question, selected_reports, selected_medications)

            if result.get('success') and result.get('answer'):
                print(f"[AI建议] 简化Agent回答生成成功")
                return result['answer'], result.get('prompt', ''), result.get('conversation_context')
            else:
                print(f"[AI建议] 简化Agent执行失败，回退到传统模式: {result.get('error')}")
                # 继续使用传统模式

        except ImportError as e:
            print(f"[AI建议] 简化Agent模块导入失败，使用传统模式: {e}")
        except Exception as e:
            print(f"[AI建议] 简化Agent执行异常，使用传统模式: {e}")

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
            answer, error = call_ai_doctor_api(question, None, user, conversation_context, selected_medications)

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
            answer, error = call_ai_doctor_api(question, health_data, user, conversation_context, selected_medications)

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
    from django.contrib.auth.models import User

    is_admin = request.user.is_superuser or request.user.is_staff
    selected_user_id = request.GET.get('user_id')

    if is_admin:
        # Admin用户可以查看所有用户
        users = User.objects.all().order_by('username')

        # 如果选择了特定用户，只显示该用户的报告
        if selected_user_id:
            try:
                selected_user = User.objects.get(id=selected_user_id)
                checkups = HealthCheckup.objects.filter(
                    user=selected_user
                ).prefetch_related('indicators').order_by('-checkup_date')
            except User.DoesNotExist:
                checkups = HealthCheckup.objects.none()
        else:
            # 默认显示所有用户的报告
            checkups = HealthCheckup.objects.all().prefetch_related('indicators').order_by('-checkup_date')
    else:
        # 普通用户只能查看自己的报告
        users = None
        checkups = HealthCheckup.objects.filter(
            user=request.user
        ).prefetch_related('indicators').order_by('-checkup_date')

    context = {
        'checkups': checkups,
        'page_title': '智能数据整合',
        'is_admin': is_admin,
        'users': users,
        'selected_user_id': int(selected_user_id) if selected_user_id else None,
    }

    return render(request, 'medical_records/data_integration.html', context)


@login_required
def system_settings(request):
    """系统设置页面"""
    if request.method == 'POST':
        form = SystemSettingsForm(request.POST)

        # 手动处理健康检查配置项（不在form中的字段）
        if 'ocr_healthcheck_timeout' in request.POST:
            SystemSettings.set_setting('ocr_healthcheck_timeout', request.POST['ocr_healthcheck_timeout'])
        if 'ocr_healthcheck_endpoints' in request.POST:
            SystemSettings.set_setting('ocr_healthcheck_endpoints', request.POST['ocr_healthcheck_endpoints'])
        if 'llm_healthcheck_timeout' in request.POST:
            SystemSettings.set_setting('llm_healthcheck_timeout', request.POST['llm_healthcheck_timeout'])
        if 'llm_healthcheck_endpoint' in request.POST:
            SystemSettings.set_setting('llm_healthcheck_endpoint', request.POST['llm_healthcheck_endpoint'])
        if 'llm_healthcheck_codes' in request.POST:
            SystemSettings.set_setting('llm_healthcheck_codes', request.POST['llm_healthcheck_codes'])
        if 'vl_model_healthcheck_timeout' in request.POST:
            SystemSettings.set_setting('vl_model_healthcheck_timeout', request.POST['vl_model_healthcheck_timeout'])
        if 'vl_model_healthcheck_endpoint' in request.POST:
            SystemSettings.set_setting('vl_model_healthcheck_endpoint', request.POST['vl_model_healthcheck_endpoint'])
        if 'vl_model_healthcheck_codes' in request.POST:
            SystemSettings.set_setting('vl_model_healthcheck_codes', request.POST['vl_model_healthcheck_codes'])

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
        # 健康检查配置
        'ocr_healthcheck_timeout': SystemSettings.get_setting('ocr_healthcheck_timeout', '10'),
        'ocr_healthcheck_endpoints': SystemSettings.get_setting('ocr_healthcheck_endpoints', '/health,/api/health,/docs,/'),
        'llm_healthcheck_timeout': SystemSettings.get_setting('llm_healthcheck_timeout', '10'),
        'llm_healthcheck_endpoint': SystemSettings.get_setting('llm_healthcheck_endpoint', '/v1/models'),
        'llm_healthcheck_codes': SystemSettings.get_setting('llm_healthcheck_codes', '200,401'),
        'vl_model_healthcheck_timeout': SystemSettings.get_setting('vl_model_healthcheck_timeout', '10'),
        'vl_model_healthcheck_endpoint': SystemSettings.get_setting('vl_model_healthcheck_endpoint', '/v1/models'),
        'vl_model_healthcheck_codes': SystemSettings.get_setting('vl_model_healthcheck_codes', '200,401'),
    }

    context = {
        'form': form,
        'current_settings': current_settings,
        'page_title': '系统设置',
    }

    return render(request, 'medical_records/system_settings.html', context)


@login_required
def check_services_status(request):
    """检查OCR和AI服务状态（使用services.py中的函数）"""
    from .services import get_mineru_api_status, get_llm_api_status, get_vision_model_api_status

    # 使用services.py中的状态检查函数（已支持可配置）
    ocr_status = get_mineru_api_status()
    llm_status = get_llm_api_status()
    vl_status = get_vision_model_api_status()

    return JsonResponse({
        'ocr_status': 'online' if ocr_status else 'offline',
        'llm_status': 'online' if llm_status else 'offline',
        'vlm_status': 'online' if vl_status else 'offline'
    })


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


@csrf_exempt
@login_required
def delete_checkup(request, checkup_id):
    """删除体检报告"""
    if request.method == 'POST':
        try:
            checkup = get_object_or_404(HealthCheckup, id=checkup_id, user=request.user)
            checkup.delete()
            return JsonResponse({'success': True, 'message': '体检报告已成功删除。'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    else:
        return JsonResponse({'success': False, 'error': '无效的请求方法'}, status=400)


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


@login_required
def export_ai_summary_pdf(request, conversation_id):
    """导出AI总结为PDF"""
    try:
        from .export_utils import AISummaryExporter
        from .models import Conversation

        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            user=request.user
        )

        if not conversation.ai_summary:
            messages.error(request, '该对话暂无AI总结，请先生成AI总结')
            return redirect('medical_records:ai_health_advice')

        exporter = AISummaryExporter(conversation_id)
        return exporter.export_to_pdf()

    except Exception as e:
        messages.error(request, f'导出PDF失败: {str(e)}')
        return redirect('medical_records:ai_health_advice')


@login_required
def export_ai_summary_word(request, conversation_id):
    """导出AI总结为Word"""
    try:
        from .export_utils import AISummaryExporter
        from .models import Conversation

        conversation = get_object_or_404(
            Conversation,
            id=conversation_id,
            user=request.user
        )

        if not conversation.ai_summary:
            messages.error(request, '该对话暂无AI总结，请先生成AI总结')
            return redirect('medical_records:ai_health_advice')

        exporter = AISummaryExporter(conversation_id)
        return exporter.export_to_word()

    except Exception as e:
        messages.error(request, f'导出Word失败: {str(e)}')
        return redirect('medical_records:ai_health_advice')


@login_required
def export_event_ai_summary_pdf(request, event_id):
    """导出事件AI分析为PDF"""
    try:
        from .export_utils import EventAiSummaryExporter
        from .models import HealthEvent

        event = get_object_or_404(
            HealthEvent,
            id=event_id,
            user=request.user
        )

        if not event.ai_summary:
            messages.error(request, '该事件暂无AI分析，请先生成AI分析')
            return redirect('medical_records:dashboard')

        exporter = EventAiSummaryExporter(event_id)
        return exporter.export_to_pdf()

    except Exception as e:
        messages.error(request, f'导出PDF失败: {str(e)}')
        return redirect('medical_records:dashboard')


@login_required
def export_event_ai_summary_word(request, event_id):
    """导出事件AI分析为Word"""
    try:
        from .export_utils import EventAiSummaryExporter
        from .models import HealthEvent

        event = get_object_or_404(
            HealthEvent,
            id=event_id,
            user=request.user
        )

        if not event.ai_summary:
            messages.error(request, '该事件暂无AI分析，请先生成AI分析')
            return redirect('medical_records:dashboard')

        exporter = EventAiSummaryExporter(event_id)
        return exporter.export_to_word()

    except Exception as e:
        messages.error(request, f'导出Word失败: {str(e)}')
        return redirect('medical_records:dashboard')


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

        # Admin用户可以导出所有报告，普通用户只能导出自己的报告
        is_admin = request.user.is_superuser or request.user.is_staff

        if is_admin:
            checkups = HealthCheckup.objects.filter(
                id__in=checkup_id_list
            ).order_by('-checkup_date')
        else:
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

        # Admin用户可以导出所有报告，普通用户只能导出自己的报告
        is_admin = request.user.is_superuser or request.user.is_staff

        if is_admin:
            checkups = HealthCheckup.objects.filter(
                id__in=checkup_id_list
            ).order_by('-checkup_date')
        else:
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


# ==================== 药单管理 ====================

@login_required
def health_management(request, default_tab='medications'):
    """统一健康管理页：药单 / 日志与计划"""
    allowed_tabs = {'health_log', 'medications'}
    active_tab = request.GET.get('tab', default_tab)

    # 兼容旧链接
    if active_tab in ('diary', 'plans'):
        active_tab = 'health_log'

    if active_tab not in allowed_tabs:
        active_tab = default_tab if default_tab in allowed_tabs else 'medications'

    symptom_form = SymptomEntryForm(request.user)
    vital_form = VitalEntryForm(request.user)
    plan_form = CarePlanForm()
    goal_form = CareGoalForm()
    action_form = CareActionForm()

    if request.method == 'POST':
        module = request.POST.get('module')
        if not module:
            # 兼容旧表单（老页面未带 module 字段）
            if request.POST.get('action'):
                module = 'plans'
            elif request.POST.get('form_type'):
                module = 'diary'

        if module == 'diary':
            active_tab = 'diary'
            form_type = request.POST.get('form_type')

            if form_type == 'symptom':
                symptom_form = SymptomEntryForm(request.user, request.POST)
                vital_form = VitalEntryForm(request.user)
                if symptom_form.is_valid():
                    entry = symptom_form.save(commit=False)
                    entry.user = request.user
                    entry.save()
                    attach_entry_to_daily_event(request.user, entry.entry_date, entry)
                    messages.success(request, '症状日志已添加')
                    return redirect(f"{reverse('medical_records:health_management')}?tab=diary")
            elif form_type == 'vital':
                symptom_form = SymptomEntryForm(request.user)
                vital_form = VitalEntryForm(request.user, request.POST)
                if vital_form.is_valid():
                    entry = vital_form.save(commit=False)
                    entry.user = request.user
                    entry.save()
                    attach_entry_to_daily_event(request.user, entry.entry_date, entry)
                    messages.success(request, '体征日志已添加')
                    return redirect(f"{reverse('medical_records:health_management')}?tab=diary")

        elif module == 'plans':
            active_tab = 'plans'
            action = request.POST.get('action')

            if action == 'create_plan':
                plan_form = CarePlanForm(request.POST)
                if plan_form.is_valid():
                    plan = plan_form.save(commit=False)
                    plan.user = request.user
                    plan.save()
                    messages.success(request, '健康计划已创建')
                    return redirect(f"{reverse('medical_records:health_management')}?tab=plans")
            elif action == 'create_goal':
                plan_id = request.POST.get('plan_id')
                plan = get_object_or_404(CarePlan, id=plan_id, user=request.user)
                goal_form = CareGoalForm(request.POST)
                if goal_form.is_valid():
                    goal = goal_form.save(commit=False)
                    goal.plan = plan
                    goal.save()
                    messages.success(request, '健康目标已添加')
                    return redirect(f"{reverse('medical_records:health_management')}?tab=plans")
            elif action == 'create_action':
                goal_id = request.POST.get('goal_id')
                goal = get_object_or_404(CareGoal, id=goal_id, plan__user=request.user)
                action_form = CareActionForm(request.POST)
                if action_form.is_valid():
                    care_action = action_form.save(commit=False)
                    care_action.goal = goal
                    care_action.suggested_by_ai = request.POST.get('suggested_by_ai') == 'true'
                    care_action.save()
                    goal.recalculate_progress()
                    messages.success(request, '行动已添加')
                    return redirect(f"{reverse('medical_records:health_management')}?tab=plans")
            elif action == 'toggle_action':
                action_id = request.POST.get('action_id')
                care_action = get_object_or_404(CareAction, id=action_id, goal__plan__user=request.user)
                care_action.status = 'done' if care_action.status == 'pending' else 'pending'
                care_action.save(update_fields=['status'])
                care_action.goal.recalculate_progress()
                return redirect(f"{reverse('medical_records:health_management')}?tab=plans")

    symptoms = SymptomEntry.objects.filter(user=request.user).order_by('-entry_date', '-created_at')[:20]
    vitals = VitalEntry.objects.filter(user=request.user).order_by('-entry_date', '-created_at')[:20]
    plans = CarePlan.objects.filter(user=request.user).prefetch_related('goals__actions')
    medications = Medication.objects.filter(user=request.user, group__isnull=True).order_by('-created_at')
    medication_groups = MedicationGroup.objects.filter(user=request.user).prefetch_related('medications').order_by('-created_at')

    context = {
        'active_tab': active_tab,
        'symptom_form': symptom_form,
        'vital_form': vital_form,
        'symptoms': symptoms,
        'vitals': vitals,
        'plan_form': plan_form,
        'goal_form': goal_form,
        'action_form': action_form,
        'plans': plans,
        'medications': medications,
        'medication_groups': medication_groups,
        'page_title': '健康管理'
    }
    return render(request, 'medical_records/health_management.html', context)


# ==================== 健康事件管理 ====================

@login_required
def events_list(request):
    """兼容旧路由：健康事件已整合到首页"""
    return redirect('medical_records:dashboard')


@login_required
def event_detail(request, event_id):
    """健康事件详情页面"""
    event = get_object_or_404(HealthEvent, id=event_id, user=request.user)

    context = {
        'event': event,
        'page_title': event.name
    }
    return render(request, 'medical_records/event_detail.html', context)


# ==================== 照护者授权与共享 ====================
@login_required
def caregiver_access(request):
    """授权照护者访问"""
    if request.method == 'POST':
        form = CaregiverAccessForm(request.POST)
        if form.is_valid():
            caregiver_username = form.cleaned_data['caregiver_username']
            caregiver = User.objects.get(username=caregiver_username)
            if caregiver == request.user:
                messages.error(request, '不能授权给自己')
            else:
                access, _ = CaregiverAccess.objects.update_or_create(
                    owner=request.user,
                    caregiver=caregiver,
                    defaults={
                        'relationship': form.cleaned_data.get('relationship'),
                        'can_view_records': form.cleaned_data.get('can_view_records', False),
                        'can_view_medications': form.cleaned_data.get('can_view_medications', False),
                        'can_view_events': form.cleaned_data.get('can_view_events', False),
                        'can_view_diary': form.cleaned_data.get('can_view_diary', False),
                        'can_manage_medications': form.cleaned_data.get('can_manage_medications', False),
                        'is_active': True
                    }
                )
                messages.success(request, f'已授权 {caregiver.username} 访问')
                return redirect('medical_records:caregiver_access')
    else:
        form = CaregiverAccessForm()

    revoke_id = request.GET.get('revoke')
    if revoke_id:
        access = get_object_or_404(CaregiverAccess, id=revoke_id, owner=request.user)
        access.is_active = False
        access.save(update_fields=['is_active'])
        messages.success(request, '授权已撤销')
        return redirect('medical_records:caregiver_access')

    accesses = CaregiverAccess.objects.filter(owner=request.user).select_related('caregiver').order_by('-created_at')

    context = {
        'form': form,
        'accesses': accesses,
        'page_title': '照护者授权'
    }
    return render(request, 'medical_records/caregiver_access.html', context)


@login_required
def shared_access(request):
    """照护者查看共享列表"""
    shares = CaregiverAccess.objects.filter(caregiver=request.user, is_active=True).select_related('owner').order_by('-created_at')
    context = {
        'shares': shares,
        'page_title': '共享访问'
    }
    return render(request, 'medical_records/shared_access.html', context)


@login_required
def shared_checkups(request, owner_id):
    """查看被授权用户的体检报告"""
    access = get_object_or_404(CaregiverAccess, owner_id=owner_id, caregiver=request.user, is_active=True)
    if not access.can_view_records:
        messages.error(request, '您没有查看体检报告的权限')
        return redirect('medical_records:shared_access')

    checkups = HealthCheckup.objects.filter(user_id=owner_id).order_by('-checkup_date')
    context = {
        'checkups': checkups,
        'shared_user': access.owner,
        'page_title': f"{access.owner.username} 的体检报告"
    }
    return render(request, 'medical_records/shared_checkups.html', context)


@login_required
def shared_medications(request, owner_id):
    """查看被授权用户的药单"""
    access = get_object_or_404(CaregiverAccess, owner_id=owner_id, caregiver=request.user, is_active=True)
    if not access.can_view_medications:
        messages.error(request, '您没有查看药单的权限')
        return redirect('medical_records:shared_access')

    medications = Medication.objects.filter(user_id=owner_id, is_active=True).order_by('-start_date')
    context = {
        'medications': medications,
        'shared_user': access.owner,
        'page_title': f"{access.owner.username} 的药单"
    }
    return render(request, 'medical_records/shared_medications.html', context)
