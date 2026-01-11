/**
 * 系统设置页面
 */

const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')
const config = require('../../config.js')

Page({
  data: {
    userInfo: {},
    serverUrl: config.server.baseUrl,
    systemSettings: {},
    servicesStatus: {},
    loading: false
  },

  onLoad() {
    this.setData({
      userInfo: app.globalData.userInfo || {},
      serverUrl: config.server.baseUrl
    })
    this.loadSystemSettings()
    this.checkServicesStatus()
  },

  /**
   * 加载系统设置
   */
  async loadSystemSettings() {
    try {
      const res = await api.getSystemSettings()
      this.setData({ systemSettings: res.data || res })
    } catch (err) {
      console.error('加载系统设置失败:', err)
    }
  },

  /**
   * 检查服务状态
   */
  async checkServicesStatus() {
    util.showLoading('检查中...')
    try {
      const res = await api.getServicesStatus()
      this.setData({ servicesStatus: res })
    } catch (err) {
      console.error('检查服务状态失败:', err)
      util.showToast('检查失败')
    } finally {
      util.hideLoading()
    }
  },

  /**
   * 服务器地址变更
   */
  onServerUrlChange(e) {
    this.setData({ serverUrl: e.detail.value })
  },

  /**
   * 保存服务器地址
   */
  saveServerUrl() {
    const url = this.data.serverUrl.trim()
    if (!url) {
      util.showToast('请输入服务器地址')
      return
    }

    // 这里应该保存到本地存储并更新config
    wx.setStorageSync('serverUrl', url)
    util.showToast('已保存，请重启小程序生效', 'success')
  },

  /**
   * 清除缓存
   */
  async clearCache() {
    const confirm = await util.showConfirm('确定要清除所有缓存吗？')
    if (!confirm) return

    try {
      wx.clearStorageSync()
      util.showToast('缓存已清除', 'success')

      // 重新加载登录信息
      app.checkLogin()
    } catch (err) {
      util.showToast('清除失败')
    }
  },

  /**
   * 退出登录
   */
  async handleLogout() {
    const confirm = await util.showConfirm('确定要退出登录吗？')
    if (!confirm) return

    app.clearLoginInfo()
    util.showToast('已退出登录', 'success')
    setTimeout(() => {
      wx.reLaunch({ url: '/pages/login/login' })
    }, 500)
  },

  /**
   * 查看关于
   */
  showAbout() {
    wx.showModal({
      title: '关于健康档案',
      content: '版本：1.0.0\n\n个人健康管理系统，基于AI技术提供智能健康建议。',
      showCancel: false,
      confirmText: '知道了'
    })
  },

  /**
   * 测试连接
   */
  async testConnection() {
    util.showLoading('测试连接...')
    try {
      await api.getSystemSettings()
      util.showToast('连接成功', 'success')
    } catch (err) {
      util.showToast('连接失败')
    } finally {
      util.hideLoading()
    }
  }
})
