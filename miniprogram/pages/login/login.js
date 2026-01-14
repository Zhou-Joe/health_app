// pages/login/login.js
const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    username: '',
    password: '',
    loading: false,
    wechatLoading: false
  },

  onUsernameInput(e) {
    this.setData({ username: e.detail.value })
  },

  onPasswordInput(e) {
    this.setData({ password: e.detail.value })
  },

  // 账号密码登录
  async handleLogin() {
    if (!this.data.username || !this.data.password) {
      util.showToast('请输入用户名和密码')
      return
    }

    this.setData({ loading: true })

    try {
      const res = await api.login({
        username: this.data.username,
        password: this.data.password
      })

      app.setLoginInfo(res.token, res.user)
      util.showToast('登录成功'))

      setTimeout(() => {
        wx.reLaunch({
          url: '/pages/dashboard/dashboard'
        })
      }, 1000)
    } catch (err) {
      util.showToast(err.message || '登录失败')
    } finally {
      this.setData({ loading: false })
    }
  },

  // 微信一键登录
  async handleWechatLogin() {
    this.setData({ wechatLoading: true })

    try {
      // 1. 获取微信登录code
      const loginRes = await wx.login()

      if (!loginRes.code) {
        throw new Error('获取微信登录code失败')
      }

      // 2. 获取用户信息（可选）
      let userInfo = {}
      try {
        const userProfile = await wx.getUserProfile({
          desc: '用于完善用户资料'
        })
        userInfo = {
          nickname: userProfile.userInfo.nickName,
          avatarUrl: userProfile.userInfo.avatarUrl
        }
      } catch (err) {
        console.log('用户拒绝授权，使用默认信息')
        userInfo = {
          nickname: '微信用户'
        }
      }

      // 3. 调用后端登录API
      const res = await api.wechatLogin({
        code: loginRes.code,
        ...userInfo
      })

      // 4. 保存登录信息
      app.setLoginInfo(res.token, res.user)

      // 5. 判断是否需要完善个人信息
      if (res.need_complete_profile) {
        util.showToast('首次登录，请完善个人信息', 'none', 2000)
        setTimeout(() => {
          wx.redirectTo({
            url: '/pages/complete-profile/complete-profile'
          })
        }, 1500)
      } else {
        util.showToast('登录成功'))
        setTimeout(() => {
          wx.reLaunch({
            url: '/pages/dashboard/dashboard'
          })
        }, 1000)
      }
    } catch (err) {
      console.error('微信登录失败:', err)
      util.showToast(err.message || '微信登录失败')
    } finally {
      this.setData({ wechatLoading: false })
    }
  }
})
