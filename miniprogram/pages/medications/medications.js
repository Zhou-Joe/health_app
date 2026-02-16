// pages/medications/medications.js
const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    groups: [],
    medications: [],
    records: [],
    expandedGroups: {},
    showAddModal: false,
    showRecordsModal: false,
    showClusterModal: false,
    showEditGroupModal: false,
    currentMedicationId: null,
    today: '',
    formData: {
      medicine_name: '',
      dosage: '',
      start_date: '',
      end_date: '',
      notes: ''
    },
    clusterFormData: {
      name: '',
      notes: ''
    },
    editGroupData: {
      id: null,
      name: '',
      notes: '',
      medications: []
    },
    ungroupedMedications: [],
    availableMedications: [],
    selectedCount: 0
  },

  onLoad() {
    this.setData({
      today: util.formatDate(new Date())
    })
    this.loadData()
  },

  onShow() {
    this.loadData()
  },

  async loadData() {
    await Promise.all([
      this.loadMedications(),
      this.loadGroups()
    ])
  },

  async loadMedications() {
    try {
      const res = await api.getMedications()
      const medications = res.medications || []
      const ungroupedMedications = medications.filter(m => !m.group)
      this.setData({ 
        medications: ungroupedMedications
      })
    } catch (error) {
      console.error('加载药单失败:', error)
    }
  },

  async loadGroups() {
    try {
      const res = await api.getMedicationGroups()
      this.setData({ groups: res.groups || [] })
    } catch (error) {
      console.error('加载药单组失败:', error)
    }
  },

  toggleGroup(e) {
    const groupId = e.currentTarget.dataset.id
    const expandedGroups = { ...this.data.expandedGroups }
    expandedGroups[groupId] = !expandedGroups[groupId]
    this.setData({ expandedGroups })
  },

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

  hideAddModal() {
    this.setData({ showAddModal: false })
  },

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

      if (result && result.success) {
        util.showToast('添加成功')
        this.hideAddModal()
        this.loadData()
      } else {
        util.showToast('添加失败：' + (result?.message || '未知错误'))
      }
    } catch (error) {
      console.error('保存药单错误:', error)
      const errorMsg = error?.message || error?.error || '保存失败'
      util.showToast('保存失败：' + errorMsg)
    } finally {
      wx.hideLoading()
    }
  },

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

      if (res && res.success) {
        const progress = res.medication_progress
        util.showToast(`签到成功！已服药 ${progress.days_taken}/${progress.total_days} 天`)
        this.loadData()
      } else {
        util.showToast(res?.message || '签到失败')
      }
    } catch (error) {
      console.error('签到错误:', error)
      const errorMsg = error?.message || error?.error || '签到失败'
      util.showToast(errorMsg)
    } finally {
      wx.hideLoading()
    }
  },

  async viewRecords(e) {
    const medicationId = e.currentTarget.dataset.id
    this.setData({ currentMedicationId: medicationId })

    try {
      util.showLoading('加载中...')
      const res = await api.getMedicationRecords(medicationId)

      if (res && res.success) {
        this.setData({
          records: res.records || [],
          showRecordsModal: true
        })
      } else {
        util.showToast('加载失败：' + (res?.message || '未知错误'))
      }
    } catch (error) {
      console.error('加载记录错误:', error)
      const errorMsg = error?.message || error?.error || '加载失败'
      util.showToast('加载失败：' + errorMsg)
    } finally {
      wx.hideLoading()
    }
  },

  hideRecordsModal() {
    this.setData({ showRecordsModal: false })
  },

  async deleteMedication(e) {
    const medicationId = e.currentTarget.dataset.id

    wx.showModal({
      title: '确认删除',
      content: '确定要删除这个药单吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            util.showLoading('删除中...')
            const result = await api.deleteMedication(medicationId)

            if (result && result.success) {
              util.showToast('删除成功')
              this.loadData()
            } else {
              util.showToast('删除失败：' + (result?.message || '未知错误'))
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

  onMakeupDateChange(e) {
    const makeupDate = e.detail.value
    const medicationId = e.currentTarget.dataset.id
    this.doMakeup(medicationId, makeupDate)
  },

  async doMakeup(medicationId, date) {
    try {
      util.showLoading('补签中...')
      const res = await api.medicationCheckin({
        medication_id: medicationId,
        record_date: date,
        frequency: 'daily'
      })

      if (res && res.success) {
        const progress = res.medication_progress
        util.showToast(`补签成功！已服药 ${progress.days_taken}/${progress.total_days} 天`)
        this.loadData()
      } else {
        util.showToast(res?.message || '补签失败')
      }
    } catch (error) {
      console.error('补签错误:', error)
      const errorMsg = error?.message || error?.error || '补签失败'
      util.showToast(errorMsg)
    } finally {
      wx.hideLoading()
    }
  },

  async showClusterModal() {
    try {
      util.showLoading('加载中...')
      const res = await api.getMedicationsWithoutGroup()
      const ungroupedMedications = (res.medications || []).map(m => ({
        ...m,
        selected: false
      }))
      this.setData({
        showClusterModal: true,
        ungroupedMedications,
        clusterFormData: {
          name: '',
          notes: ''
        },
        selectedCount: 0
      })
    } catch (error) {
      console.error('加载未分组药单失败:', error)
      util.showToast('加载失败')
    } finally {
      wx.hideLoading()
    }
  },

  hideClusterModal() {
    this.setData({ showClusterModal: false })
  },

  onClusterNameInput(e) {
    this.setData({ 'clusterFormData.name': e.detail.value })
  },

  onClusterNotesInput(e) {
    this.setData({ 'clusterFormData.notes': e.detail.value })
  },

  toggleMedicationSelect(e) {
    const medicationId = e.currentTarget.dataset.id
    const ungroupedMedications = this.data.ungroupedMedications.map(m => {
      if (m.id === medicationId) {
        return { ...m, selected: !m.selected }
      }
      return m
    })
    const selectedCount = ungroupedMedications.filter(m => m.selected).length
    this.setData({ ungroupedMedications, selectedCount })
  },

  async createCluster() {
    const selectedMeds = this.data.ungroupedMedications.filter(m => m.selected)
    if (selectedMeds.length === 0) {
      util.showToast('请选择至少一个药物')
      return
    }

    try {
      util.showLoading('创建中...')
      const result = await api.createMedicationGroup({
        name: this.data.clusterFormData.name,
        notes: this.data.clusterFormData.notes,
        medication_ids: selectedMeds.map(m => m.id)
      })

      if (result && result.success) {
        util.showToast(result.message || '创建成功')
        this.hideClusterModal()
        this.loadData()
      } else {
        util.showToast('创建失败：' + (result?.message || '未知错误'))
      }
    } catch (error) {
      console.error('创建药单组错误:', error)
      util.showToast('创建失败：' + (error?.message || '未知错误'))
    } finally {
      wx.hideLoading()
    }
  },

  async autoCluster() {
    wx.showModal({
      title: '自动聚类',
      content: '将根据开始日期相近的药单自动创建药单组，确定继续吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            util.showLoading('聚类中...')
            const result = await api.autoClusterMedications({ days_threshold: 3 })

            if (result && result.success) {
              util.showToast(result.message || '聚类完成')
              this.loadData()
            } else {
              util.showToast('聚类失败：' + (result?.message || '未知错误'))
            }
          } catch (error) {
            console.error('自动聚类错误:', error)
            util.showToast('聚类失败：' + (error?.message || '未知错误'))
          } finally {
            wx.hideLoading()
          }
        }
      }
    })
  },

  async groupCheckin(e) {
    const groupId = e.currentTarget.dataset.id
    const today = util.formatDate(new Date())

    try {
      util.showLoading('批量签到中...')
      const res = await api.medicationGroupCheckin(groupId, {
        record_date: today,
        frequency: 'daily'
      })

      if (res && res.success) {
        util.showToast(res.message || '批量签到成功')
        this.loadData()
      } else {
        util.showToast(res?.message || '签到失败')
      }
    } catch (error) {
      console.error('批量签到错误:', error)
      util.showToast('签到失败：' + (error?.message || '未知错误'))
    } finally {
      wx.hideLoading()
    }
  },

  async showEditGroupModal(e) {
    const group = e.currentTarget.dataset.group
    try {
      util.showLoading('加载中...')
      const res = await api.getMedicationGroupDetail(group.id)
      const res2 = await api.getMedicationsWithoutGroup()
      
      const availableMedications = (res2.medications || []).map(m => ({
        ...m,
        selected: false
      }))

      this.setData({
        showEditGroupModal: true,
        editGroupData: {
          id: res.group.id,
          name: res.group.name,
          notes: res.group.ai_summary || '',
          medications: res.medications || [],
          removeMedicationIds: [],
          addMedicationIds: []
        },
        availableMedications
      })
    } catch (error) {
      console.error('加载药单组详情失败:', error)
      util.showToast('加载失败')
    } finally {
      wx.hideLoading()
    }
  },

  hideEditGroupModal() {
    this.setData({ showEditGroupModal: false })
  },

  onEditGroupNameInput(e) {
    this.setData({ 'editGroupData.name': e.detail.value })
  },

  onEditGroupNotesInput(e) {
    this.setData({ 'editGroupData.notes': e.detail.value })
  },

  removeMedFromGroup(e) {
    const medicationId = e.currentTarget.dataset.id
    const medications = this.data.editGroupData.medications.filter(m => m.id !== medicationId)
    const removeMedicationIds = [...this.data.editGroupData.removeMedicationIds, medicationId]
    this.setData({
      'editGroupData.medications': medications,
      'editGroupData.removeMedicationIds': removeMedicationIds
    })
  },

  toggleAvailableMedSelect(e) {
    const medicationId = e.currentTarget.dataset.id
    const availableMedications = this.data.availableMedications.map(m => {
      if (m.id === medicationId) {
        return { ...m, selected: !m.selected }
      }
      return m
    })
    const addMedicationIds = availableMedications.filter(m => m.selected).map(m => m.id)
    this.setData({ availableMedications, 'editGroupData.addMedicationIds': addMedicationIds })
  },

  async updateGroup() {
    const { id, name, notes, removeMedicationIds, addMedicationIds } = this.data.editGroupData

    try {
      util.showLoading('保存中...')
      const result = await api.updateMedicationGroup(id, {
        name,
        notes,
        remove_medication_ids: removeMedicationIds,
        add_medication_ids: addMedicationIds
      })

      if (result && result.success) {
        util.showToast('保存成功')
        this.hideEditGroupModal()
        this.loadData()
      } else {
        util.showToast('保存失败：' + (result?.message || '未知错误'))
      }
    } catch (error) {
      console.error('更新药单组错误:', error)
      util.showToast('保存失败：' + (error?.message || '未知错误'))
    } finally {
      wx.hideLoading()
    }
  },

  async deleteGroup(e) {
    const groupId = e.currentTarget.dataset.id

    wx.showModal({
      title: '删除药单组',
      content: '选择删除方式',
      confirmText: '仅删除组',
      cancelText: '取消',
      success: async (res) => {
        if (res.confirm) {
          try {
            util.showLoading('删除中...')
            const result = await api.deleteMedicationGroup(groupId, 'delete_group')
            if (result && result.success) {
              util.showToast('删除成功')
              this.loadData()
            } else {
              util.showToast('删除失败：' + (result?.message || '未知错误'))
            }
          } catch (error) {
            console.error('删除药单组错误:', error)
            util.showToast('删除失败')
          } finally {
            wx.hideLoading()
          }
        }
      }
    })
  }
})
