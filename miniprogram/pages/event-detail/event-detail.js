const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    eventId: null,
    loading: false,
    event: null,
    items: [],
    boundReportObjectIds: [],
    eventTypeLabel: '',
    dateRange: '',
    showRenameModal: false,
    renameInput: '',
    savingRename: false,
    showReportPicker: false,
    availableLoading: false,
    availableReports: [],
    addingReportId: null,
    removingItemId: null,
    aiSummary: null,
    aiSummaryLoading: false,
    aiSummaryError: null
  },

  onLoad(options) {
    const eventId = options.id ? parseInt(options.id, 10) : null
    if (!eventId) {
      util.showToast('事件ID无效')
      return
    }

    this.setData({ eventId })
    this.loadEventDetail()
  },

  onPullDownRefresh() {
    this.loadEventDetail().finally(() => {
      wx.stopPullDownRefresh()
    })
  },

  async loadEventDetail() {
    if (this.data.loading || !this.data.eventId) {
      return
    }

    this.setData({ loading: true })
    util.showLoading('加载中...')

    try {
      const res = await api.getEventDetail(this.data.eventId)
      const event = res.event || null
      const rawItems = res.items || []

      const items = rawItems.map((item) => {
        const contentType = item.content_type || 'other'
        const canNavigate = this.canNavigateByType(contentType)

        return {
          ...item,
          id: Number(item.id),
          object_id: Number(item.object_id),
          contentTypeLabel: this.getContentTypeLabel(contentType),
          addedByLabel: item.added_by === 'auto' ? '自动' : '手动',
          canNavigate,
          canRemoveReport: contentType === 'healthcheckup',
          actionLabel: canNavigate ? '查看详情' : '查看信息'
        }
      })
      const boundReportObjectIds = items
        .filter(item => item.content_type === 'healthcheckup')
        .map(item => Number(item.object_id))

      this.setData({
        event,
        items,
        boundReportObjectIds,
        eventTypeLabel: this.getEventTypeLabel(event?.event_type),
        dateRange: this.getDateRange(event)
      })

      this.loadAiSummary()
    } catch (err) {
      console.error('[event-detail] load failed:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
      this.setData({ loading: false })
    }
  },

  async loadAiSummary() {
    if (!this.data.eventId) return

    this.setData({ aiSummaryLoading: true, aiSummaryError: null })

    try {
      const res = await api.getEventAiSummary(this.data.eventId)
      const aiSummary = res.ai_summary || null
      this.setData({
        aiSummary,
        aiSummaryLoading: false
      })
    } catch (err) {
      console.error('[event-detail] loadAiSummary failed:', err)
      this.setData({
        aiSummaryLoading: false,
        aiSummaryError: err.message || '加载AI总结失败'
      })
    }
  },

  async generateAiSummary() {
    if (!this.data.eventId || this.data.aiSummaryLoading) return

    this.setData({ aiSummaryLoading: true, aiSummaryError: null, aiSummary: '' })

    try {
      await api.streamEventAiSummary(
        this.data.eventId,
        (chunk, fullContent) => {
          this.setData({
            aiSummary: fullContent
          })
        },
        (error) => {
          console.error('[event-detail] generateAiSummary error:', error)
          this.setData({
            aiSummaryLoading: false,
            aiSummaryError: error || '生成失败'
          })
        },
        (finalContent) => {
          this.setData({
            aiSummary: finalContent,
            aiSummaryLoading: false
          })
          util.showToast('AI总结已生成')
        }
      )
    } catch (err) {
      console.error('[event-detail] generateAiSummary failed:', err)
      this.setData({
        aiSummaryLoading: false,
        aiSummaryError: err.message || '生成AI总结失败'
      })
      util.showToast(err.message || '生成AI总结失败')
    }
  },

  async exportSummaryPdf() {
    if (!this.data.eventId) return

    util.showLoading('正在导出PDF...')
    try {
      await api.exportEventSummaryPdf(this.data.eventId)
      util.showToast('导出成功')
    } catch (err) {
      console.error('[event-detail] exportSummaryPdf failed:', err)
      util.showToast(err.message || '导出失败')
    } finally {
      util.hideLoading()
    }
  },

  async exportSummaryWord() {
    if (!this.data.eventId) return

    util.showLoading('正在导出Word...')
    try {
      await api.exportEventSummaryWord(this.data.eventId)
      util.showToast('导出成功')
    } catch (err) {
      console.error('[event-detail] exportSummaryWord failed:', err)
      util.showToast(err.message || '导出失败')
    } finally {
      util.hideLoading()
    }
  },

  getEventTypeLabel(type) {
    const labelMap = {
      illness: '疾病事件',
      checkup: '体检事件',
      chronic_management: '慢病管理',
      emergency: '急诊事件',
      wellness: '健康管理',
      medication_course: '用药疗程',
      other: '其他'
    }
    return labelMap[type] || '其他'
  },

  getDateRange(event) {
    if (!event) return ''
    const start = event.start_date || ''
    const end = event.end_date || ''
    if (start && end && start !== end) {
      return `${start} ~ ${end}`
    }
    return start || end || ''
  },

  getContentTypeLabel(type) {
    const typeMap = {
      healthcheckup: '体检报告',
      medication: '药单',
      healthindicator: '健康指标',
      medicationrecord: '服药记录',
      symptomentry: '症状日志',
      vitalentry: '体征记录'
    }
    return typeMap[type] || '健康记录'
  },

  canNavigateByType(type) {
    return ['healthcheckup', 'medication', 'healthindicator', 'medicationrecord'].includes(type)
  },

  noop() {},

  openRenameModal() {
    const currentName = this.data.event?.name || ''
    this.setData({
      showRenameModal: true,
      renameInput: currentName
    })
  },

  closeRenameModal() {
    if (this.data.savingRename) return
    this.setData({
      showRenameModal: false,
      renameInput: ''
    })
  },

  onRenameInput(e) {
    this.setData({
      renameInput: e.detail.value || ''
    })
  },

  async confirmRename() {
    if (this.data.savingRename || !this.data.eventId) {
      return
    }

    const name = (this.data.renameInput || '').trim()
    if (!name) {
      util.showToast('事件名称不能为空')
      return
    }

    this.setData({ savingRename: true })
    util.showLoading('保存中...')

    try {
      await api.updateEvent(this.data.eventId, { name })
      this.setData({
        showRenameModal: false,
        renameInput: ''
      })
      await this.loadEventDetail()
      util.showToast('事件名称已更新')
    } catch (err) {
      console.error('[event-detail] rename failed:', err)
      util.showToast(err.message || '改名失败')
    } finally {
      util.hideLoading()
      this.setData({ savingRename: false })
    }
  },

  async openReportPicker() {
    this.setData({
      showReportPicker: true,
      availableReports: []
    })
    await this.loadAvailableReports()
  },

  closeReportPicker() {
    if (this.data.availableLoading || this.data.addingReportId) return
    this.setData({
      showReportPicker: false
    })
  },

  async loadAvailableReports() {
    if (this.data.availableLoading || !this.data.eventId) {
      return
    }

    this.setData({ availableLoading: true })
    try {
      const res = await api.getEventAvailableItems({
        content_type: 'healthcheckup',
        limit: 100
      })
      const items = (res.items || []).map((item) => ({
        ...item,
        object_id: Number(item.object_id),
        summary: item.summary || `体检报告 #${item.object_id}`
      }))
      const boundSet = new Set(this.data.boundReportObjectIds || [])
      const availableReports = items.filter((item) => !boundSet.has(Number(item.object_id)))

      this.setData({ availableReports })
    } catch (err) {
      console.error('[event-detail] load available reports failed:', err)
      util.showToast(err.message || '加载可选报告失败')
    } finally {
      this.setData({ availableLoading: false })
    }
  },

  async onAddReportTap(e) {
    const objectId = Number(e.currentTarget.dataset.objectId)
    if (!objectId || this.data.addingReportId || !this.data.eventId) {
      return
    }

    this.setData({ addingReportId: objectId })
    util.showLoading('添加中...')
    try {
      await api.addEventItem(this.data.eventId, {
        content_type: 'healthcheckup',
        object_id: objectId
      })
      await this.loadEventDetail()
      await this.loadAvailableReports()
      util.showToast('报告已添加')
    } catch (err) {
      console.error('[event-detail] add report failed:', err)
      util.showToast(err.message || '添加报告失败')
    } finally {
      util.hideLoading()
      this.setData({ addingReportId: null })
    }
  },

  async onRemoveReportTap(e) {
    const itemId = Number(e.currentTarget.dataset.itemId)
    if (!itemId || this.data.removingItemId || !this.data.eventId) {
      return
    }

    const confirm = await util.showConfirm('确认从事件中移除此报告？', '移除报告')
    if (!confirm) return

    this.setData({ removingItemId: itemId })
    util.showLoading('移除中...')
    try {
      await api.removeEventItem(this.data.eventId, itemId)
      await this.loadEventDetail()
      if (this.data.showReportPicker) {
        await this.loadAvailableReports()
      }
      util.showToast('已移除')
    } catch (err) {
      console.error('[event-detail] remove report failed:', err)
      util.showToast(err.message || '移除失败')
    } finally {
      util.hideLoading()
      this.setData({ removingItemId: null })
    }
  },

  onTapItem(e) {
    const index = e.currentTarget.dataset.index
    const item = this.data.items[index]
    if (!item) return
    this.openItemDetail(item)
  },

  onTapItemAction(e) {
    const index = e.currentTarget.dataset.index
    const item = this.data.items[index]
    if (!item) return
    this.openItemDetail(item)
  },

  openItemDetail(item) {
    const contentType = item.content_type
    const objectId = item.object_id

    if (contentType === 'healthcheckup') {
      wx.navigateTo({
        url: `/pages/checkup-detail/checkup-detail?id=${objectId}`
      })
      return
    }

    if (contentType === 'medication' || contentType === 'medicationrecord') {
      wx.navigateTo({
        url: '/pages/medications/medications'
      })
      return
    }

    if (contentType === 'healthindicator') {
      wx.switchTab({
        url: '/pages/checkups/checkups'
      })
      util.showToast('请在报告详情页查看该指标')
      return
    }

    wx.showModal({
      title: '记录详情',
      content: [
        `类型：${this.getContentTypeLabel(contentType)}`,
        `摘要：${item.item_summary || '无'}`,
        `记录ID：${objectId}`,
        item.notes ? `备注：${item.notes}` : ''
      ].filter(Boolean).join('\n'),
      showCancel: false,
      confirmText: '知道了'
    })
  }
})
