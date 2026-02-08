/**
 * 全局配置文件
 * 集中管理所有配置项
 */

module.exports = {
  // 服务器配置
  server: {
    // 生产环境URL
    baseUrl: 'https://www.zctestbench.asia', // 生产环境
    // 开发时在微信开发者工具中：
    // 1. 点击右上角"详情"
    // 2. 本地设置 -> 勾选"不校验合法域名"
    // baseUrl: 'http://127.0.0.1:8000', // 开发环境（注释掉）
    timeout: 60000 // 请求超时时间（AI生成可能需要较长时间）
  },

  // API 路径配置（注意：小程序API使用 /api/miniprogram/ 前缀）
  api: {
    // 用户认证
    login: '/api/miniprogram/login/',
    userInfo: '/api/miniprogram/user-info/',
    completeProfile: '/api/miniprogram/complete-profile/',

    // 体检报告
    checkups: '/api/miniprogram/checkups/',
    checkupDetail: (id) => `/api/miniprogram/checkups/${id}/`,
    deleteCheckup: (id) => `/api/miniprogram/checkups/${id}/delete/`,
    uploadReport: '/api/miniprogram/upload/',
    processingStatus: (id) => `/api/miniprogram/processing-status/${id}/`,

    // 健康指标
    indicators: (params) => {
      // 支持两种路径：/api/miniprogram/indicators/ 和 /api/miniprogram/checkups/<id>/indicators/
      if (params && params.checkup_id !== undefined && params.checkup_id !== null) {
        return `/api/miniprogram/checkups/${params.checkup_id}/indicators/`
      }
      return '/api/miniprogram/indicators/'
    },
    createIndicator: '/api/miniprogram/indicators/create/',
    updateIndicator: (id) => `/api/miniprogram/indicators/${id}/update/`,
    deleteIndicator: (id) => `/api/miniprogram/indicators/${id}/delete/`,

    // AI健康建议
    advice: '/api/miniprogram/advice/',
    streamAdvice: '/api/stream-advice/', // 网页端的流式接口
    streamAdviceSync: '/api/stream-advice-sync/', // 小程序专用的非流式接口

    // AI对话
    conversations: '/api/miniprogram/conversations/',
    conversationDetail: (id) => `/api/miniprogram/conversations/${id}/`,
    conversationMessages: (id) => `/api/miniprogram/conversations/${id}/`, // 与conversationDetail相同
    createConversation: '/api/miniprogram/conversations/create/',
    adviceMessageStatus: (id) => `/api/miniprogram/advice-message/${id}/`,
    deleteConversation: (id) => `/api/miniprogram/conversations/${id}/delete/`,
    exportConversationPDF: (id) => `/api/miniprogram/conversations/${id}/export/pdf/`,
    exportConversationWord: (id) => `/api/miniprogram/conversations/${id}/export/word/`,

    // 数据整合
    integrateData: '/api/miniprogram/integrate-data/',
    applyIntegration: '/api/miniprogram/apply-integration/',

    // 系统信息
    servicesStatus: '/api/miniprogram/services-status/', // 小程序专用接口
    systemSettings: '/api/miniprogram/system-settings/', // 小程序专用接口
    commonHospitals: '/api/miniprogram/hospitals/common/',
    indicatorTypes: '/api/miniprogram/indicator-types/', // 获取指标类型统计
    detectDuplicates: '/api/miniprogram/detect-duplicates/', // 检测重复报告
    mergeDuplicates: '/api/miniprogram/merge-duplicates/', // 合并重复报告

    // 药单管理（使用小程序专用接口）
    medications: '/api/miniprogram/medications/',
    medicationDetail: (id) => `/api/miniprogram/medications/${id}/`,
    medicationCheckin: '/api/miniprogram/medications/checkin/',
    medicationRecords: (id) => `/api/miniprogram/medications/${id}/records/`,

    // 导出功能（使用小程序专用接口）
    exportHealthTrendsPDF: '/dashboard/export/pdf/',
    exportHealthTrendsWord: '/dashboard/export/word/',
    exportCheckupsPDF: '/api/miniprogram/export/checkups/pdf/',
    exportCheckupsWord: '/api/miniprogram/export/checkups/word/'
  },

  // 存储键名
  storageKeys: {
    TOKEN: 'token',
    USER_INFO: 'userInfo',
    LAST_CONVERSATION_SETTINGS: 'lastConversationSettings',
    THEME: 'theme'
  },

  // 页面路径
  pages: {
    login: '/pages/login/login',
    dashboard: '/pages/dashboard/dashboard',
    upload: '/pages/upload/upload',
    checkups: '/pages/checkups/checkups',
    checkupDetail: '/pages/checkup-detail/checkup-detail',
    indicatorEdit: '/pages/indicator-edit/indicator-edit',
    aiAdvice: '/pages/ai-advice/ai-advice',
    conversation: '/pages/conversation/conversation',
    integration: '/pages/integration/integration',
    settings: '/pages/settings/settings',
    completeProfile: '/pages/complete-profile/complete-profile'
  },

  // 工作流类型
  workflows: {
    MINERU_PIPELINE: 'mineru_pipeline',
    MINERU_VLM: 'mineru_vlm',
    MULTIMODAL: 'vl_model'
  },

  // 指标状态
  indicatorStatus: {
    NORMAL: 'normal',
    ATTENTION: 'attention',
    ABNORMAL: 'abnormal'
  },

  // AI 提供商
  aiProviders: {
    OPENAI: 'openai',
    GEMINI: 'gemini'
  }
}
