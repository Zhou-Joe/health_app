from django.urls import path
from . import views
from . import api_views

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
    path('api/conversations/<int:conversation_id>/', api_views.get_conversation_messages, name='api_conversation_messages'),
    path('api/conversations/<int:conversation_id>/delete/', api_views.delete_conversation, name='api_delete_conversation'),
    path('api/user-advices/', api_views.get_user_advices, name='api_user_advices'),
    path('api/hospitals/common/', api_views.get_common_hospitals, name='api_common_hospitals'),
    path('api/check-services/', api_views.check_services_status, name='api_check_services'),
    path('api/checkups/', api_views.get_user_checkups, name='api_user_checkups'),
    path('api/integrate-data/', api_views.integrate_data, name='api_integrate_data'),
    path('api/apply-integration/', api_views.apply_integration, name='api_apply_integration'),
    path('api/stream-advice/', api_views.stream_ai_advice, name='api_stream_ai_advice'),
    path('api/stream-upload/', api_views.stream_upload_and_process, name='api_stream_upload'),
    path('api/stream-integrate/', api_views.stream_integrate_data, name='api_stream_integrate'),
    path('api/checkup/<int:checkup_id>/update-notes/', api_views.update_checkup_notes, name='api_update_checkup_notes'),
    path('api/task/<str:task_id>/status/', api_views.api_task_status, name='api_task_status'),
    path('api/processing-mode/', api_views.api_processing_mode, name='api_processing_mode'),

    # 导出功能
    path('conversations/<int:conversation_id>/export/pdf/', views.export_conversation_pdf, name='export_conversation_pdf'),
    path('conversations/<int:conversation_id>/export/word/', views.export_conversation_word, name='export_conversation_word'),

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

    # 药单管理页面
    path('medications/', views.medication_list, name='medication_list'),
]