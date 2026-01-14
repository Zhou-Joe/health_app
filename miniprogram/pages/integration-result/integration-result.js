const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    result: {
      total_indicators: 0,
      changed_count: 0,
      unchanged_count: 0
    },
    changes: []
  },

  onLoad() {
    const app = getApp()
    const result = app.globalData.integrationResult

    if (!result) {
      util.showToast('未找到整合结果')
      wx.navigateBack()
      return
    }

    console.log('整合结果:', result)

    // 使用 all_indicators 或 changes
    const changes = result.all_indicators || result.changes || []

    this.setData({
      result: result,
      changes: changes
    })
  },

  goBack() {
    wx.navigateBack()
  },

  async applyChanges() {
    if (this.data.result.changed_count === 0) {
      return util.showToast('没有需要应用的更改')
    }

    // 过滤出有变更的指标
    const changesToApply = this.data.changes.filter(item => !item.unchanged)

    if (!changesToApply || changesToApply.length === 0) {
      return util.showToast('没有需要应用的更改')
    }

    const confirmMsg = '确定要应用 ' + changesToApply.length + ' 个更改吗？此操作不可撤销。'

    wx.showModal({
      title: '确认应用',
      content: confirmMsg,
      success: async (res) => {
        if (res.confirm) {
          await this.doApplyChanges(changesToApply)
        }
      }
    })
  },

  async doApplyChanges(changes) {
    util.showLoading('正在应用更改...')

    try {
      const res = await api.applyIntegration({ changes: changes })
      console.log('应用更改结果:', res)

      util.hideLoading()

      if (res.success) {
        const updatedCount = res.updated_count || changes.length
        wx.showModal({
          title: '更新完成',
          content: '成功更新 ' + updatedCount + ' 个指标',
          showCancel: false,
          success: () => {
            // 返回首页或上一页
            wx.navigateBack()
          }
        })
      } else {
        util.showToast(res.message || '更新失败')
      }
    } catch (err) {
      console.error('应用更改失败:', err)
      util.hideLoading()
      util.showToast(err.message || '更新失败，请稍后重试')
    }
  }
})
