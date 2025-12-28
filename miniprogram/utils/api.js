// utils/api.js - API接口封装
const { get, post, put, delete: del, uploadFile } = require('./request.js')

module.exports = {
  // ==================== 用户认证 ====================
  // 登录
  login: (data) => post('/login/', data),

  // 获取用户信息
  getUserInfo: () => get('/user-info/'),

  // ==================== 体检报告管理 ====================
  // 上传体检报告
  uploadReport: (filePath, formData) => uploadFile(filePath, formData),

  // 获取处理状态
  getProcessingStatus: (processingId) => get(`/processing-status/${processingId}/`),

  // 获取体检记录列表
  getCheckups: (params) => get('/checkups/', params),

  // 获取体检记录详情
  getCheckupDetail: (checkupId) => get(`/checkups/${checkupId}/`),

  // 删除体检报告
  deleteCheckup: (checkupId) => del(`/checkups/${checkupId}/delete/`),

  // ==================== 健康指标管理 ====================
  // 获取健康指标列表
  getIndicators: (params) => get('/indicators/', params),

  // 创建健康指标
  createIndicator: (data) => post('/indicators/create/', data),

  // 更新健康指标
  updateIndicator: (indicatorId, data) => put(`/indicators/${indicatorId}/update/`, data),

  // 删除健康指标
  deleteIndicator: (indicatorId) => del(`/indicators/${indicatorId}/delete/`),

  // ==================== AI健康建议 ====================
  // 获取AI建议
  getAdvice: (data) => post('/advice/', data),

  // ==================== AI对话 ====================
  // 获取对话列表
  getConversations: () => get('/conversations/'),

  // 创建对话
  createConversation: (data) => post('/conversations/create/', data),

  // 获取对话详情
  getConversationDetail: (conversationId) => get(`/conversations/${conversationId}/`),

  // 删除对话
  deleteConversation: (conversationId) => del(`/conversations/${conversationId}/delete/`),

  // ==================== 数据整合 ====================
  // 整合数据
  integrateData: (data) => post('/integrate-data/', data),

  // ==================== 系统信息 ====================
  // 获取服务状态
  getServicesStatus: () => get('/services-status/'),

  // 获取系统设置
  getSystemSettings: () => get('/system-settings/'),

  // 获取常用医院
  getCommonHospitals: () => get('/hospitals/common/')
}
