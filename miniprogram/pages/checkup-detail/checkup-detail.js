const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: { checkup: {}, indicators: [], stats: { total: 0, normal: 0, abnormal: 0 } },

  onLoad(options) {
    if (options.id) { this.loadData(options.id) }
  },

  async loadData(id) {
    util.showLoading()
    try {
      const [checkupRes, indicatorsRes] = await Promise.all([
        api.getCheckupDetail(id),
        api.getIndicators({ checkup_id: id, page_size: 500 })
      ])

      const indicators = indicatorsRes.data || []
      const stats = { total: indicators.length, normal: 0, abnormal: 0 }
      indicators.forEach(i => { i.status === 'normal' ? stats.normal++ : stats.abnormal++ })

      this.setData({ checkup: checkupRes.data, indicators, stats })
    } catch (err) {
      console.error('加载失败:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
    }
  },

  addIndicator() { wx.navigateTo({ url: `/pages/indicator-edit/indicator-edit?checkupId=${this.data.checkup.id}` }) },
  editIndicator(e) { wx.navigateTo({ url: `/pages/indicator-edit/indicator-edit?id=${e.currentTarget.dataset.id}&checkupId=${this.data.checkup.id}` }) }
})
