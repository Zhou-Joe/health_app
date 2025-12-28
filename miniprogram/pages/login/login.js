// pages/login/login.js
const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    username: '',
    password: '',
    loading: false
  },

  onUsernameInput(e) {
    this.setData({ username: e.detail.value })
  },

  onPasswordInput(e) {
    this.setData({ password: e.detail.value })
  },

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
      util.showToast('登录成功', 'success')

      setTimeout(() => {
        wx.switchTab({
          url: '/pages/dashboard/dashboard'
        })
      }, 1000)
    } catch (err) {
      util.showToast(err.message || '登录失败')
    } finally {
      this.setData({ loading: false })
    }
  }
})
