const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    checkups: [],
    page: 1,
    hasMore: true,
    isSelectMode: false, // 是否处于选择模式
    selectedIds: [], // 已选择的报告ID
    selectAll: false // 是否全选
  },

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
            indicators_count: indicators.length,
            selected: false // 添加选中状态
          }
        } catch (err) {
          console.error('获取报告指标失败:', err)
          return {
            ...checkup,
            abnormal_count: 0,
            indicators_count: checkup.indicator_count || checkup.indicators_count || 0,
            selected: false
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
    // 如果在选择模式，不跳转
    if (this.data.isSelectMode) return
    wx.navigateTo({ url: `/pages/checkup-detail/checkup-detail?id=${e.currentTarget.dataset.id}` })
  },

  /**
   * 切换选择模式
   */
  toggleSelectMode() {
    const isSelectMode = !this.data.isSelectMode
    this.setData({
      isSelectMode,
      selectedIds: [],
      selectAll: false
    })

    // 清除所有选中状态
    const checkups = this.data.checkups.map(c => ({ ...c, selected: false }))
    this.setData({ checkups })
  },

  /**
   * 选择/取消选择单个报告
   */
  toggleSelect(e) {
    const { id } = e.currentTarget.dataset
    const checkups = this.data.checkups.map(c => {
      if (c.id === id) {
        return { ...c, selected: !c.selected }
      }
      return c
    })

    const selectedIds = checkups.filter(c => c.selected).map(c => c.id)
    const selectAll = selectedIds.length === checkups.length && checkups.length > 0

    this.setData({ checkups, selectedIds, selectAll })
  },

  /**
   * 全选/取消全选
   */
  toggleSelectAll() {
    const selectAll = !this.data.selectAll
    const checkups = this.data.checkups.map(c => ({ ...c, selected: selectAll }))
    const selectedIds = selectAll ? checkups.map(c => c.id) : []

    this.setData({ checkups, selectedIds, selectAll })
  },

  /**
   * 批量导出选中的报告
   */
  async exportSelected(format) {
    if (this.data.selectedIds.length === 0) {
      util.showToast('请先选择要导出的报告')
      return
    }
    await this.exportReport(this.data.selectedIds, format)
  },

  /**
   * 导出报告
   */
  async exportReport(checkupIds, format) {
    const formatText = format === 'pdf' ? 'PDF' : 'Word'
    util.showLoading(`生成${formatText}中...`)

    try {
      const downloadFunc = format === 'pdf' ? api.exportCheckupsPDF : api.exportCheckupsWord
      const tempFilePath = await downloadFunc(checkupIds)

      util.hideLoading()

      // 打开文件
      wx.openDocument({
        filePath: tempFilePath,
        fileType: format,
        showMenu: true,
        success: () => {
          console.log('文件打开成功')
        },
        fail: (err) => {
          console.error('打开文件失败:', err)
          util.showToast('打开文件失败')
        }
      })
    } catch (err) {
      console.error('导出失败:', err)
      util.showToast(err.message || '导出失败')
    } finally {
      util.hideLoading()
    }
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
