// pages/login/login.js
const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    username: '',
    password: '',
    loading: false,
    wechatLoading: false,
    showModal: false,
    modalTitle: '',
    modalContent: '',
    agreed: false
  },

  onUsernameInput(e) {
    this.setData({ username: e.detail.value })
  },

  onPasswordInput(e) {
    this.setData({ password: e.detail.value })
  },

  // 切换协议勾选状态
  toggleAgreement() {
    this.setData({
      agreed: !this.data.agreed
    })
  },

  // 阻止checkbox事件冒泡
  stopCheckboxEvent(e) {
    // 阻止事件冒泡，防止触发toggleAgreement
  },

  // 账号密码登录
  async handleLogin() {
    if (!this.data.agreed) {
      util.showToast('请先阅读并同意用户协议和隐私政策')
      return
    }

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
      util.showToast('登录成功')

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
    if (!this.data.agreed) {
      util.showToast('请先阅读并同意用户协议和隐私政策')
      return
    }

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
        util.showToast('登录成功')
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
  },

  // 显示用户协议
  showUserAgreement() {
    this.setData({
      modalTitle: '用户协议',
      modalContent: '欢迎使用我的健康档案！请您仔细阅读以下条款：\n\n一、服务说明\n本平台为用户提供健康档案管理、健康数据分析、AI健康咨询等服务。AI建议仅供参考，不构成医疗诊断或治疗方案。\n\n二、用户义务\n1. 请妥善保管您的账号和密码，注意账号安全\n2. 合理使用平台服务，请勿恶意攻击或干扰系统运行\n\n三、知识产权\n平台内容（包括但不限于文字、图片、软件等）版权归本平台所有，未经授权不得复制、传播。\n\n四、免责声明\n1. 因用户提供信息不准确导致的后果，平台不承担责任\n2. 因不可抗力导致的服务中断，平台不承担责任\n3. AI健康建议仅供参考，具体诊疗请遵医嘱\n\n五、服务变更与终止\n平台保留修改或中断服务的权利，用户如有异议可停止使用。\n\n六、协议修改\n本平台有权根据需要修改协议条款，修改后的协议一经公布即生效。',
      showModal: true
    })
  },

  // 显示隐私政策
  showPrivacyPolicy() {
    this.setData({
      modalTitle: '隐私政策',
      modalContent: '我们深知个人信息对您的重要性，将依法采取相应安全保护措施：\n\n一、信息收集\n本平台尊重用户隐私，所有个人信息（包括体检报告、健康指标等）均由用户自愿选择上传，平台不强制要求提供。\n\n二、信息使用\n1. 提供健康咨询和管理服务\n2. 改进产品功能和用户体验\n3. 数据统计和分析（不包含个人身份信息）\n4. 安全防范和欺诈检测\n\n三、信息保护\n1. 采用SSL加密技术传输数据\n2. 严格的数据访问权限控制\n3. 定期进行安全审计和漏洞检测\n\n四、信息共享\n未经您同意，我们不会向第三方共享您的个人信息。法律规定必须提供的情况除外。\n\n五、信息存储\n您的信息将存储于中华人民共和国境内的服务器。\n\n六、您的权利\n您有权访问、更正、删除您的个人信息，可通过设置页面操作或联系客服。',
      showModal: true
    })
  },

  // 隐藏弹窗
  hideModal() {
    this.setData({
      showModal: false
    })
  },

  // 阻止冒泡
  stopPropagation() {
    // 阻止点击事件冒泡，防止关闭弹窗
  }
})
