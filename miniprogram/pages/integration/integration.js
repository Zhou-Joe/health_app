const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    checkups: [],
    selectedIds: [],
    integrating: false
  },

  onLoad() {
    this.loadCheckups()
  },

  async loadCheckups() {
    util.showLoading()
    try {
      const res = await api.getCheckups({ page_size: 100, status: 'completed' })
      this.setData({ checkups: res.data || [] })
    } catch (err) {
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
    }
  },

  toggleSelection(e) {
    const id = e.currentTarget.dataset.id
    const selectedIds = [...this.data.selectedIds]
    const index = selectedIds.indexOf(id)

    if (index > -1) {
      selectedIds.splice(index, 1)
    } else {
      selectedIds.push(id)
    }

    this.setData({ selectedIds })
  },

  async handleIntegrate() {
    if (this.data.selectedIds.length < 2) {
      return util.showToast('请至少选择2份报告')
    }

    this.setData({ integrating: true })

    try {
      const res = await api.integrateData({ checkup_ids: this.data.selectedIds })

      wx.showModal({
        title: '整合完成',
        content: `共分析${res.total_indicators}个指标，发现${res.changed_count}个需要统一`,
        confirmText: '查看详情',
        success: (modalRes) => {
          if (modalRes.confirm) {
            // 可以跳转到详情页查看具体变化
            console.log('整合结果:', res)
          }
        }
      })
    } catch (err) {
      util.showToast(err.message || '整合失败')
    } finally {
      this.setData({ integrating: false })
    }
  }
})
