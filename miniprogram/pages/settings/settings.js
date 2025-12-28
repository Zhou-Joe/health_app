const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    userInfo: {},
    baseUrl: ''
  },

  onLoad() {
    const app = getApp()
    this.setData({
      userInfo: app.globalData.userInfo || {},
      baseUrl: app.globalData.baseUrl
    })
  },

  goToProfile() {
    util.showToast('个人信息功能开发中')
  },

  async checkServices() {
    util.showLoading()
    try {
      const res = await api.getServicesStatus()
      wx.showModal({
        title: '服务状态',
        content: `OCR: ${res.services[0]?.status}\nLLM: ${res.services[1]?.status}\nAI医生: ${res.services[2]?.status}`,
        showCancel: false
      })
    } catch (err) {
      util.showToast('检查失败')
    } finally {
      util.hideLoading()
    }
  },

  handleLogout() {
    util.showConfirm('确定要退出登录吗？').then(confirm => {
      if (confirm) {
        app.clearLoginInfo()
        wx.reLaunch({ url: '/pages/login/login' })
      }
    })
  }
})
