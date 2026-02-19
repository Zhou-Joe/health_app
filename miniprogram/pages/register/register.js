const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    username: '',
    password: '',
    confirmPassword: '',
    nickname: '',
    loading: false,
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

  onNicknameInput(e) {
    this.setData({ nickname: e.detail.value })
  },

  toggleAgreement() {
    this.setData({
      agreed: !this.data.agreed
    })
  },

  async handleRegister() {
    if (!this.data.agreed) {
      util.showToast('请先阅读并同意用户协议和隐私政策')
      return
    }

    const { username, password, confirmPassword, nickname } = this.data

    if (!username || !username.trim()) {
      util.showToast('请输入用户名')
      return
    }

    if (username.length < 3 || username.length > 20) {
      util.showToast('用户名需要3-20位')
      return
    }

    if (!password) {
      util.showToast('请输入密码')
      return
    }

    if (password.length < 6) {
      util.showToast('密码至少6位')
      return
    }

    if (!confirmPassword) {
      util.showToast('请确认密码')
      return
    }

    if (password !== confirmPassword) {
      util.showToast('两次输入的密码不一致')
      return
    }

    this.setData({ loading: true })

    try {
      const res = await api.register({
        username: username.trim(),
        password: password,
        nickname: nickname.trim() || username.trim()
      })

      app.setLoginInfo(res.token, res.user)
      util.showToast('注册成功')

      setTimeout(() => {
        wx.reLaunch({
          url: '/pages/dashboard/dashboard'
        })
      }, 1000)
    } catch (err) {
      util.showToast(err.message || '注册失败')
    } finally {
      this.setData({ loading: false })
    }
  },

  goToLogin() {
    wx.navigateBack()
  },

  showUserAgreement() {
    wx.showModal({
      title: '用户协议',
      content: '欢迎使用我的健康档案！请您仔细阅读以下条款：\n\n一、服务说明\n本平台为用户提供健康档案管理、健康数据分析、AI健康咨询等服务。AI建议仅供参考，不构成医疗诊断或治疗方案。\n\n二、用户义务\n1. 请妥善保管您的账号和密码，注意账号安全\n2. 合理使用平台服务，请勿恶意攻击或干扰系统运行\n\n三、知识产权\n平台内容版权归本平台所有，未经授权不得复制、传播。\n\n四、免责声明\n1. 因用户提供信息不准确导致的后果，平台不承担责任\n2. AI健康建议仅供参考，具体诊疗请遵医嘱',
      showCancel: false,
      confirmText: '我知道了'
    })
  },

  showPrivacyPolicy() {
    wx.showModal({
      title: '隐私政策',
      content: '我们深知个人信息对您的重要性，将依法采取相应安全保护措施：\n\n一、信息收集\n所有个人信息均由用户自愿选择上传，平台不强制要求提供。\n\n二、信息使用\n1. 提供健康咨询和管理服务\n2. 改进产品功能和用户体验\n\n三、信息保护\n1. 采用SSL加密技术传输数据\n2. 严格的数据访问权限控制\n\n四、信息共享\n未经您同意，我们不会向第三方共享您的个人信息。',
      showCancel: false,
      confirmText: '我知道了'
    })
  }
})
