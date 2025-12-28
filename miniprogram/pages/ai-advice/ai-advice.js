const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: { conversations: [] },

  onLoad() { this.loadConversations() },

  async loadConversations() {
    util.showLoading()
    try {
      const res = await api.getConversations()
      const conversations = (res.data || []).map(c => ({
        ...c,
        updated_at: util.formatDate(c.updated_at, 'MM-DD HH:mm')
      }))
      this.setData({ conversations })
    } catch (err) {
      console.error(err)
    } finally {
      util.hideLoading()
    }
  },

  startNewChat() {
    wx.navigateTo({ url: '/pages/conversation/conversation' })
  },

  openChat(e) {
    wx.navigateTo({ url: `/pages/conversation/conversation?id=${e.currentTarget.dataset.id}` })
  },

  viewHistory() {
    // 显示所有历史对话，已在列表中
  },

  async deleteChat(e) {
    const id = e.currentTarget.dataset.id
    const confirm = await util.showConfirm('确定删除此对话吗？')
    if (!confirm) return

    util.showLoading()
    try {
      await api.deleteConversation(id)
      util.showToast('删除成功', 'success')
      this.setData({ conversations: [] })
      this.loadConversations()
    } catch (err) {
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  }
})
