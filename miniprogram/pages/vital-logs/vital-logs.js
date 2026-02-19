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
      vital_type: 'blood_pressure',
      value: '',
      unit: '',
      notes: ''
    },
    vitalTypes: [
      { value: 'blood_pressure', label: '血压', unit: 'mmHg', icon: '❤️', color: '#F44336' },
      { value: 'heart_rate', label: '心率', unit: 'bpm', icon: '💓', color: '#E91E63' },
      { value: 'weight', label: '体重', unit: 'kg', icon: '⚖️', color: '#2196F3' },
      { value: 'temperature', label: '体温', unit: '°C', icon: '🌡️', color: '#FF9800' },
      { value: 'blood_sugar', label: '血糖', unit: 'mmol/L', icon: '💧', color: '#9C27B0' },
      { value: 'oxygen', label: '血氧', unit: '%', icon: '🫁', color: '#00BCD4' },
      { value: 'other', label: '其他', unit: '', icon: '📝', color: '#9E9E9E' }
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
      const res = await api.getVitalLogs({ page_size: 100 })
      const logs = (res.logs || res.data || []).map(log => ({
        ...log,
        entry_date: util.formatDate(log.entry_date, 'YYYY-MM-DD'),
        vitalTypeInfo: this.getVitalTypeInfo(log.vital_type)
      }))
      this.setData({ logs, loading: false })
    } catch (err) {
      console.error('[vital-logs] loadLogs failed:', err)
      this.setData({ loading: false })
      util.showToast(err.message || '加载失败')
    }
  },

  getVitalTypeInfo(vitalType) {
    const typeMap = {
      blood_pressure: { label: '血压', unit: 'mmHg', icon: '❤️', color: '#F44336' },
      heart_rate: { label: '心率', unit: 'bpm', icon: '💓', color: '#E91E63' },
      weight: { label: '体重', unit: 'kg', icon: '⚖️', color: '#2196F3' },
      temperature: { label: '体温', unit: '°C', icon: '🌡️', color: '#FF9800' },
      blood_sugar: { label: '血糖', unit: 'mmol/L', icon: '💧', color: '#9C27B0' },
      oxygen: { label: '血氧', unit: '%', icon: '🫁', color: '#00BCD4' },
      other: { label: '其他', unit: '', icon: '📝', color: '#9E9E9E' }
    }
    return typeMap[vitalType] || typeMap.other
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
        vital_type: 'blood_pressure',
        value: '',
        unit: 'mmHg',
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
        vital_type: log.vital_type,
        value: log.value,
        unit: log.unit || '',
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

  onVitalTypeChange(e) {
    const index = e.detail.value
    const vitalType = this.data.vitalTypes[index]
    if (vitalType) {
      this.setData({
        'formData.vital_type': vitalType.value,
        'formData.unit': vitalType.unit
      })
    }
  },

  onValueInput(e) {
    this.setData({ 'formData.value': e.detail.value })
  },

  onUnitInput(e) {
    this.setData({ 'formData.unit': e.detail.value })
  },

  onNotesInput(e) {
    this.setData({ 'formData.notes': e.detail.value })
  },

  async submitForm() {
    const { formData, editingLog } = this.data

    if (!formData.value.trim()) {
      util.showToast('请输入数值')
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
        vital_type: formData.vital_type,
        value: formData.value.trim(),
        unit: formData.unit.trim(),
        notes: formData.notes.trim()
      }

      if (editingLog) {
        await api.updateVitalLog(editingLog.id, data)
        util.showToast('保存成功')
      } else {
        await api.createVitalLog(data)
        util.showToast('添加成功')
      }

      this.setData({ showAddModal: false, editingLog: null })
      this.loadLogs()
    } catch (err) {
      console.error('[vital-logs] submitForm failed:', err)
      util.showToast(err.message || '操作失败')
    } finally {
      util.hideLoading()
      this.setData({ submitting: false })
    }
  },

  async deleteLog(e) {
    const log = e.currentTarget.dataset.log
    const typeInfo = log.vitalTypeInfo || this.getVitalTypeInfo(log.vital_type)
    const confirm = await util.showConfirm(`确定要删除这条${typeInfo.label}记录吗？`)
    if (!confirm) return

    util.showLoading('删除中...')
    try {
      await api.deleteVitalLog(log.id)
      util.showToast('删除成功')
      this.loadLogs()
    } catch (err) {
      console.error('[vital-logs] deleteLog failed:', err)
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  },

  stopPropagation() {}
})
