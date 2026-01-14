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

    // 输入
    question: '',
    submitting: false
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
      const [conversationsRes, reportsRes] = await Promise.all([
        api.getConversations(),
        api.getCheckups({ page_size: 100 })
      ])

      const conversations = conversationsRes.data || []
      const reports = reportsRes.data || reportsRes.results || []

      this.setData({
        conversations,
        reports: reports.map(r => ({ ...r, selected: false }))
      })
    } catch (err) {
      console.error('加载数据失败:', err)
      util.showToast('加载失败')
    } finally {
      util.hideLoading()
    }
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
   * 问题输入
   */
  onQuestionInput(e) {
    this.setData({ question: e.detail.value })
  },

  /**
   * 提交咨询
   */
  async handleSubmit() {
    const { question, conversationMode, selectedConversationId, reportMode, selectedReportIds } = this.data

    if (!question.trim()) {
      return util.showToast('请输入问题')
    }

    if (question.length < 5) {
      return util.showToast('请详细描述您的问题，至少5个字符')
    }

    // 准备请求数据
    const requestData = {
      question: question.trim(),
      report_mode: reportMode
    }

    // 处理报告选择 - 如果选择了报告，添加到请求数据
    if (reportMode === 'select' && selectedReportIds.length > 0) {
      requestData.selected_reports = selectedReportIds
    }

    // 处理对话模式 - 如果是继续对话，添加conversation_id
    if (conversationMode === 'continue' && selectedConversationId) {
      requestData.conversation_id = selectedConversationId
    }

    this.setData({ submitting: true })
    util.showLoading('AI正在分析...')

    try {
      // 使用对话创建API
      const res = await api.createConversation(requestData)

      util.hideLoading()

      // 立即跳转到对话详情页（AI在后台生成中）
      const conversationId = res.conversation_id || res.data?.conversation_id || res.id || res.data?.id
      const adviceId = res.advice_id || res.data?.advice_id

      if (conversationId) {
        util.showToast('已创建对话，AI正在思考中...')
        setTimeout(() => {
          const params = `id=${conversationId}&generating=true`
          if (adviceId) {
            wx.navigateTo({
              url: `/pages/conversation/conversation?${params}&adviceId=${adviceId}`
            })
          } else {
            wx.navigateTo({
              url: `/pages/conversation/conversation?${params}`
            })
          }
        }, 300)
      } else {
        util.showToast('创建对话失败')
      }

    } catch (err) {
      console.error('提交失败:', err)
      util.showToast(err.message || '提交失败，请重试')
    } finally {
      this.setData({ submitting: false })
      util.hideLoading()
    }
  }
})
