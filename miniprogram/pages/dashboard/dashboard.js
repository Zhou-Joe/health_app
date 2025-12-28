// pages/dashboard/dashboard.js
const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    userInfo: {},
    stats: {
      checkupCount: 0,
      indicatorCount: 0,
      conversationCount: 0
    },
    recentCheckups: []
  },

  onLoad() {
    this.checkLogin()
    this.loadData()
  },

  onShow() {
    this.loadData()
  },

  checkLogin() {
    if (!app.globalData.isLogin) {
      wx.reLaunch({ url: '/pages/login/login' })
    }
  },

  async loadData() {
    util.showLoading()
    try {
      this.setData({ userInfo: app.globalData.userInfo })

      const [checkupsRes, conversationsRes] = await Promise.all([
        api.getCheckups({ page: 1, page_size: 3 }),
        api.getConversations()
      ])

      const checkups = checkupsRes.data || []
      let indicatorCount = 0
      checkups.forEach(c => {
        indicatorCount += c.indicators_count || 0
      })

      this.setData({
        recentCheckups: checkups,
        stats: {
          checkupCount: checkupsRes.total || 0,
          indicatorCount: indicatorCount,
          conversationCount: conversationsRes.total || 0
        }
      })
    } catch (err) {
      console.error('加载数据失败:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
    }
  },

  goToCheckups() {
    wx.switchTab({ url: '/pages/checkups/checkups' })
  },

  goToIndicators() {
    wx.switchTab({ url: '/pages/checkups/checkups' })
  },

  goToConversations() {
    wx.switchTab({ url: '/pages/ai-advice/ai-advice' })
  },

  goToUpload() {
    wx.switchTab({ url: '/pages/upload/upload' })
  },

  goToIntegration() {
    wx.navigateTo({ url: '/pages/integration/integration' })
  },

  goToAIAdvice() {
    wx.switchTab({ url: '/pages/ai-advice/ai-advice' })
  },

  goToManualInput() {
    wx.navigateTo({ url: '/pages/indicator-edit/indicator-edit' })
  },

  goToCheckupDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/checkup-detail/checkup-detail?id=${id}` })
  }
})
