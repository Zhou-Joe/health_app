// pages/bind-account/bind-account.js
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    username: '',
    password: '',
    confirmPassword: '',
    submitting: false,
    agreed: false
  },

  onUsernameInput(e) {
    this.setData({ username: e.detail.value })
  },

  onPasswordInput(e) {
    this.setData({ password: e.detail.value })
  },

  onConfirmPasswordInput(e) {
    this.setData({ confirmPassword: e.detail.value })
  },

  toggleAgreement() {
    this.setData({
      agreed: !this.data.agreed
    })
  },

  async handleSubmit() {
    if (!this.data.agreed) {
      util.showToast('请先阅读并同意用户协议')
      return
    }

    const username = this.data.username.trim()
    const password = this.data.password
    const confirmPassword = this.data.confirmPassword

    if (!username) {
      util.showToast('请输入用户名')
      return
    }

    if (username.length < 3 || username.length > 20) {
      util.showToast('用户名需要3-20位')
      return
    }

    if (!/^[a-zA-Z0-9]+$/.test(username)) {
      util.showToast('用户名只能包含字母和数字')
      return
    }

    if (!password) {
      util.showToast('请输入密码')
      return
    }

    if (password.length < 6) {
      util.showToast('密码至少需要6位')
      return
    }

    if (password !== confirmPassword) {
      util.showToast('两次密码输入不一致')
      return
    }

    this.setData({ submitting: true })

    try {
      const res = await api.bindUsername({
        username: username,
        password: password
      })

      if (res.success) {
        util.showToast('绑定成功', 'success')
        
        const userInfo = wx.getStorageSync('userInfo') || {}
        userInfo.username = username
        wx.setStorageSync('userInfo', userInfo)
        
        setTimeout(() => {
          wx.navigateBack()
        }, 1500)
      } else {
        util.showToast(res.message || '绑定失败')
      }
    } catch (err) {
      util.showToast(err.message || '绑定失败')
    } finally {
      this.setData({ submitting: false })
    }
  },

  showUserAgreement() {
    wx.showModal({
      title: '用户协议',
      content: '一、服务说明\n本平台为用户提供健康档案管理、健康数据分析、AI健康咨询等服务。\n\n二、账号安全\n请妥善保管您的账号和密码，账号绑定后可用于网页端和其他平台登录。\n\n三、免责声明\nAI健康建议仅供参考，具体诊疗请遵医嘱。',
      showCancel: false,
      confirmText: '我知道了'
    })
  },

  skipBind() {
    wx.navigateBack()
  }
})
