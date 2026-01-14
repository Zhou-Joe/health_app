const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    checkups: [],
    selectedIds: [],
    selectedIdSet: {},  // 用Set来存储选中的ID，方便快速查找
    integrating: false,
    userPrompt: '',  // 用户自定义提示词
    // 重复报告相关
    duplicateGroups: [],
    hasChecked: false
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

  onPromptInput(e) {
    this.setData({
      userPrompt: e.detail.value
    })
  },

  async handleIntegrate() {
    if (this.data.selectedIds.length < 2) {
      return util.showToast('请至少选择2份报告')
    }

    this.setData({ integrating: true })

    try {
      console.log('开始数据整合，选择的报告ID:', this.data.selectedIds)
      console.log('用户提示词:', this.data.userPrompt)

      const requestData = {
        checkup_ids: this.data.selectedIds
      }

      // 如果用户填写了提示词，添加到请求数据中
      if (this.data.userPrompt && this.data.userPrompt.trim()) {
        requestData.user_prompt = this.data.userPrompt.trim()
        console.log('包含用户自定义提示词')
      }

      const res = await api.integrateData(requestData)
      console.log('整合结果:', res)

      // 显示整合结果并跳转到详情页
      wx.showModal({
        title: '整合完成',
        content: `共分析${res.total_indicators}个指标，发现${res.changed_count}个需要统一`,
        confirmText: '查看详情',
        cancelText: '返回',
        success: (modalRes) => {
          if (modalRes.confirm) {
            // 跳转到详情页面
            this.goToIntegrationResult(res)
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
  },

  goToIntegrationResult(result) {
    // 将结果存储到全局数据中，以便详情页使用
    const app = getApp()
    app.globalData.integrationResult = result

    // 跳转到详情页
    wx.navigateTo({
      url: '/pages/integration-result/integration-result'
    })
  },

  /**
   * 检测重复报告
   */
  async detectDuplicates() {
    util.showLoading('检测中...')
    try {
      const res = await api.detectDuplicates()
      console.log('重复报告检测结果:', res)

      const groups = res.data || []
      // 为每组初始化主报告ID（默认选第一个）
      groups.forEach(group => {
        if (!group.targetCheckupId && group.checkups.length > 0) {
          group.targetCheckupId = group.checkups[0].id
        }
      })

      this.setData({
        duplicateGroups: groups,
        hasChecked: true
      })

      if (groups.length === 0) {
        util.showToast('未发现重复报告')
      } else {
        util.showToast(`发现 ${groups.length} 组重复报告`)
      }
    } catch (err) {
      console.error('检测重复报告失败:', err)
      util.showToast(err.message || '检测失败')
    } finally {
      util.hideLoading()
    }
  },

  /**
   * 选择主报告
   */
  selectTargetCheckup(e) {
    const groupIndex = e.currentTarget.dataset.groupIndex
    const checkupId = parseInt(e.currentTarget.dataset.checkupId)

    const duplicateGroups = [...this.data.duplicateGroups]
    duplicateGroups[groupIndex].targetCheckupId = checkupId

    this.setData({ duplicateGroups })
  },

  /**
   * 合并重复报告
   */
  async mergeDuplicates(e) {
    const groupIndex = e.currentTarget.dataset.groupIndex
    const group = this.data.duplicateGroups[groupIndex]

    if (!group.targetCheckupId) {
      return util.showToast('请先选择主报告')
    }

    // 获取要合并的源报告ID（除了主报告之外的所有报告）
    const sourceCheckupIds = group.checkups
      .filter(c => c.id !== group.targetCheckupId)
      .map(c => c.id)

    if (sourceCheckupIds.length === 0) {
      return util.showToast('没有要合并的报告')
    }

    const confirmMsg = `确定将 ${sourceCheckupIds.length} 份报告合并到 ID ${group.targetCheckupId} 中吗？此操作不可撤销。`

    wx.showModal({
      title: '确认合并',
      content: confirmMsg,
      success: async (res) => {
        if (res.confirm) {
          await this.doMergeDuplicates(groupIndex, group.targetCheckupId, sourceCheckupIds)
        }
      }
    })
  },

  async doMergeDuplicates(groupIndex, targetCheckupId, sourceCheckupIds) {
    const duplicateGroups = [...this.data.duplicateGroups]
    duplicateGroups[groupIndex].merging = true
    this.setData({ duplicateGroups })

    try {
      const res = await api.mergeDuplicates({
        target_checkup_id: targetCheckupId,
        source_checkup_ids: sourceCheckupIds
      })

      console.log('合并结果:', res)

      util.showToast(res.message || '合并成功')

      // 移除已合并的组
      duplicateGroups.splice(groupIndex, 1)
      this.setData({ duplicateGroups })

      // 刷新报告列表
      await this.loadCheckups()

      // 如果所有重复都处理完了
      if (duplicateGroups.length === 0) {
        wx.showModal({
          title: '全部完成',
          content: '所有重复报告已合并完成',
          showCancel: false
        })
      }
    } catch (err) {
      console.error('合并失败:', err)
      util.showToast(err.message || '合并失败')
      duplicateGroups[groupIndex].merging = false
      this.setData({ duplicateGroups })
    }
  }
})
