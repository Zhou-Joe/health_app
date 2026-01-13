// pages/complete-profile/complete-profile.js
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    nickname: '',
    gender: '',
    birthDate: '',
    today: '',
    submitting: false
  },

  onLoad() {
    // 设置今天的日期
    const today = new Date()
    const year = today.getFullYear()
    const month = String(today.getMonth() + 1).padStart(2, '0')
    const day = String(today.getDate()).padStart(2, '0')
    this.setData({ today: `${year}-${month}-${day}` })
  },

  onNicknameInput(e) {
    this.setData({ nickname: e.detail.value })
  },

  selectGender(e) {
    const gender = e.currentTarget.dataset.gender
    this.setData({ gender })
  },

  onBirthDateChange(e) {
    this.setData({ birthDate: e.detail.value })
  },

  async handleSubmit() {
    // 验证表单
    if (!this.data.nickname.trim()) {
      util.showToast('请输入昵称')
      return
    }

    if (!this.data.gender) {
      util.showToast('请选择性别')
      return
    }

    if (!this.data.birthDate) {
      util.showToast('请选择出生日期')
      return
    }

    this.setData({ submitting: true })

    try {
      // 调用API保存个人信息
      await api.completeProfile({
        nickname: this.data.nickname,
        gender: this.data.gender,
        birth_date: this.data.birthDate
      })

      util.showToast('保存成功', 'success')

      // 跳转到首页
      setTimeout(() => {
        wx.switchTab({
          url: '/pages/dashboard/dashboard'
        })
      }, 1500)
    } catch (err) {
      console.error('保存失败:', err)
      util.showToast(err.message || '保存失败')
    } finally {
      this.setData({ submitting: false })
    }
  }
})
