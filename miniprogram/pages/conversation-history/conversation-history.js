/**
 * 对话历史列表页面
 * 显示所有AI咨询历史记录
 */

const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    conversations: [],
    loading: false
  },

  onLoad() {
    this.loadConversations()
  },

  onShow() {
    // 每次显示页面时刷新列表
    this.loadConversations()
  },

  /**
   * 加载对话列表
   */
  async loadConversations() {
    if (this.data.loading) return

    this.setData({ loading: true })
    util.showLoading('加载中...')

    try {
      const res = await api.getConversations()
      const conversations = (res.data || []).map(conv => ({
        ...conv,
        created_at: this.formatDate(conv.created_at)
      }))

      this.setData({ conversations })
    } catch (err) {
      console.error('加载对话列表失败:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      this.setData({ loading: false })
      util.hideLoading()
    }
  },

  /**
   * 格式化日期
   */
  formatDate(dateStr) {
    if (!dateStr) return ''

    const date = new Date(dateStr)
    const now = new Date()
    const diff = now - date

    // 小于1分钟
    if (diff < 60000) {
      return '刚刚'
    }

    // 小于1小时
    if (diff < 3600000) {
      return `${Math.floor(diff / 60000)}分钟前`
    }

    // 小于24小时
    if (diff < 86400000) {
      return `${Math.floor(diff / 3600000)}小时前`
    }

    // 小于7天
    if (diff < 604800000) {
      return `${Math.floor(diff / 86400000)}天前`
    }

    // 超过7天，显示具体日期
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')

    return `${year}-${month}-${day}`
  },

  /**
   * 跳转到对话详情
   */
  goToConversation(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: `/pages/conversation/conversation?id=${id}`
    })
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
      util.showToast('删除成功', 'success')

      // 从列表中移除
      const conversations = this.data.conversations.filter(c => c.id !== id)
      this.setData({ conversations })
    } catch (err) {
      console.error('删除失败:', err)
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  },

  /**
   * 跳转到AI咨询页面
   */
  goToAIAdvice() {
    wx.navigateTo({
      url: '/pages/ai-advice/ai-advice'
    })
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    this.loadConversations().then(() => {
      wx.stopPullDownRefresh()
    })
  }
})
