/**
 * 系统设置页面
 */

const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    userInfo: {},
    userProfile: {},
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
      today: `${year}-${month}-${day}`
    })

    this.loadUserProfile()
  },

  /**
   * 选择头像
   */
  async chooseAvatar() {
    try {
      const res = await wx.getUserProfile({
        desc: '用于完善用户资料'
      })

      const avatarUrl = res.userInfo.avatarUrl
      console.log('获取到头像:', avatarUrl)

      // 保存到本地存储
      wx.setStorageSync('wechat_avatar', avatarUrl)

      // 更新页面显示
      this.setData({
        'userInfo.avatar_url': avatarUrl
      })

      util.showToast('头像已更新')
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

  /**
   * 加载用户个人信息
   */
  async loadUserProfile() {
    try {
      // 从本地存储读取微信头像
      const wechatAvatar = wx.getStorageSync('wechat_avatar') || ''

      const res = await api.getUserInfo()
      const user = res.user

      // 使用微信头像
      if (wechatAvatar) {
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
        userInfo: user
      })
    } catch (err) {
      console.error('加载用户信息失败:', err)
    }
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
      content: '版本：2.0.0\n\n个人健康管理系统，基于AI技术提供智能健康建议。',
      showCancel: false,
      confirmText: '知道了'
    })
  }
})
