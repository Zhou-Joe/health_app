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

  onShow() {
    // 页面显示时，如果有正在处理的上传，恢复轮询
    if (this.data.processingId && !this.data.progressTimer) {
      console.log('恢复轮询处理进度')
      this.pollProgress()
    }
  },

  onHide() {
    // 页面隐藏时，不停止轮询，让它在后台继续运行
    console.log('页面隐藏，轮询继续')
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
      console.error('上传失败详情:', err)
      console.error('错误信息:', err.message)
      console.error('错误堆栈:', err.stack)
      this.setData({ uploading: false })
      util.showToast(err.message || '上传失败')
    }
  },

  pollProgress() {
    console.log('开始轮询处理进度，processingId:', this.data.processingId)

    // 立即执行一次
    this.checkProgress()

    // 然后定时轮询
    this.data.progressTimer = setInterval(() => {
      this.checkProgress()
    }, 2000)
  },

  async checkProgress() {
    try {
      console.log('查询处理状态，processingId:', this.data.processingId)
      const res = await api.getProcessingStatus(this.data.processingId)

      console.log('处理状态响应:', res)

      this.setData({
        progress: res.progress || 0,
        statusText: this.getStatusText(res.status)
      })

      console.log('当前进度:', this.data.progress, '状态:', this.data.statusText)

      if (res.status === 'completed') {
        console.log('处理完成！')
        clearInterval(this.data.progressTimer)
        this.setData({ progress: 100, progressTimer: null })
        util.showToast('处理完成', 'success')
      } else if (res.status === 'failed') {
        console.error('处理失败:', res.error_message)
        clearInterval(this.data.progressTimer)
        this.setData({ progressTimer: null })
        util.showToast('处理失败：' + (res.error_message || '未知错误'))
      }
    } catch (err) {
      console.error('获取状态失败:', err)
      // 不要立即停止轮询，可能是网络波动
      console.log('继续轮询...')
    }
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
