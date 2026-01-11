from django.urls import path
from . import miniprogram_api

app_name = 'miniprogram'

urlpatterns = [
    # 用户认证
    path('login/', miniprogram_api.miniprogram_login, name='login'),
    path('user-info/', miniprogram_api.miniprogram_user_info, name='user_info'),

    # 体检报告管理
    path('upload/', miniprogram_api.miniprogram_upload_report, name='upload_report'),
    path('processing-status/<int:processing_id>/', miniprogram_api.miniprogram_processing_status, name='processing_status'),

    # 体检记录查询
    path('checkups/', miniprogram_api.miniprogram_checkup_list, name='checkup_list'),
    path('checkups/<int:checkup_id>/', miniprogram_api.miniprogram_checkup_detail, name='checkup_detail'),
    path('checkups/<int:checkup_id>/delete/', miniprogram_api.miniprogram_delete_checkup, name='delete_checkup'),

    # 健康指标
    path('indicators/', miniprogram_api.miniprogram_indicators, name='indicators'),
    path('indicators/create/', miniprogram_api.miniprogram_create_indicator, name='create_indicator'),
    path('indicators/<int:indicator_id>/update/', miniprogram_api.miniprogram_update_indicator, name='update_indicator'),
    path('indicators/<int:indicator_id>/delete/', miniprogram_api.miniprogram_delete_indicator, name='delete_indicator'),
    path('checkups/<int:checkup_id>/indicators/', miniprogram_api.miniprogram_indicators, name='checkup_indicators'),

    # AI建议和对话
    path('advice/', miniprogram_api.miniprogram_get_advice, name='get_advice'),
    path('conversations/', miniprogram_api.miniprogram_conversations, name='conversations'),
    path('conversations/create/', miniprogram_api.miniprogram_create_conversation, name='create_conversation'),
    path('conversations/<int:conversation_id>/', miniprogram_api.miniprogram_conversation_detail, name='conversation_detail'),
    path('advice-message/<int:advice_id>/', miniprogram_api.miniprogram_advice_message_status, name='advice_message_status'),
    path('conversations/<int:conversation_id>/delete/', miniprogram_api.miniprogram_delete_conversation, name='delete_conversation'),
    path('conversations/<int:conversation_id>/export/pdf/', miniprogram_api.miniprogram_export_conversation_pdf, name='export_conversation_pdf'),
    path('conversations/<int:conversation_id>/export/word/', miniprogram_api.miniprogram_export_conversation_word, name='export_conversation_word'),

    # 数据整合
    path('integrate-data/', miniprogram_api.miniprogram_integrate_data, name='integrate_data'),

    # 系统状态和设置
    path('services-status/', miniprogram_api.miniprogram_services_status, name='services_status'),
    path('system-settings/', miniprogram_api.miniprogram_system_settings, name='system_settings'),
    path('hospitals/common/', miniprogram_api.miniprogram_common_hospitals, name='common_hospitals'),
]