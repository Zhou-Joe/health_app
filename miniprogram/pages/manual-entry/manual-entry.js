const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    mode: 'new',
    checkupDate: '',
    hospital: '',
    selectedCheckupId: null,
    checkups: [],
    indicators: [],
    indicatorTypes: [],
    commonHospitals: [],
    showAddModal: false,
    newIndicator: {
      indicator_name: '',
      indicator_type: 'blood_routine',
      value: '',
      unit: '',
      reference_range: '',
      status: 'normal'
    },
    statusOptions: [
      { value: 'normal', label: '正常' },
      { value: 'attention', label: '关注' },
      { value: 'abnormal', label: '异常' }
    ],
    today: '',
    submitting: false,
    loading: true
  },

  onLoad() {
    const today = new Date()
    const year = today.getFullYear()
    const month = String(today.getMonth() + 1).padStart(2, '0')
    const day = String(today.getDate()).padStart(2, '0')

    this.setData({
      today: `${year}-${month}-${day}`,
      checkupDate: `${year}-${month}-${day}`
    })

    this.loadData()
  },

  async loadData() {
    try {
      const [checkupsRes, hospitalsRes, typesRes] = await Promise.all([
        api.getCheckups({ page_size: 100 }),
        api.getCommonHospitals(),
        api.getIndicatorTypes()
      ])

      this.setData({
        checkups: checkupsRes.data || [],
        commonHospitals: hospitalsRes.hospitals || hospitalsRes.data || [],
        indicatorTypes: typesRes.types || typesRes.data || [],
        loading: false
      })
    } catch (err) {
      console.error('加载数据失败:', err)
      this.setData({ loading: false })
    }
  },

  onModeChange(e) {
    this.setData({
      mode: e.detail.value,
      indicators: []
    })
  },

  onDateChange(e) {
    this.setData({ checkupDate: e.detail.value })
  },

  onHospitalInput(e) {
    this.setData({ hospital: e.detail.value })
  },

  onCheckupChange(e) {
    const index = e.detail.value
    const checkup = this.data.checkups[index]
    this.setData({
      selectedCheckupId: checkup ? checkup.id : null
    })
  },

  showAddIndicator() {
    this.setData({
      showAddModal: true,
      newIndicator: {
        indicator_name: '',
        indicator_type: 'blood_routine',
        value: '',
        unit: '',
        reference_range: '',
        status: 'normal'
      }
    })
  },

  hideAddModal() {
    this.setData({ showAddModal: false })
  },

  onIndicatorNameInput(e) {
    this.setData({ 'newIndicator.indicator_name': e.detail.value })
  },

  onIndicatorTypeChange(e) {
    const index = e.detail.value
    const types = this.data.indicatorTypes
    if (types && types[index]) {
      this.setData({ 'newIndicator.indicator_type': types[index].value || types[index].name })
    }
  },

  onIndicatorValueInput(e) {
    this.setData({ 'newIndicator.value': e.detail.value })
  },

  onIndicatorUnitInput(e) {
    this.setData({ 'newIndicator.unit': e.detail.value })
  },

  onIndicatorReferenceInput(e) {
    this.setData({ 'newIndicator.reference_range': e.detail.value })
  },

  onIndicatorStatusChange(e) {
    const index = e.detail.value
    const status = this.data.statusOptions[index]
    if (status) {
      this.setData({ 'newIndicator.status': status.value })
    }
  },

  addIndicator() {
    const { newIndicator } = this.data

    if (!newIndicator.indicator_name.trim()) {
      util.showToast('请输入指标名称')
      return
    }

    if (!newIndicator.value.trim()) {
      util.showToast('请输入数值')
      return
    }

    this.setData({
      indicators: [...this.data.indicators, { ...newIndicator }],
      showAddModal: false
    })
  },

  removeIndicator(e) {
    const index = e.currentTarget.dataset.index
    const indicators = this.data.indicators.filter((_, i) => i !== index)
    this.setData({ indicators })
  },

  async submitData() {
    const { mode, checkupDate, hospital, selectedCheckupId, indicators } = this.data

    if (indicators.length === 0) {
      util.showToast('请至少添加一个健康指标')
      return
    }

    if (mode === 'new') {
      if (!checkupDate) {
        util.showToast('请选择体检日期')
        return
      }
    } else {
      if (!selectedCheckupId) {
        util.showToast('请选择体检报告')
        return
      }
    }

    this.setData({ submitting: true })

    try {
      let checkupId = selectedCheckupId

      if (mode === 'new') {
        const checkupRes = await api.createIndicator({
          checkup_date: checkupDate,
          hospital: hospital || '手动录入',
          indicators: indicators
        })
        
        if (checkupRes.success) {
          util.showToast('提交成功')
          setTimeout(() => {
            wx.navigateBack()
          }, 1500)
        }
      } else {
        const res = await api.batchCreateIndicators({
          checkup_id: checkupId,
          indicators: indicators
        })

        if (res.success) {
          util.showToast('提交成功')
          setTimeout(() => {
            wx.navigateBack()
          }, 1500)
        }
      }
    } catch (err) {
      util.showToast(err.message || '提交失败')
    } finally {
      this.setData({ submitting: false })
    }
  },

  stopPropagation() {}
})
