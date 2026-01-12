// pages/upload/upload.js
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    filePath: '',
    checkupDate: '',
    hospital: '',
    workflows: [
      { value: 'vl_model', label: '多模态大模型模式（推荐）' },
      { value: 'ocr_llm', label: 'OCR+LLM模式' },
      { value: 'vlm_transformers', label: 'VLM Transformers模式' }
    ],
    workflowIndex: 0,
    commonHospitals: [],
    uploading: false,
    showProgress: false,
    progress: 0,
    statusText: '',
    processingId: null,
    checkupId: null,
    progressTimer: null
  },

  onLoad() {
    const today = util.formatDate(new Date())
    this.setData({ checkupDate: today })
    this.loadCommonHospitals()
  },

  onUnload() {
    if (this.data.progressTimer) {
      clearInterval(this.data.progressTimer)
    }
  },

  async loadCommonHospitals() {
    try {
      const res = await api.getCommonHospitals()
      this.setData({ commonHospitals: res.data || [] })
    } catch (err) {
      console.error('加载常用医院失败:', err)
    }
  },

  chooseFile() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['pdf', 'png', 'jpg', 'jpeg'],
      success: (res) => {
        const file = res.tempFiles[0]
        this.setData({ filePath: file.path })
      }
    })
  },

  removeFile() {
    this.setData({ filePath: '' })
  },

  onDateChange(e) {
    this.setData({ checkupDate: e.detail.value })
  },

  onHospitalInput(e) {
    this.setData({ hospital: e.detail.value })
  },

  onWorkflowChange(e) {
    this.setData({ workflowIndex: e.detail.value })
  },

  selectHospital(e) {
    const name = e.currentTarget.dataset.name
    this.setData({ hospital: name })
  },

  async handleSubmit() {
    if (!this.data.filePath) {
      util.showToast('请先选择文件')
      return
    }

    if (!this.data.checkupDate) {
      util.showToast('请选择体检日期')
      return
    }

    this.setData({ uploading: true })

    try {
      const formData = {
        checkup_date: this.data.checkupDate,
        hospital: this.data.hospital,
        workflow_type: this.data.workflows[this.data.workflowIndex].value
      }

      const res = await api.uploadReport(this.data.filePath, formData)

      this.setData({
        uploading: false,
        showProgress: true,
        processingId: res.processing_id,
        checkupId: res.checkup_id
      })

      util.showToast('上传成功，开始处理', 'success')
      this.pollProgress()
    } catch (err) {
      this.setData({ uploading: false })
      util.showToast(err.message || '上传失败')
    }
  },

  pollProgress() {
    this.data.progressTimer = setInterval(async () => {
      try {
        const res = await api.getProcessingStatus(this.data.processingId)

        this.setData({
          progress: res.progress || 0,
          statusText: this.getStatusText(res.status)
        })

        if (res.status === 'completed') {
          clearInterval(this.data.progressTimer)
          this.setData({ progress: 100 })
          util.showToast('处理完成', 'success')
        } else if (res.status === 'failed') {
          clearInterval(this.data.progressTimer)
          util.showToast('处理失败：' + (res.error_message || '未知错误'))
        }
      } catch (err) {
        clearInterval(this.data.progressTimer)
        util.showToast('获取状态失败')
      }
    }, 2000)
  },

  getStatusText(status) {
    const statusMap = {
      pending: '等待处理',
      uploading: '上传中',
      ocr_processing: 'OCR识别中',
      ai_processing: 'AI分析中',
      saving_data: '保存数据中',
      completed: '处理完成',
      failed: '处理失败'
    }
    return statusMap[status] || status
  },

  viewResult() {
    wx.navigateTo({
      url: `/pages/checkup-detail/checkup-detail?id=${this.data.checkupId}`
    })
  }
})
