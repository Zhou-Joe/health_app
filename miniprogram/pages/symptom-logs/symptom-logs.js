const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    logs: [],
    loading: true,
    showAddModal: false,
    editingLog: null,
    formData: {
      entry_date: '',
      symptom: '',
      severity: 3,
      notes: ''
    },
    severityOptions: [
      { value: 1, label: '轻微', color: '#4CAF50' },
      { value: 2, label: '轻度', color: '#8BC34A' },
      { value: 3, label: '中度', color: '#FFC107' },
      { value: 4, label: '严重', color: '#FF9800' },
      { value: 5, label: '非常严重', color: '#F44336' }
    ],
    today: '',
    submitting: false
  },

  onLoad() {
    const today = new Date()
    const year = today.getFullYear()
    const month = String(today.getMonth() + 1).padStart(2, '0')
    const day = String(today.getDate()).padStart(2, '0')

    this.setData({
      today: `${year}-${month}-${day}`,
      'formData.entry_date': `${year}-${month}-${day}`
    })

    this.loadLogs()
  },

  onShow() {
    this.loadLogs()
  },

  async loadLogs() {
    this.setData({ loading: true })
    try {
      const res = await api.getSymptomLogs({ page_size: 100 })
      const logs = (res.logs || res.data || []).map(log => ({
        ...log,
        entry_date: util.formatDate(log.entry_date, 'YYYY-MM-DD'),
        severityColor: this.getSeverityColor(log.severity)
      }))
      this.setData({ logs, loading: false })
    } catch (err) {
      console.error('[symptom-logs] loadLogs failed:', err)
      this.setData({ loading: false })
      util.showToast(err.message || '加载失败')
    }
  },

  getSeverityColor(severity) {
    const colors = {
      1: '#4CAF50',
      2: '#8BC34A',
      3: '#FFC107',
      4: '#FF9800',
      5: '#F44336'
    }
    return colors[severity] || '#9E9E9E'
  },

  getSeverityLabel(severity) {
    const labels = {
      1: '轻微',
      2: '轻度',
      3: '中度',
      4: '严重',
      5: '非常严重'
    }
    return labels[severity] || '未知'
  },

  showAddModal() {
    const today = new Date()
    const year = today.getFullYear()
    const month = String(today.getMonth() + 1).padStart(2, '0')
    const day = String(today.getDate()).padStart(2, '0')

    this.setData({
      showAddModal: true,
      editingLog: null,
      formData: {
        entry_date: `${year}-${month}-${day}`,
        symptom: '',
        severity: 3,
        notes: ''
      }
    })
  },

  editLog(e) {
    const log = e.currentTarget.dataset.log
    this.setData({
      showAddModal: true,
      editingLog: log,
      formData: {
        entry_date: log.entry_date,
        symptom: log.symptom,
        severity: log.severity,
        notes: log.notes || ''
      }
    })
  },

  hideModal() {
    if (this.data.submitting) return
    this.setData({ showAddModal: false, editingLog: null })
  },

  onDateChange(e) {
    this.setData({ 'formData.entry_date': e.detail.value })
  },

  onSymptomInput(e) {
    this.setData({ 'formData.symptom': e.detail.value })
  },

  onSeverityChange(e) {
    const index = e.detail.value
    const severity = this.data.severityOptions[index]
    if (severity) {
      this.setData({ 'formData.severity': severity.value })
    }
  },

  onNotesInput(e) {
    this.setData({ 'formData.notes': e.detail.value })
  },

  async submitForm() {
    const { formData, editingLog } = this.data

    if (!formData.symptom.trim()) {
      util.showToast('请输入症状名称')
      return
    }

    if (!formData.entry_date) {
      util.showToast('请选择日期')
      return
    }

    this.setData({ submitting: true })
    util.showLoading(editingLog ? '保存中...' : '添加中...')

    try {
      const data = {
        entry_date: formData.entry_date,
        symptom: formData.symptom.trim(),
        severity: formData.severity,
        notes: formData.notes.trim()
      }

      if (editingLog) {
        await api.updateSymptomLog(editingLog.id, data)
        util.showToast('保存成功')
      } else {
        await api.createSymptomLog(data)
        util.showToast('添加成功')
      }

      this.setData({ showAddModal: false, editingLog: null })
      this.loadLogs()
    } catch (err) {
      console.error('[symptom-logs] submitForm failed:', err)
      util.showToast(err.message || '操作失败')
    } finally {
      util.hideLoading()
      this.setData({ submitting: false })
    }
  },

  async deleteLog(e) {
    const log = e.currentTarget.dataset.log
    const confirm = await util.showConfirm(`确定要删除"${log.symptom}"吗？`)
    if (!confirm) return

    util.showLoading('删除中...')
    try {
      await api.deleteSymptomLog(log.id)
      util.showToast('删除成功')
      this.loadLogs()
    } catch (err) {
      console.error('[symptom-logs] deleteLog failed:', err)
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  },

  stopPropagation() {}
})
