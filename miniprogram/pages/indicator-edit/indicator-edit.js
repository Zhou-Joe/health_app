const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    checkupId: null,
    indicatorId: null,
    formData: {
      indicator_name: '',
      value: '',
      unit: '',
      reference_range: '',
      status: 'normal'
    },
    statusOptions: ['正常', '异常', '关注'],
    statusIndex: 0
  },

  onLoad(options) {
    if (options.checkupId) {
      this.setData({ checkupId: options.checkupId })
    }
    if (options.id) {
      this.setData({ indicatorId: options.id })
      this.loadIndicator(options.id)
    }
  },

  async loadIndicator(id) {
    try {
      const res = await api.getIndicators({ page_size: 1000 })
      const indicator = res.data.find(i => i.id == id)
      if (indicator) {
        this.setData({ formData: indicator })
        const statusIndex = ['normal', 'abnormal', 'attention'].indexOf(indicator.status)
        if (statusIndex >= 0) {
          this.setData({ statusIndex })
        }
      }
    } catch (err) {
      console.error(err)
    }
  },

  onNameInput(e) {
    this.setData({ 'formData.indicator_name': e.detail.value })
  },

  onValueInput(e) {
    this.setData({ 'formData.value': e.detail.value })
  },

  onUnitInput(e) {
    this.setData({ 'formData.unit': e.detail.value })
  },

  onRefInput(e) {
    this.setData({ 'formData.reference_range': e.detail.value })
  },

  onStatusChange(e) {
    const statusMap = ['normal', 'abnormal', 'attention']
    this.setData({
      statusIndex: e.detail.value,
      'formData.status': statusMap[e.detail.value]
    })
  },

  async handleSubmit() {
    const { formData, checkupId, indicatorId } = this.data
    if (!formData.indicator_name || !formData.value) {
      return util.showToast('请填写必填项')
    }

    util.showLoading()
    try {
      if (indicatorId) {
        await api.updateIndicator(indicatorId, formData)
      } else {
        await api.createIndicator({ ...formData, checkup_id: checkupId })
      }
      util.showToast('保存成功', 'success')
      setTimeout(() => wx.navigateBack(), 1000)
    } catch (err) {
      util.showToast(err.message || '保存失败')
    } finally {
      util.hideLoading()
    }
  }
})
