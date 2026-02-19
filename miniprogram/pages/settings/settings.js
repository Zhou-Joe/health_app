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
    userProfile: {},
    canChooseAvatar: false,
    avatarLoadFailed: false,
    showEditModal: false,
    editField: {},
    editValue: '',
    saving: false,
    today: ''
  },

  onLoad() {
    // 设置今天的日期
    const today = new Date()
    const year = today.getFullYear()
    const month = String(today.getMonth() + 1).padStart(2, '0')
    const day = String(today.getDate()).padStart(2, '0')

    this.setData({
      today: `${year}-${month}-${day}`,
      canChooseAvatar: wx.canIUse('button.open-type.chooseAvatar')
    })

    this.loadUserProfile()
  },

  async onChooseAvatar(e) {
    const avatarUrl = this.normalizeAvatarUrl(e?.detail?.avatarUrl)
    if (!avatarUrl) {
      util.showToast('未获取到头像，请重试')
      return
    }
    console.log('chooseAvatar返回:', avatarUrl)
    await this.applyAvatar(avatarUrl)
  },

  /**
   * 选择头像
   */
  async chooseAvatar() {
    try {
      const res = await wx.getUserProfile({
        desc: '用于完善用户资料'
      })

      const avatarUrl = this.normalizeAvatarUrl(res.userInfo.avatarUrl)
      await this.applyAvatar(avatarUrl)
    } catch (err) {
      console.log('获取头像失败:', err)
      // 用户取消授权
      if (err.errMsg && err.errMsg.includes('cancel')) {
        util.showToast('您取消了授权')
      } else {
        util.showToast('获取头像失败')
      }
    }
  },

  async applyAvatar(avatarUrl) {
    console.log('获取到头像:', avatarUrl)

    // 先更新本地显示，使用临时路径
    this.setData({
      'userInfo.avatar_url': avatarUrl,
      avatarLoadFailed: false
    })

    try {
      // 上传文件到服务器
      util.showToast('正在上传头像...')
      const res = await api.uploadAvatar(avatarUrl)

      // 使用服务器返回的URL
      const serverAvatarUrl = res.avatar_url
      console.log('头像上传成功，服务器URL:', serverAvatarUrl)

      // 保存到本地存储
      wx.setStorageSync('wechat_avatar', serverAvatarUrl)

      // 更新全局用户信息
      const mergedUserInfo = {
        ...(app.globalData.userInfo || {}),
        avatar_url: serverAvatarUrl
      }
      app.globalData.userInfo = mergedUserInfo
      wx.setStorageSync(config.storageKeys.USER_INFO, mergedUserInfo)

      this.setData({
        'userInfo.avatar_url': serverAvatarUrl
      })

      util.showToast('头像已更新')
    } catch (err) {
      console.error('头像上传失败:', err)
      util.showToast(err.message || '头像上传失败')
      // 上传失败时保留临时路径
    }
  },

  /**
   * 加载用户个人信息
   */
  async loadUserProfile() {
    try {
      // 从本地存储读取微信头像
      const wechatAvatar = wx.getStorageSync('wechat_avatar') || ''

      const res = await api.getUserInfo()
      const user = res.user

      // 优先后端头像，无后端时回退本地微信头像
      if (!user.avatar_url && wechatAvatar) {
        user.avatar_url = wechatAvatar
      }

      console.log('用户信息:', user)

      // 计算年龄显示
      let ageDisplay = '未知'
      if (user.birth_date) {
        // 后端已经计算好了age，直接使用
        // 注意：age可能是0，所以使用 !== null 判断
        if (user.age !== null && user.age !== undefined) {
          ageDisplay = `${user.age}岁`
        } else {
          ageDisplay = '未知'
        }
      } else {
        ageDisplay = '未知'
      }

      // 构建用户profile数据
      const userProfile = {
        nickname: user.first_name || '',
        gender: user.gender || '',
        genderDisplay: this.getGenderDisplay(user.gender),
        birthDate: user.birth_date || '',
        age: ageDisplay
      }


      this.setData({
        userProfile,
        userInfo: user,
        avatarLoadFailed: false
      })

      app.globalData.userInfo = user
      wx.setStorageSync(config.storageKeys.USER_INFO, user)
    } catch (err) {
      console.error('加载用户信息失败:', err)
      const cachedUser = wx.getStorageSync(config.storageKeys.USER_INFO) || {}
      const localAvatar = wx.getStorageSync('wechat_avatar') || ''
      if (!cachedUser.avatar_url && localAvatar) {
        cachedUser.avatar_url = localAvatar
      }
      this.setData({
        userInfo: cachedUser,
        avatarLoadFailed: false
      })
    }
  },

  normalizeAvatarUrl(url) {
    if (!url) return ''
    return String(url).trim()
  },

  onAvatarError(e) {
    console.error('头像加载失败:', e)
    this.setData({ avatarLoadFailed: true })
    util.showToast('头像加载失败，请配置图片域名')
  },

  /**
   * 获取性别显示文本
   */
  getGenderDisplay(gender) {
    if (!gender) return '未设置'
    return gender === 'male' ? '男' : '女'
  },

  /**
   * 编辑昵称
   */
  editNickname() {
    this.setData({
      showEditModal: true,
      editField: { key: 'nickname', label: '昵称' },
      editValue: this.data.userProfile.nickname || ''
    })
  },

  /**
   * 编辑性别
   */
  editGender() {
    this.setData({
      showEditModal: true,
      editField: { key: 'gender', label: '性别' },
      editValue: this.data.userProfile.gender || ''
    })
  },

  /**
   * 编辑出生日期
   */
  editBirthDate() {
    this.setData({
      showEditModal: true,
      editField: { key: 'birthDate', label: '出生日期' },
      editValue: this.data.userProfile.birthDate || ''
    })
  },

  /**
   * 输入框输入事件
   */
  onEditInput(e) {
    this.setData({ editValue: e.detail.value })
  },

  /**
   * 选择性别
   */
  selectGender(e) {
    const gender = e.currentTarget.dataset.value
    this.setData({ editValue: gender })
  },

  /**
   * 出生日期变更
   */
  onBirthDateChange(e) {
    this.setData({ editValue: e.detail.value })
  },

  /**
   * 保存编辑
   */
  async saveEdit() {
    const { editField, editValue } = this.data


    // 验证
    if (editField.key === 'nickname') {
      if (!editValue || !editValue.trim()) {
        util.showToast('请输入昵称')
        return
      }
    }

    if (editField.key === 'gender') {
      if (!editValue) {
        util.showToast('请选择性别')
        return
      }
    }

    if (editField.key === 'birthDate') {
      if (!editValue) {
        util.showToast('请选择出生日期')
        return
      }
    }

    this.setData({ saving: true })

    try {
      // 调用完善个人信息API
      const data = {
        nickname: this.data.userProfile.nickname,
        gender: this.data.userProfile.gender,
        birth_date: this.data.userProfile.birthDate
      }

      // 更新当前编辑的字段
      // 注意：需要映射驼峰命名到下划线命名
      if (editField.key === 'birthDate') {
        data.birth_date = editValue
      } else if (editField.key === 'nickname') {
        data.nickname = editValue
      } else if (editField.key === 'gender') {
        data.gender = editValue
      }


      const res = await api.completeProfile(data)

      util.showToast('保存成功')

      // 关闭弹窗并重新加载数据
      this.closeModal()
      setTimeout(() => {
        this.loadUserProfile()
      }, 1000)
    } catch (err) {
      console.error('[保存] 保存失败:', err)
      console.error('[保存] 错误详情:', JSON.stringify(err, null, 2))
      util.showToast(err.message || '保存失败')
    } finally {
      this.setData({ saving: false })
    }
  },

  /**
   * 关闭弹窗
   */
  closeModal() {
    this.setData({
      showEditModal: false,
      editField: {},
      editValue: ''
    })
  },

  /**
   * 阻止冒泡
   */
  stopPropagation() {
    // 空函数，用于阻止事件冒泡
  },

  /**
   * 退出登录
   */
  async handleLogout() {
    const confirm = await util.showConfirm('确定要退出登录吗？')
    if (!confirm) return

    app.clearLoginInfo()
    util.showToast('已退出登录')
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
      content: '版本：2.0\n\n个人健康管理系统，基于AI技术提供智能健康建议。',
      showCancel: false,
      confirmText: '知道了'
    })
  },

  navigateToChangePassword() {
    wx.navigateTo({
      url: '/pages/change-password/change-password'
    })
  },

  navigateToManualEntry() {
    wx.navigateTo({
      url: '/pages/manual-entry/manual-entry'
    })
  },

  navigateToHelpFeedback() {
    wx.navigateTo({
      url: '/pages/help-feedback/help-feedback'
    })
  },

  navigateToSymptomLogs() {
    wx.navigateTo({
      url: '/pages/symptom-logs/symptom-logs'
    })
  },

  navigateToVitalLogs() {
    wx.navigateTo({
      url: '/pages/vital-logs/vital-logs'
    })
  }
})
