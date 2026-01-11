/**
 * 小程序主入口
 */

const config = require('./config.js')

App({
  globalData: {
    userInfo: null,
    token: null,
    isLogin: false,
    // 从配置文件读取
    baseUrl: config.server.baseUrl
  },

  onLaunch() {
    console.log('小程序启动')
    this.checkLogin()
    this.checkUpdate()
  },

  onShow() {
    console.log('小程序显示')
  },

  onHide() {
    console.log('小程序隐藏')
  },

  /**
   * 检查登录状态
   */
  checkLogin() {
    const token = wx.getStorageSync(config.storageKeys.TOKEN)
    const userInfo = wx.getStorageSync(config.storageKeys.USER_INFO)

    if (token && userInfo) {
      this.globalData.token = token
      this.globalData.userInfo = userInfo
      this.globalData.isLogin = true
    }
  },

  /**
   * 设置登录信息
   */
  setLoginInfo(token, userInfo) {
    this.globalData.token = token
    this.globalData.userInfo = userInfo
    this.globalData.isLogin = true

    wx.setStorageSync(config.storageKeys.TOKEN, token)
    wx.setStorageSync(config.storageKeys.USER_INFO, userInfo)
  },

  /**
   * 清除登录信息
   */
  clearLoginInfo() {
    this.globalData.token = null
    this.globalData.userInfo = null
    this.globalData.isLogin = false

    wx.removeStorageSync(config.storageKeys.TOKEN)
    wx.removeStorageSync(config.storageKeys.USER_INFO)
  },

  /**
   * 检查小程序更新
   */
  checkUpdate() {
    if (wx.canIUse('getUpdateManager')) {
      const updateManager = wx.getUpdateManager()

      updateManager.onCheckForUpdate((res) => {
        if (res.hasUpdate) {
          console.log('发现新版本')
        }
      })

      updateManager.onUpdateReady(() => {
        wx.showModal({
          title: '更新提示',
          content: '新版本已准备好，是否重启应用？',
          success: (res) => {
            if (res.confirm) {
              updateManager.applyUpdate()
            }
          }
        })
      })

      updateManager.onUpdateFailed(() => {
        console.error('新版本下载失败')
      })
    }
  },

  /**
   * 获取用户信息（如果需要）
   */
  getUserInfo() {
    return this.globalData.userInfo
  },

  /**
   * 检查是否登录
   */
  isLoggedIn() {
    return this.globalData.isLogin
  },

  /**
   * 获取Token
   */
  getToken() {
    return this.globalData.token
  }
})
