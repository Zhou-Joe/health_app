// pages/upload/upload.js
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    filePath: '',
    fileName: '',
    fileType: '', // 'image' 或 'pdf'
    checkupDate: '',
    hospital: '',
    notes: '',
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
    // 清理定时器
    if (this.data.progressTimer) {
      clearInterval(this.data.progressTimer)
      this.setData({ progressTimer: null })
    }
    wx.hideLoading()
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
    console.log('页面隐藏，轮询继续，当前状态:', this.data.statusText)
    // 关闭loading提示，避免阻塞用户操作
    wx.hideLoading()
  },

  chooseImage() {
    wx.chooseImage({
      count: 1,
      sizeType: ['original', 'compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const filePath = res.tempFilePaths[0]
        this.setData({
          filePath: filePath,
          fileName: 'report.jpg',
          fileType: 'image'
        })
      },
      fail: (err) => {
        console.error('选择图片失败:', err)
        util.showToast('选择图片失败')
      }
    })
  },

  choosePDF() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['pdf'],
      success: (res) => {
        const file = res.tempFiles[0]
        this.setData({
          filePath: file.path,
          fileName: file.name,
          fileType: 'pdf'
        })
      },
      fail: (err) => {
        console.error('选择PDF失败:', err)
        util.showToast('选择PDF失败')
      }
    })
  },

  removeFile() {
    this.setData({
      filePath: '',
      fileName: '',
      fileType: ''
    })
  },

  onDateChange(e) {
    this.setData({ checkupDate: e.detail.value })
  },

  onHospitalInput(e) {
    this.setData({ hospital: e.detail.value })
  },

  onNotesInput(e) {
    this.setData({ notes: e.detail.value })
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
      // 根据文件类型自动选择处理模式
      const isPDF = this.data.fileType === 'pdf'
      const workflow_type = isPDF ? 'ocr_llm' : 'vl_model'

      const formData = {
        checkup_date: this.data.checkupDate,
        hospital: this.data.hospital,
        notes: this.data.notes,
        workflow_type: workflow_type
      }

      const res = await api.uploadReport(this.data.filePath, formData)

      this.setData({
        uploading: false,
        showProgress: true,
        processingId: res.processing_id,
        checkupId: res.checkup_id
      })

      // 检查是否合并到现有报告
      if (res.is_merged || res.merged_into_existing) {
        wx.showModal({
          title: '报告合并',
          content: res.message || '已合并到现有报告中',
          showCancel: false,
          confirmText: '查看报告',
          success: () => {
            // 跳转到报告详情页
            wx.redirectTo({
              url: `/pages/checkup-detail/checkup-detail?id=${this.data.checkupId}`
            })
          }
        })
        return
      }

      util.showToast('上传成功，后台处理中...')
      this.pollProgress()

      // 显示loading提示后台处理中
      wx.showLoading({
        title: '正在处理报告...',
        mask: true
      })
    } catch (err) {
      console.error('上传失败详情:', err)
      console.error('错误信息:', err.message)
      console.error('错误堆栈:', err.stack)
      this.setData({ uploading: false })
      wx.hideLoading()
      util.showToast(err.message || '上传失败')
    }
  },

  pollProgress() {
    console.log('开始轮询处理进度，processingId:', this.data.processingId)

    // 立即执行一次
    this.checkProgress()

    // 然后定时轮询
    const timer = setInterval(() => {
      this.checkProgress()
    }, 2000)

    // 保存timer到data中
    this.setData({ progressTimer: timer })
  },

  async checkProgress() {
    // 如果已经完成或失败，不再查询
    if (this.data.progress === 100 || this.data.statusText === '处理失败') {
      return
    }

    try {
      console.log('查询处理状态，processingId:', this.data.processingId)
      const res = await api.getProcessingStatus(this.data.processingId)

      console.log('处理状态响应:', res)

      const statusText = this.getStatusText(res.status)
      const oldStatus = this.data.statusText

      this.setData({
        progress: res.progress || 0,
        statusText: statusText
      })

      console.log('当前进度:', this.data.progress, '状态:', this.data.statusText)

      // 状态变化时显示对应的toast
      if (oldStatus !== statusText && statusText !== '处理完成' && statusText !== '处理失败') {
        util.showToast(statusText + '...')
      }

      if (res.status === 'completed') {
        console.log('处理完成！')
        // 停止轮询
        if (this.data.progressTimer) {
          clearInterval(this.data.progressTimer)
          this.setData({
            progress: 100,
            progressTimer: null,
            statusText: '处理完成'
          })
        }
        wx.hideLoading()

        // 显示成功提示
        wx.showToast({
          title: '✅ 处理完成！',
          icon: 'success',
          duration: 1500
        })

        // 自动跳转到报告详情页
        setTimeout(() => {
          wx.redirectTo({
            url: `/pages/checkup-detail/checkup-detail?id=${this.data.checkupId}`
          })
        }, 1500)
      } else if (res.status === 'failed') {
        console.error('处理失败:', res.error_message)
        // 停止轮询
        if (this.data.progressTimer) {
          clearInterval(this.data.progressTimer)
          this.setData({
            progressTimer: null,
            statusText: '处理失败'
          })
        }
        wx.hideLoading()
        util.showToast('❌ 处理失败：' + (res.error_message || '未知错误'))
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
  }
})
