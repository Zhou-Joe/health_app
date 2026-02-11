/**
 * API 接口封装
 * 所有 API 接口的统一管理
 */

const config = require('../config.js')
const request = require('./request.js')

module.exports = {
  // ==================== 用户认证 ====================
  login: (data) => request.post(config.api.login, data),

  wechatLogin: (data) => request.post(config.api.login, data),

  completeProfile: (data) => request.post(config.api.completeProfile, data),

  getUserInfo: () => request.get(config.api.userInfo),

  // ==================== 体检报告管理 ====================
  uploadReport: (filePath, formData) =>
    request.uploadFile(filePath, formData, { url: config.api.uploadReport }),

  getProcessingStatus: (processingId) =>
    request.get(config.api.processingStatus(processingId)),

  getCheckups: (params = {}) =>
    request.get(config.api.checkups, params),

  getCheckupDetail: (checkupId) =>
    request.get(config.api.checkupDetail(checkupId)),

  deleteCheckup: (checkupId) =>
    request.delete(config.api.deleteCheckup(checkupId)),

  // ==================== 健康指标管理 ====================
  getIndicators: (params = {}) =>
    request.get(config.api.indicators(params), params),

  createIndicator: (data) =>
    request.post(config.api.createIndicator, data),

  updateIndicator: (indicatorId, data) =>
    request.put(config.api.updateIndicator(indicatorId), data),

  deleteIndicator: (indicatorId) =>
    request.delete(config.api.deleteIndicator(indicatorId)),

  // ==================== AI健康建议 ====================
  getAdvice: (data) =>
    request.post(config.api.advice, data),

  // 流式AI咨询（使用SSE）
  streamAdvice: (data, onMessage, onError, onComplete) => {
    const token = wx.getStorageSync(config.storageKeys.TOKEN)
    const url = config.server.baseUrl + config.api.streamAdvice

    // 小程序不支持原生的SSE，需要使用WebSocket或者轮询
    // 这里使用WebSocket实现流式响应
    return new Promise((resolve, reject) => {
      const wsUrl = url.replace('http://', 'ws://').replace('https://', 'wss://')
      const socketTask = wx.connectSocket({
        url: wsUrl,
        header: {
          'Authorization': `Token ${token}`
        }
      })

      socketTask.onOpen(() => {
        // 发送数据
        socketTask.send({
          data: JSON.stringify(data)
        })
      })

      socketTask.onMessage((res) => {
        try {
          const lines = res.data.split('\n')
          lines.forEach(line => {
            if (line.startsWith('data: ')) {
              const data = JSON.parse(line.slice(6))
              if (data.error) {
                onError?.(data.error)
              } else if (data.content) {
                onMessage?.(data.content)
              } else if (data.done) {
                onComplete?.()
                socketTask.close()
              }
            }
          })
        } catch (e) {
          console.error('解析消息失败:', e)
        }
      })

      socketTask.onError((err) => {
        console.error('WebSocket错误:', err)
        onError?.(err)
        reject(err)
      })

      socketTask.onClose(() => {
        resolve()
      })
    })
  },

  // ==================== AI对话 ====================
  getConversations: () =>
    request.get(config.api.conversations),

  // 直接调用小程序专用的非流式API
  streamAdviceSync: (data) =>
    request.post(config.api.streamAdviceSync, data, { timeout: 300000 }), // 5分钟超时

  createConversation: (data) =>
    request.post(config.api.createConversation, data),

  getAdviceMessageStatus: (adviceId) =>
    request.get(config.api.adviceMessageStatus(adviceId)),

  getConversationDetail: (conversationId) =>
    request.get(config.api.conversationDetail(conversationId)),

  getConversationMessages: (conversationId) =>
    request.get(config.api.conversationMessages(conversationId)),

  deleteConversation: (conversationId) =>
    request.delete(config.api.deleteConversation(conversationId)),

  // 导出对话
  exportConversationPDF: (conversationId) =>
    request.downloadFile(config.api.exportConversationPDF(conversationId)),

  exportConversationWord: (conversationId) =>
    request.downloadFile(config.api.exportConversationWord(conversationId)),

  // ==================== 数据整合 ====================
  integrateData: (data) =>
    request.post(config.api.integrateData, data),

  applyIntegration: (data) =>
    request.post(config.api.applyIntegration, data),

  // ==================== 健康事件 ====================
  getEvents: (params = {}) =>
    request.get(config.api.events, params),

  getEventDetail: (eventId) =>
    request.get(config.api.eventDetail(eventId)),

  updateEvent: (eventId, data) =>
    request.put(config.api.eventDetail(eventId), data),

  autoClusterEvents: (data = {}) =>
    request.post(config.api.eventAutoCluster, data),

  getEventAvailableItems: (params = {}) =>
    request.get(config.api.eventAvailableItems, params),

  addEventItem: (eventId, data) =>
    request.post(config.api.eventAddItem(eventId), data),

  removeEventItem: (eventId, itemId) =>
    request.delete(config.api.eventRemoveItem(eventId, itemId)),

  // ==================== 系统信息 ====================
  getServicesStatus: () =>
    request.get(config.api.servicesStatus),

  getSystemSettings: () =>
    request.get(config.api.systemSettings),

  updateSystemSettings: (data) =>
    request.post(config.api.systemSettings, data),

  getCommonHospitals: () =>
    request.get(config.api.commonHospitals),

  getIndicatorTypes: () =>
    request.get(config.api.indicatorTypes),

  detectDuplicates: () =>
    request.get(config.api.detectDuplicates),

  mergeDuplicates: (data) =>
    request.post(config.api.mergeDuplicates, data),

  // ==================== 药单管理 ====================
  getMedications: () =>
    request.get(config.api.medications),

  createMedication: (data) =>
    request.post(config.api.medications, data),

  getMedicationDetail: (medicationId) =>
    request.get(config.api.medicationDetail(medicationId)),

  updateMedication: (medicationId, data) =>
    request.put(config.api.medicationDetail(medicationId), data),

  deleteMedication: (medicationId) =>
    request.delete(config.api.medicationDetail(medicationId)),

  medicationCheckin: (data) =>
    request.post(config.api.medicationCheckin, data),

  getMedicationRecords: (medicationId) =>
    request.get(config.api.medicationRecords(medicationId)),

  // ==================== 导出功能 ====================
  exportHealthTrendsPDF: () =>
    request.downloadFile(config.api.exportHealthTrendsPDF),

  exportHealthTrendsWord: () =>
    request.downloadFile(config.api.exportHealthTrendsWord),

  // 导出体检报告（单个或批量）
  exportCheckupsPDF: (checkupIds) => {
    const url = `${config.api.exportCheckupsPDF}?checkup_ids=${Array.isArray(checkupIds) ? checkupIds.join(',') : checkupIds}`
    return request.downloadFile(url)
  },

  exportCheckupsWord: (checkupIds) => {
    const url = `${config.api.exportCheckupsWord}?checkup_ids=${Array.isArray(checkupIds) ? checkupIds.join(',') : checkupIds}`
    return request.downloadFile(url)
  }
}
