// pages/medications/medications.js
const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    medications: [],
    records: [],
    showAddModal: false,
    showRecordsModal: false,
    showMakeupModal: false,
    currentMedicationId: null,
    makeupDate: '',
    today: '',
    formData: {
      medicine_name: '',
      dosage: '',
      start_date: '',
      end_date: '',
      notes: ''
    }
  },

  onLoad() {
    this.setData({
      today: util.formatDate(new Date())
    })
    this.loadMedications()
  },

  onShow() {
    this.loadMedications()
  },

  // 加载药单列表
  async loadMedications() {
    try {
      util.showLoading('加载中...')
      const res = await api.getMedications()
      this.setData({ medications: res.medications || [] })
    } catch (error) {
      util.showToast('加载失败：' + (error.message || '未知错误'))
    } finally {
      wx.hideLoading()
    }
  },

  // 显示添加弹窗
  showAddModal() {
    this.setData({
      showAddModal: true,
      formData: {
        medicine_name: '',
        dosage: '',
        start_date: util.formatDate(new Date()),
        end_date: util.formatDate(new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)),
        notes: ''
      }
    })
  },

  // 隐藏添加弹窗
  hideAddModal() {
    this.setData({ showAddModal: false })
  },

  // 表单输入
  onMedicineNameInput(e) {
    this.setData({ 'formData.medicine_name': e.detail.value })
  },

  onDosageInput(e) {
    this.setData({ 'formData.dosage': e.detail.value })
  },

  onStartDateChange(e) {
    this.setData({ 'formData.start_date': e.detail.value })
  },

  onEndDateChange(e) {
    this.setData({ 'formData.end_date': e.detail.value })
  },

  onNotesInput(e) {
    this.setData({ 'formData.notes': e.detail.value })
  },

  // 保存药单
  async saveMedication() {
    const { medicine_name, dosage, start_date, end_date, notes } = this.data.formData

    if (!medicine_name || !dosage) {
      util.showToast('请填写药名和服药方式')
      return
    }

    if (!start_date || !end_date) {
      util.showToast('请选择开始日期和结束日期')
      return
    }

    try {
      util.showLoading('保存中...')
      const result = await api.createMedication({
        medicine_name,
        dosage,
        start_date,
        end_date,
        notes
      })

      console.log('保存结果:', result)

      if (result && result.success) {
        util.showToast('添加成功')
        this.hideAddModal()
        this.loadMedications()
      } else {
        util.showToast('添加失败：' + (result?.error || '未知错误'))
      }
    } catch (error) {
      console.error('保存药单错误:', error)
      const errorMsg = error?.message || error?.error || '保存失败'
      util.showToast('保存失败：' + errorMsg)
    } finally {
      wx.hideLoading()
    }
  },

  // 服药签到
  async checkin(e) {
    const medicationId = e.currentTarget.dataset.id
    const today = util.formatDate(new Date())

    try {
      util.showLoading('签到中...')
      const res = await api.medicationCheckin({
        medication_id: medicationId,
        record_date: today,
        frequency: 'daily'
      })

      console.log('签到结果:', res)

      if (res && res.success) {
        const progress = res.medication_progress
        util.showToast(`签到成功！已服药 ${progress.days_taken}/${progress.total_days} 天`)
        this.loadMedications()
      } else {
        util.showToast(res?.error || '签到失败')
      }
    } catch (error) {
      console.error('签到错误:', error)
      const errorMsg = error?.message || error?.error || '签到失败'
      util.showToast(errorMsg)
    } finally {
      wx.hideLoading()
    }
  },

  // 查看服药记录
  async viewRecords(e) {
    const medicationId = e.currentTarget.dataset.id
    this.setData({ currentMedicationId: medicationId })

    try {
      util.showLoading('加载中...')
      const res = await api.getMedicationRecords(medicationId)

      console.log('服药记录:', res)

      if (res && res.success) {
        this.setData({
          records: res.records || [],
          showRecordsModal: true
        })
      } else {
        util.showToast('加载失败：' + (res?.error || '未知错误'))
      }
    } catch (error) {
      console.error('加载记录错误:', error)
      const errorMsg = error?.message || error?.error || '加载失败'
      util.showToast('加载失败：' + errorMsg)
    } finally {
      wx.hideLoading()
    }
  },

  // 隐藏记录弹窗
  hideRecordsModal() {
    this.setData({ showRecordsModal: false })
  },

  // 删除药单
  deleteMedication(e) {
    const medicationId = e.currentTarget.dataset.id

    wx.showModal({
      title: '确认删除',
      content: '确定要删除这个药单吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            util.showLoading('删除中...')
            const result = await api.deleteMedication(medicationId)

            console.log('删除结果:', result)

            if (result && result.success) {
              util.showToast('删除成功')
              this.loadMedications()
            } else {
              util.showToast('删除失败：' + (result?.error || '未知错误'))
            }
          } catch (error) {
            console.error('删除错误:', error)
            const errorMsg = error?.message || error?.error || '删除失败'
            util.showToast('删除失败：' + errorMsg)
          } finally {
            wx.hideLoading()
          }
        }
      }
    })
  },

  // 显示补签弹窗
  showMakeupModal(e) {
    const medicationId = e.currentTarget.dataset.id
    this.setData({
      currentMedicationId: medicationId,
      showMakeupModal: true,
      makeupDate: ''
    })
  },

  // 隐藏补签弹窗
  hideMakeupModal() {
    this.setData({
      showMakeupModal: false
    })
  },

  // 补签日期选择
  onMakeupDateChange(e) {
    const makeupDate = e.detail.value
    const { currentMedicationId } = this.data

    // 直接补签
    this.doMakeup(currentMedicationId, makeupDate)
  },

  // 执行补签
  async doMakeup(medicationId, date) {
    try {
      util.showLoading('补签中...')
      const res = await api.medicationCheckin({
        medication_id: medicationId,
        record_date: date,
        frequency: 'daily'
      })

      console.log('补签结果:', res)

      if (res && res.success) {
        const progress = res.medication_progress
        util.showToast(`补签成功！已服药 ${progress.days_taken}/${progress.total_days} 天`)
        this.hideMakeupModal()
        this.loadMedications()
      } else {
        util.showToast(res?.error || '补签失败')
      }
    } catch (error) {
      console.error('补签错误:', error)
      const errorMsg = error?.message || error?.error || '补签失败'
      util.showToast(errorMsg)
    } finally {
      wx.hideLoading()
    }
  }
})
