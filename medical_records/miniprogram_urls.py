from django.urls import path
from . import miniprogram_api

app_name = 'miniprogram'

urlpatterns = [
    # 用户认证
    path('login/', miniprogram_api.miniprogram_login, name='login'),
    path('register/', miniprogram_api.miniprogram_register, name='register'),
    path('user-info/', miniprogram_api.miniprogram_user_info, name='user_info'),
    path('complete-profile/', miniprogram_api.miniprogram_complete_profile, name='complete_profile'),
    path('change-password/', miniprogram_api.miniprogram_change_password, name='change_password'),

    # 头像管理
    path('avatar/', miniprogram_api.miniprogram_get_avatar, name='get_avatar'),
    path('avatar/upload/', miniprogram_api.miniprogram_upload_avatar, name='upload_avatar'),

    # 体检报告管理
    path('upload/', miniprogram_api.miniprogram_upload_report, name='upload_report'),
    path('processing-status/<int:processing_id>/', miniprogram_api.miniprogram_processing_status, name='processing_status'),

    # 体检记录查询
    path('checkups/', miniprogram_api.miniprogram_checkup_list, name='checkup_list'),
    path('checkups/<int:checkup_id>/', miniprogram_api.miniprogram_checkup_detail, name='checkup_detail'),
    path('checkups/<int:checkup_id>/delete/', miniprogram_api.miniprogram_delete_checkup, name='delete_checkup'),

    # 体检报告导出
    path('export/checkups/pdf/', miniprogram_api.miniprogram_export_checkups_pdf, name='export_checkups_pdf'),
    path('export/checkups/word/', miniprogram_api.miniprogram_export_checkups_word, name='export_checkups_word'),

    # 健康指标
    path('indicators/', miniprogram_api.miniprogram_indicators, name='indicators'),
    path('indicators/<int:indicator_id>/', miniprogram_api.mp_indicator_detail, name='indicator_detail'),
    path('indicators/create/', miniprogram_api.mp_indicator_create, name='indicator_create'),
    path('indicators/<int:indicator_id>/update/', miniprogram_api.mp_indicator_update, name='indicator_update'),
    path('indicators/<int:indicator_id>/delete/', miniprogram_api.mp_indicator_delete, name='indicator_delete'),
    path('indicators/batch-create/', miniprogram_api.mp_indicator_batch_create, name='indicator_batch_create'),
    path('checkups/<int:checkup_id>/indicators/', miniprogram_api.miniprogram_indicators, name='checkup_indicators'),

    # AI建议和对话
    path('advice/', miniprogram_api.miniprogram_get_advice, name='get_advice'),
    path('conversations/', miniprogram_api.miniprogram_conversations, name='conversations'),
    path('conversations/create/', miniprogram_api.miniprogram_create_conversation, name='create_conversation'),
    path('conversations/<int:conversation_id>/', miniprogram_api.miniprogram_conversation_detail, name='conversation_detail'),
    path('advice-message/<int:advice_id>/', miniprogram_api.miniprogram_advice_message_status, name='advice_message_status'),
    path('conversations/<int:conversation_id>/delete/', miniprogram_api.miniprogram_delete_conversation, name='delete_conversation'),
    path('conversations/<int:conversation_id>/test-export/', miniprogram_api.test_export_conversation, name='test_export_conversation'),
    path('conversations/<int:conversation_id>/export/pdf/', miniprogram_api.miniprogram_export_conversation_pdf, name='export_conversation_pdf'),
    path('conversations/<int:conversation_id>/export/word/', miniprogram_api.miniprogram_export_conversation_word, name='export_conversation_word'),

    # 数据整合
    path('integrate-data/', miniprogram_api.miniprogram_integrate_data, name='integrate_data'),
    path('apply-integration/', miniprogram_api.miniprogram_apply_integration, name='apply_integration'),

    # 系统状态和设置
    path('services-status/', miniprogram_api.miniprogram_services_status, name='services_status'),
    path('system-settings/', miniprogram_api.miniprogram_system_settings, name='system_settings'),
    path('hospitals/common/', miniprogram_api.miniprogram_common_hospitals, name='common_hospitals'),
    path('indicator-types/', miniprogram_api.miniprogram_indicator_types, name='indicator_types'),
    path('indicator-trends/', miniprogram_api.miniprogram_indicator_trends, name='indicator_trends'),
    path('detect-duplicates/', miniprogram_api.miniprogram_detect_duplicate_checkups, name='detect_duplicate_checkups'),
    path('merge-duplicates/', miniprogram_api.miniprogram_merge_duplicate_checkups, name='merge_duplicate_checkups'),

    # 药单管理
    path('medications/', miniprogram_api.miniprogram_medications, name='medications'),
    path('medications/<int:medication_id>/', miniprogram_api.miniprogram_medication_detail, name='medication_detail'),
    path('medications/checkin/', miniprogram_api.miniprogram_medication_checkin, name='medication_checkin'),
    path('medications/<int:medication_id>/records/', miniprogram_api.miniprogram_medication_records, name='medication_records'),
    path('medications/recognize-image/', miniprogram_api.miniprogram_recognize_medication_image, name='recognize_medication_image'),

    # 药单组管理
    path('medication-groups/', miniprogram_api.mp_medication_groups, name='medication_groups'),
    path('medication-groups/<int:group_id>/', miniprogram_api.mp_medication_group_detail, name='medication_group_detail'),
    path('medication-groups/<int:group_id>/checkin/', miniprogram_api.mp_medication_group_checkin, name='medication_group_checkin'),
    path('medication-groups/<int:group_id>/dissolve/', miniprogram_api.mp_medication_group_dissolve, name='medication_group_dissolve'),

    # 健康日志（症状日志 & 体征日志）
    path('symptom-logs/', miniprogram_api.mp_symptom_logs, name='symptom_logs'),
    path('symptom-logs/<int:log_id>/', miniprogram_api.mp_symptom_log_detail, name='symptom_log_detail'),
    path('vital-logs/', miniprogram_api.mp_vital_logs, name='vital_logs'),
    path('vital-logs/<int:log_id>/', miniprogram_api.mp_vital_log_detail, name='vital_log_detail'),
    path('vital-types/', miniprogram_api.mp_vital_types, name='vital_types'),
]