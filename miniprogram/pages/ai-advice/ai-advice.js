/**
 * AI健康咨询页面
 * 完整实现网页端的所有功能
 */

const api = require('../../utils/api.js')
const util = require('../../utils/util.js')
const config = require('../../config.js')

Page({
  data: {
    // 对话模式
    conversationMode: 'new', // 'new' 或 'continue'
    selectedConversationId: null,
    conversations: [],

    // 报告模式
    reportMode: 'none', // 'none' 或 'select'
    selectedReportIds: [],
    reports: [],

    // 药单选择
    medicationMode: 'none', // 'none' 或 'select'
    selectedMedicationIds: [],
    medications: [],

    // 健康事件
    eventMode: 'none', // 'none' 或 'select'
    selectedEventId: null,
    events: [],

    // 输入
    question: '',
    submitting: false,

    // 弹窗状态
    showModeModal: false,
    showReportModal: false,
    showMedicationModal: false,
    showEventModal: false
  },

  onLoad() {
    this.loadData()
  },

  onShow() {
    this.loadData()
  },

  /**
   * 跳转到对话历史页面
   */
  goToHistory() {
    wx.navigateTo({
      url: '/pages/conversation-history/conversation-history'
    })
  },

  /**
   * 加载数据
   */
  async loadData() {
    util.showLoading('加载中...')
    try {
      const [conversationsRes, reportsRes, medicationsRes, eventsRes] = await Promise.all([
        api.getConversations(),
        api.getCheckups({ page_size: 100 }),
        api.getMedications(),
        api.getEvents({ limit: 50 })
      ])

      const conversations = conversationsRes.data || []
      const reports = reportsRes.data || reportsRes.results || []
      const medications = medicationsRes.medications || []
      const rawEvents = eventsRes.events || eventsRes.data || []

      const events = rawEvents.map(e => ({
        ...e,
        event_type_label: this.getEventTypeLabel(e.event_type),
        date_range: this.getEventDateRange(e)
      }))

      this.setData({
        conversations,
        reports: reports.map(r => ({ ...r, selected: false })),
        medications: medications.map(m => ({ ...m, selected: false })),
        events
      })
    } catch (err) {
      console.error('加载数据失败:', err)
      util.showToast('加载失败')
    } finally {
      util.hideLoading()
    }
  },

  getEventTypeLabel(type) {
    const labelMap = {
      illness: '疾病事件',
      checkup: '体检事件',
      chronic_management: '慢病管理',
      emergency: '急诊事件',
      wellness: '健康管理',
      medication_course: '用药疗程',
      other: '其他'
    }
    return labelMap[type] || '其他'
  },

  getEventDateRange(event) {
    const start = event.start_date || ''
    const end = event.end_date || ''
    if (start && end && start !== end) {
      return `${start} ~ ${end}`
    }
    return start || end || '未知时间'
  },

  /**
   * 选择对话模式
   */
  selectConversationMode(e) {
    const mode = e.currentTarget.dataset.mode
    this.setData({
      conversationMode: mode,
      selectedConversationId: mode === 'continue' && this.data.conversations.length > 0
        ? this.data.conversations[0].id
        : null
    })
  },

  /**
   * 选择要继续的对话
   */
  selectConversation(e) {
    const id = e.currentTarget.dataset.id
    this.setData({ selectedConversationId: id })
  },

  /**
   * 删除对话
   */
  async deleteConversation(e) {
    const id = e.currentTarget.dataset.id

    const confirm = await util.showConfirm('确定要删除这个对话吗？删除后无法恢复。')
    if (!confirm) return

    util.showLoading('删除中...')
    try {
      await api.deleteConversation(id)
      util.showToast('删除成功')

      // 从列表中移除
      const conversations = this.data.conversations.filter(c => c.id !== id)
      let selectedConversationId = this.data.selectedConversationId
      if (selectedConversationId === id) {
        selectedConversationId = conversations.length > 0 ? conversations[0].id : null
      }

      this.setData({ conversations, selectedConversationId })
    } catch (err) {
      console.error('删除失败:', err)
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  },

  /**
   * 选择报告模式
   */
  selectReportMode(e) {
    const mode = e.currentTarget.dataset.mode
    this.setData({
      reportMode: mode,
      selectedReportIds: []
    })

    if (mode === 'select') {
      const reports = this.data.reports.map(r => ({ ...r, selected: false }))
      this.setData({ reports })
    }
  },

  /**
   * 切换报告选择
   */
  toggleReport(e) {
    const id = e.currentTarget.dataset.id
    const reports = this.data.reports.map(r => {
      if (r.id === id) {
        return { ...r, selected: !r.selected }
      }
      return r
    })

    const selectedReportIds = reports
      .filter(r => r.selected)
      .map(r => r.id)

    this.setData({ reports, selectedReportIds })
  },

  /**
   * 全选报告
   */
  selectAllReports() {
    const reports = this.data.reports.map(r => ({ ...r, selected: true }))
    const selectedReportIds = reports.map(r => r.id)
    this.setData({ reports, selectedReportIds })
    util.showToast('已全选')
  },

  /**
   * 选择最近2份报告
   */
  selectRecentReports() {
    const reports = this.data.reports.map((r, index) => ({
      ...r,
      selected: index < 2
    }))
    const selectedReportIds = reports.filter(r => r.selected).map(r => r.id)
    this.setData({ reports, selectedReportIds })
    util.showToast('已选择最近2份')
  },

  /**
   * 清空报告选择
   */
  clearReports() {
    const reports = this.data.reports.map(r => ({ ...r, selected: false }))
    this.setData({ reports, selectedReportIds: [] })
    util.showToast('已清空')
  },

  /**
   * 选择药单模式
   */
  selectMedicationMode(e) {
    const mode = e.currentTarget.dataset.mode
    this.setData({
      medicationMode: mode,
      selectedMedicationIds: []
    })

    if (mode === 'select') {
      const medications = this.data.medications.map(m => ({ ...m, selected: false }))
      this.setData({ medications })
    }
  },

  /**
   * 切换药单选择
   */
  toggleMedication(e) {
    const id = e.currentTarget.dataset.id
    const medications = this.data.medications.map(m => {
      if (m.id === id) {
        return { ...m, selected: !m.selected }
      }
      return m
    })

    const selectedMedicationIds = medications
      .filter(m => m.selected)
      .map(m => m.id)

    this.setData({ medications, selectedMedicationIds })
  },

  /**
   * 全选药单
   */
  selectAllMedications() {
    const medications = this.data.medications.map(m => ({ ...m, selected: true }))
    const selectedMedicationIds = medications.map(m => m.id)
    this.setData({ medications, selectedMedicationIds })
    util.showToast('已全选')
  },

  /**
   * 清空药单选择
   */
  clearMedications() {
    const medications = this.data.medications.map(m => ({ ...m, selected: false }))
    this.setData({ medications, selectedMedicationIds: [] })
    util.showToast('已清空')
  },

  /**
   * 问题输入
   */
  onQuestionInput(e) {
    this.setData({ question: e.detail.value })
  },

  /**
   * 显示对话模式弹窗
   */
  showModeModal() {
    this.setData({ showModeModal: true })
  },

  /**
   * 显示报告弹窗
   */
  showReportModal() {
    this.setData({ showReportModal: true })
  },

  /**
   * 显示药单弹窗
   */
  showMedicationModal() {
    this.setData({ showMedicationModal: true })
  },

  /**
   * 显示健康事件弹窗
   */
  showEventModal() {
    this.setData({ showEventModal: true })
  },

  /**
   * 隐藏所有弹窗
   */
  hideModals() {
    this.setData({
      showModeModal: false,
      showReportModal: false,
      showMedicationModal: false,
      showEventModal: false
    })
  },

  /**
   * 选择事件模式
   */
  selectEventMode(e) {
    const mode = e.currentTarget.dataset.mode
    this.setData({
      eventMode: mode,
      selectedEventId: null
    })
  },

  /**
   * 切换事件选择
   */
  toggleEvent(e) {
    const id = parseInt(e.currentTarget.dataset.id, 10)
    const selectedEventId = this.data.selectedEventId === id ? null : id
    console.log('[ai-advice] toggleEvent:', { id, selectedEventId, prevId: this.data.selectedEventId })
    this.setData({ selectedEventId })
  },

  /**
   * 阻止事件冒泡
   */
  stopPropagation() {
    // 空方法，用于阻止点击事件冒泡
  },

  /**
   * 提交咨询
   */
  async handleSubmit() {
    const { question, conversationMode, selectedConversationId, reportMode, selectedReportIds, medicationMode, selectedMedicationIds, eventMode, selectedEventId } = this.data

    if (!question.trim()) {
      return util.showToast('请输入问题')
    }

    if (question.length < 5) {
      return util.showToast('请详细描述您的问题，至少5个字符')
    }

    // 准备请求数据（与网页端API格式一致）
    const requestData = {
      question: question.trim(),
      conversation_mode: conversationMode === 'continue' ? 'continue_conversation' : 'new_conversation',
      report_mode: reportMode === 'none' ? 'no_reports' : 'select',
      medication_mode: medicationMode === 'none' ? 'no_medications' : 'select'
    }

    // 处理对话ID
    if (conversationMode === 'continue' && selectedConversationId) {
      requestData.conversation_id = selectedConversationId
      console.log('[小程序] 继续对话模式 - conversation_id:', selectedConversationId)
    } else {
      console.log('[小程序] 新对话模式')
    }

    // 处理报告选择 - 使用selected_report_ids（与网页端一致）
    if (reportMode === 'select' && selectedReportIds.length > 0) {
      requestData.selected_report_ids = selectedReportIds
    }

    // 处理药单选择 - 使用selected_medication_ids（与网页端一致）
    if (medicationMode === 'select' && selectedMedicationIds.length > 0) {
      requestData.selected_medication_ids = selectedMedicationIds
    }

    // 处理健康事件选择
    if (eventMode === 'select' && selectedEventId) {
      requestData.selected_event = selectedEventId
      requestData.event_mode = 'select_event'
      console.log('[小程序] 选择了健康事件:', selectedEventId)
    } else {
      requestData.event_mode = 'no_event'
      console.log('[小程序] 未选择健康事件, eventMode:', eventMode, 'selectedEventId:', selectedEventId)
    }

    console.log('[小程序] 提交咨询，请求数据:', JSON.stringify({
      ...requestData,
      conversation_id: requestData.conversation_id || '(none)'
    }))

    this.setData({ submitting: true })
    util.showLoading('正在跳转...')

    try {
      // 将请求数据保存到缓存，供对话页面使用
      wx.setStorageSync('pendingAdviceRequest', requestData)

      util.hideLoading()

      // 立即跳转到对话页面（不带ID，让对话页面自己创建）
      wx.redirectTo({
        url: `/pages/conversation/conversation?new=true&data=1`
      })

    } catch (err) {
      console.error('跳转失败:', err)
      util.hideLoading()
      this.setData({ submitting: false })
      util.showToast('跳转失败，请重试')
    }
  }
})
