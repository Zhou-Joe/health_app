const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    checkups: [],
    selectedIds: [],
    selectedIdSet: {},  // 用Set来存储选中的ID，方便快速查找
    integrating: false
  },

  onLoad() {
    this.loadCheckups()
  },

  async loadCheckups() {
    util.showLoading()
    try {
      const res = await api.getCheckups({ page_size: 100, status: 'completed' })
      const checkups = res.data || []
      console.log('加载的报告列表:', checkups)
      console.log('第一个报告ID:', checkups[0]?.id, '类型:', typeof checkups[0]?.id)
      this.setData({ checkups })
    } catch (err) {
      console.error('加载报告失败:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
    }
  },

  toggleSelection(e) {
    const id = e.currentTarget.dataset.id
    const idNum = parseInt(id)  // 转换为数字
    const idStr = String(idNum)  // 同时保留字符串版本

    const selectedIds = [...this.data.selectedIds]
    const selectedIdSet = { ...this.data.selectedIdSet }

    const index = selectedIds.indexOf(idNum)

    if (index > -1) {
      // 取消选择
      selectedIds.splice(index, 1)
      delete selectedIdSet[idStr]
      delete selectedIdSet[idNum]
    } else {
      // 添加选择
      selectedIds.push(idNum)
      selectedIdSet[idStr] = true
      selectedIdSet[idNum] = true
    }

    console.log('更新后的已选择IDs:', selectedIds)
    console.log('更新后的selectedIdSet:', selectedIdSet)

    this.setData({
      selectedIds,
      selectedIdSet
    })
  },

  async handleIntegrate() {
    if (this.data.selectedIds.length < 2) {
      return util.showToast('请至少选择2份报告')
    }

    this.setData({ integrating: true })

    try {
      console.log('开始数据整合，选择的报告ID:', this.data.selectedIds)
      const res = await api.integrateData({ checkup_ids: this.data.selectedIds })
      console.log('整合结果:', res)

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
      console.error('数据整合失败:', err)
      // 显示更详细的错误信息
      let errorMsg = '整合失败'
      if (err.message) {
        errorMsg = err.message
      } else if (err.error) {
        errorMsg = err.error
      } else if (typeof err === 'string') {
        errorMsg = err
      }
      util.showToast(errorMsg)
    } finally {
      this.setData({ integrating: false })
    }
  }
})
