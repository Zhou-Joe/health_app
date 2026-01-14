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
      console.log('=== 小程序指标数据调试 ===')
      console.log('指标数量:', indicators.length)
      console.log('前3个指标:')
      indicators.slice(0, 3).forEach((i, idx) => {
        console.log(`  指标${idx+1}:`, {
          indicator_name: i.indicator_name,
          value: i.value,
          unit: i.unit,
          reference_range: i.reference_range,
          status: i.status
        })
      })

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
  editIndicator(e) { wx.navigateTo({ url: `/pages/indicator-edit/indicator-edit?id=${e.currentTarget.dataset.id}&checkupId=${this.data.checkup.id}` }) },

  /**
   * 删除报告
   */
  async deleteCheckup() {
    const confirm = await util.showConfirm('确定要删除这份体检报告吗？删除后无法恢复。')
    if (!confirm) return

    util.showLoading('删除中...')
    try {
      await api.deleteCheckup(this.data.checkup.id)
      util.showToast('删除成功'))

      // 返回上一页
      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
    } catch (err) {
      console.error('删除失败:', err)
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  }
})
