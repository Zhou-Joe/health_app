const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')
const config = require('../../config.js')

Page({
  data: {
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
    loading: false
  },

  onOldPasswordInput(e) {
    this.setData({ oldPassword: e.detail.value })
  },

  onNewPasswordInput(e) {
    this.setData({ newPassword: e.detail.value })
  },

  onConfirmPasswordInput(e) {
    this.setData({ confirmPassword: e.detail.value })
  },

  async handleChangePassword() {
    const { oldPassword, newPassword, confirmPassword } = this.data

    if (!oldPassword) {
      util.showToast('请输入原密码')
      return
    }

    if (!newPassword) {
      util.showToast('请输入新密码')
      return
    }

    if (newPassword.length < 6) {
      util.showToast('新密码长度不能少于6位')
      return
    }

    if (!confirmPassword) {
      util.showToast('请确认新密码')
      return
    }

    if (newPassword !== confirmPassword) {
      util.showToast('两次输入的新密码不一致')
      return
    }

    this.setData({ loading: true })

    try {
      const res = await api.changePassword({
        old_password: oldPassword,
        new_password: newPassword,
        confirm_password: confirmPassword
      })

      if (res.success) {
        if (res.token) {
          wx.setStorageSync(config.storageKeys.TOKEN, res.token)
        }
        
        util.showToast('密码修改成功')
        
        setTimeout(() => {
          app.clearLoginInfo()
          wx.reLaunch({
            url: '/pages/login/login'
          })
        }, 1500)
      }
    } catch (err) {
      util.showToast(err.message || '修改密码失败')
    } finally {
      this.setData({ loading: false })
    }
  }
})
