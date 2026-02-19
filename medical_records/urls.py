from django.urls import path
from . import views
from . import api_views
from . import batch_upload_views

app_name = 'medical_records'

urlpatterns = [
    # 原有页面路由
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_report, name='upload_report'),
    path('manual-input/', views.manual_input, name='manual_input'),
    path('ai-advice/', views.ai_health_advice, name='ai_health_advice'),
    path('data-integration/', views.data_integration, name='data_integration'),
    path('checkup/<int:checkup_id>/', views.checkup_detail, name='checkup_detail'),
    path('checkup/<int:checkup_id>/delete/', views.delete_checkup, name='delete_checkup'),
    path('checkup/indicator/<int:indicator_id>/update/', views.update_indicator, name='update_indicator'),
    path('all/', views.all_checkups, name='all_checkups'),
    path('settings/', views.system_settings, name='system_settings'),
    path('profile/', views.user_profile, name='user_profile'),
    path('health-management/', views.health_management, name='health_management'),
    # 兼容错误/历史入口，避免外部链接导致404
    path('-management/', views.health_management),
    path('management/', views.health_management),
    path('caregivers/', views.caregiver_access, name='caregiver_access'),
    path('shared/', views.shared_access, name='shared_access'),
    path('shared/<int:owner_id>/checkups/', views.shared_checkups, name='shared_checkups'),
    path('shared/<int:owner_id>/medications/', views.shared_medications, name='shared_medications'),

    # API路由
    path('api/upload/', api_views.upload_and_process, name='api_upload'),
    path('api/status/<int:processing_id>/', api_views.get_processing_status, name='api_status'),
    path('api/history/', api_views.get_processing_history, name='api_history'),
    path('api/ocr/<int:processing_id>/', api_views.get_ocr_result, name='api_ocr'),
    path('api/ai-result/<int:processing_id>/', api_views.get_ai_result, name='api_ai_result'),
    path('api/advice/<int:advice_id>/', views.get_advice_detail, name='api_advice_detail'),
    path('api/advice/<int:advice_id>/delete/', views.delete_advice, name='api_delete_advice'),
    path('api/conversations/', api_views.get_conversations, name='api_conversations'),
    path('api/conversations/create/', api_views.create_new_conversation, name='api_create_conversation'),
    path('api/conversations/<int:conversation_id>/resources/', api_views.api_conversation_resources, name='api_conversation_resources'),
    path('api/conversations/<int:conversation_id>/', api_views.get_conversation_messages, name='api_conversation_messages'),
    path('api/conversations/<int:conversation_id>/delete/', api_views.delete_conversation, name='api_delete_conversation'),
    path('api/user-advices/', api_views.get_user_advices, name='api_user_advices'),
    path('api/hospitals/common/', api_views.get_common_hospitals, name='api_common_hospitals'),
    path('api/check-services/', api_views.check_services_status, name='api_check_services'),
    path('api/checkups/', api_views.get_user_checkups, name='api_user_checkups'),
    path('api/checkups/<int:checkup_id>/', api_views.get_checkup_detail, name='api_checkup_detail'),
    path('api/integrate-data/', api_views.integrate_data, name='api_integrate_data'),
    path('api/apply-integration/', api_views.apply_integration, name='api_apply_integration'),
    path('api/stream-advice/', api_views.stream_ai_advice, name='api_stream_ai_advice'),
    path('api/stream-advice-sync/', api_views.stream_advice_sync, name='api_stream_ai_advice_sync'),
    path('api/stream-ai-summary/', api_views.stream_ai_summary, name='api_stream_ai_summary'),
    path('api/conversations/<int:conversation_id>/summary/', api_views.get_ai_summary, name='api_get_ai_summary'),
    path('api/stream-event-ai-summary/', api_views.stream_event_ai_summary, name='api_stream_event_ai_summary'),
    path('api/events/<int:event_id>/summary/', api_views.get_event_ai_summary, name='api_get_event_ai_summary'),
    path('api/stream-checkup-ai-summary/', api_views.stream_checkup_ai_summary, name='api_stream_checkup_ai_summary'),
    path('api/checkups/<int:checkup_id>/summary/', api_views.get_checkup_ai_summary, name='api_get_checkup_ai_summary'),
    path('api/stream-upload/', api_views.stream_upload_and_process, name='api_stream_upload'),
    path('api/stream-integrate/', api_views.stream_integrate_data, name='api_stream_integrate'),
    path('api/checkup/<int:checkup_id>/update-notes/', api_views.update_checkup_notes, name='api_update_checkup_notes'),
    path('api/checkup/<int:checkup_id>/update/', api_views.update_checkup_info, name='api_update_checkup_info'),
    path('api/checkup/<int:checkup_id>/reparse/', api_views.reparse_checkup, name='api_reparse_checkup'),
    path('api/task/<str:task_id>/status/', api_views.api_task_status, name='api_task_status'),
    path('api/processing-mode/', api_views.api_processing_mode, name='api_processing_mode'),
    path('api/avatar/upload/', api_views.upload_avatar, name='api_avatar_upload'),

    # 导出功能
    path('conversations/<int:conversation_id>/export/pdf/', views.export_conversation_pdf, name='export_conversation_pdf'),
    path('conversations/<int:conversation_id>/export/word/', views.export_conversation_word, name='export_conversation_word'),
    path('conversations/<int:conversation_id>/export-summary/pdf/', views.export_ai_summary_pdf, name='export_ai_summary_pdf'),
    path('conversations/<int:conversation_id>/export-summary/word/', views.export_ai_summary_word, name='export_ai_summary_word'),
    path('events/<int:event_id>/export-summary/pdf/', views.export_event_ai_summary_pdf, name='export_event_ai_summary_pdf'),
    path('events/<int:event_id>/export-summary/word/', views.export_event_ai_summary_word, name='export_event_ai_summary_word'),

    # 健康趋势导出
    path('dashboard/export/pdf/', views.export_health_trends_pdf, name='export_health_trends_pdf'),
    path('dashboard/export/word/', views.export_health_trends_word, name='export_health_trends_word'),

    # 批量导出体检报告
    path('export/checkups/pdf/', views.export_checkups_pdf, name='export_checkups_pdf'),
    path('export/checkups/word/', views.export_checkups_word, name='export_checkups_word'),

    # 药单管理API
    path('api/medications/', api_views.api_medications, name='api_medications'),
    path('api/medications/<int:medication_id>/', api_views.api_medication_detail, name='api_medication_detail'),
    path('api/medications/checkin/', api_views.api_medication_checkin, name='api_medication_checkin'),
    path('api/medications/<int:medication_id>/records/', api_views.api_medication_records, name='api_medication_records'),
    path('api/medications/recognize-image/', api_views.api_medication_recognize_image, name='api_medication_recognize_image'),
    path('api/medication-groups/', api_views.api_medication_groups, name='api_medication_groups'),
    path('api/medication-groups/<int:group_id>/', api_views.api_medication_group_detail, name='api_medication_group_detail'),
    path('api/medication-groups/create/', api_views.api_medication_group_create, name='api_medication_group_create'),
    path('api/medication-groups/<int:group_id>/checkin/', api_views.api_medication_group_checkin, name='api_medication_group_checkin'),
    path('api/medication-groups/<int:group_id>/update/', api_views.api_medication_group_update, name='api_medication_group_update'),
    path('api/medication-groups/<int:group_id>/dissolve/', api_views.api_medication_group_dissolve, name='api_medication_group_dissolve'),
    path('api/medications/auto-cluster/', api_views.api_medication_auto_cluster, name='api_medication_auto_cluster'),
    path('api/medications/without-group/', api_views.api_medications_without_group, name='api_medications_without_group'),

    # 健康事件管理页面
    path('events/', views.events_list, name='events_list'),
    path('events/<int:event_id>/', views.event_detail, name='event_detail'),

    # 健康事件聚合API
    path('api/events/', api_views.api_events, name='api_events'),
    path('api/events/<int:event_id>/', api_views.api_event_detail, name='api_event_detail'),
    path('api/events/<int:event_id>/add-item/', api_views.api_event_add_item, name='api_event_add_item'),
    path('api/events/<int:event_id>/remove-item/<int:item_id>/', api_views.api_event_remove_item, name='api_event_remove_item'),
    path('api/events/auto-cluster/', api_views.api_event_auto_cluster, name='api_event_auto_cluster'),
    path('api/events/recluster/', api_views.api_event_recluster, name='api_event_recluster'),
    path('api/events/available-items/', api_views.api_event_available_items, name='api_event_available_items'),
    path('api/care-goals/<int:goal_id>/suggest-actions/', api_views.api_care_goal_suggest_actions, name='api_care_goal_suggest_actions'),
    path('api/care-goals/<int:goal_id>/actions/bulk/', api_views.api_care_goal_add_actions, name='api_care_goal_add_actions'),

    # 健康管理计划API
    path('api/care-plans/', api_views.api_care_plans, name='api_care_plans'),
    path('api/care-plans/<int:plan_id>/', api_views.api_care_plan_detail, name='api_care_plan_detail'),
    path('api/care-plans/<int:plan_id>/goals/', api_views.api_care_goals, name='api_care_goals'),
    path('api/care-goals/<int:goal_id>/', api_views.api_care_goal_detail, name='api_care_goal_detail'),
    path('api/care-goals/<int:goal_id>/actions/', api_views.api_care_actions, name='api_care_actions'),
    path('api/care-actions/<int:action_id>/', api_views.api_care_action_detail, name='api_care_action_detail'),

    # 健康日志API（症状日志 & 体征日志）
    path('api/symptom-logs/', api_views.api_symptom_logs, name='api_symptom_logs'),
    path('api/symptom-logs/<int:log_id>/', api_views.api_symptom_log_detail, name='api_symptom_log_detail'),
    path('api/vital-logs/', api_views.api_vital_logs, name='api_vital_logs'),
    path('api/vital-logs/<int:log_id>/', api_views.api_vital_log_detail, name='api_vital_log_detail'),
    path('api/vital-types/', api_views.api_vital_types, name='api_vital_types'),

    # TODO: Advanced features - to be implemented later
    # # 批量操作
    # path('api/events/<int:event_id>/bulk-add-items/', api_views.api_event_bulk_add_items, name='api_event_bulk_add_items'),
    # path('api/events/<int:event_id>/bulk-remove-items/', api_views.api_event_bulk_remove_items, name='api_event_bulk_remove_items'),
    # path('api/events/bulk-delete/', api_views.api_event_bulk_delete, name='api_event_bulk_delete'),
    #
    # # 事件模板
    # path('api/events/templates/', api_views.api_event_templates, name='api_event_templates'),
    # path('api/events/apply-template/', api_views.api_event_apply_template, name='api_event_apply_template'),
    #
    # # 统计和搜索
    # path('api/events/statistics/', api_views.api_event_statistics, name='api_event_statistics'),
    # path('api/events/search/', api_views.api_events_advanced_search, name='api_events_advanced_search'),
    # path('api/events/timeline/', api_views.api_events_timeline, name='api_events_timeline'),

    # 批量上传API
    path('api/batch-upload/', batch_upload_views.batch_upload_and_process, name='api_batch_upload'),
    path('api/batch-upload/<int:batch_id>/status/', batch_upload_views.get_batch_status, name='api_batch_status'),
    path('api/batch-upload/list/', batch_upload_views.get_batch_list, name='api_batch_list'),
    path('api/batch-upload/item/<int:item_id>/retry/', batch_upload_views.retry_batch_item, name='api_batch_item_retry'),

    # 批量上传页面
    path('batch-upload/', views.batch_upload_page, name='batch_upload_page'),
]
