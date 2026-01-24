const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: { checkups: [], page: 1, hasMore: true },

  onLoad() { this.loadCheckups() },

  async loadCheckups() {
    if (!this.data.hasMore) return
    util.showLoading()

    try {
      const res = await api.getCheckups({ page: this.data.page, page_size: 20 })
      const checkups = res.data || []

      // 为每个报告计算异常指标数量
      const processedCheckups = await Promise.all(checkups.map(async (checkup) => {
        try {
          // 获取该报告的指标列表
          const indicatorsRes = await api.getIndicators({ checkup_id: checkup.id, page_size: 500 })
          const indicators = indicatorsRes.data || indicatorsRes.results || []

          // 计算异常数量
          const abnormalCount = indicators.filter(indicator => {
            const status = indicator.status
            return status === 'abnormal' || status === 'abnormal_high' || status === 'abnormal_low'
          }).length

          return {
            ...checkup,
            abnormal_count: abnormalCount,
            indicators_count: indicators.length
          }
        } catch (err) {
          console.error('获取报告指标失败:', err)
          return {
            ...checkup,
            abnormal_count: 0,
            indicators_count: checkup.indicator_count || checkup.indicators_count || 0
          }
        }
      }))

      this.setData({
        checkups: [...this.data.checkups, ...processedCheckups],
        hasMore: res.has_more !== undefined ? res.has_more : checkups.length >= 20,
        page: this.data.page + 1
      })
    } catch (err) {
      console.error('加载失败:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
    }
  },

  goToDetail(e) {
    wx.navigateTo({ url: `/pages/checkup-detail/checkup-detail?id=${e.currentTarget.dataset.id}` })
  },

  /**
   * 删除报告
   */
  async deleteCheckup(e) {
    const id = e.currentTarget.dataset.id

    const confirm = await util.showConfirm('确定要删除这份体检报告吗？删除后无法恢复。')
    if (!confirm) return

    util.showLoading('删除中...')
    try {
      await api.deleteCheckup(id)
      util.showToast('删除成功')

      // 从列表中移除
      const checkups = this.data.checkups.filter(c => c.id !== id)
      this.setData({ checkups })
    } catch (err) {
      console.error('删除失败:', err)
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  },

  goToUpload() { wx.switchTab({ url: '/pages/upload/upload' }) },

  onReachBottom() { this.loadCheckups() }
})
