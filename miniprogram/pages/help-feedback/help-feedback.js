const util = require('../../utils/util.js')

Page({
  data: {
    email: '',
    feedback: '',
    submitting: false,
    faqList: [
      {
        question: '如何上传体检报告？',
        answer: '在首页点击"上传"按钮，选择体检报告文件（支持 PDF、图片格式），填写体检日期和机构后提交即可。'
      },
      {
        question: '报告上传后多久能处理完成？',
        answer: '通常 1-3 分钟内可以完成处理，具体时间取决于报告大小和网络状况。您可以在"报告"页面查看处理进度。'
      },
      {
        question: '如何与 AI 医生对话？',
        answer: '进入"AI咨询"页面，点击"新建对话"，输入您的问题即可。您还可以选择相关的体检报告让 AI 医生参考。'
      },
      {
        question: '如何管理我的药单？',
        answer: '在"我的"页面，点击"药单管理"，您可以添加新的药物信息、设置用药提醒，以及查看服药记录。'
      },
      {
        question: '数据安全吗？',
        answer: '您的健康数据采用SSL加密传输，存储在安全的服务器上。我们不会向第三方共享您的个人信息。'
      }
    ],
    expandedIndex: -1
  },

  onEmailInput(e) {
    this.setData({ email: e.detail.value })
  },

  onFeedbackInput(e) {
    this.setData({ feedback: e.detail.value })
  },

  toggleFaq(e) {
    const index = e.currentTarget.dataset.index
    if (this.data.expandedIndex === index) {
      this.setData({ expandedIndex: -1 })
    } else {
      this.setData({ expandedIndex: index })
    }
  },

  async submitFeedback() {
    if (!this.data.feedback.trim()) {
      util.showToast('请输入反馈内容')
      return
    }

    this.setData({ submitting: true })

    try {
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      wx.showModal({
        title: '提交成功',
        content: '感谢您的反馈！我们会尽快处理。',
        showCancel: false,
        confirmText: '确定',
        success: () => {
          this.setData({
            email: '',
            feedback: ''
          })
        }
      })
    } catch (err) {
      util.showToast('提交失败，请稍后重试')
    } finally {
      this.setData({ submitting: false })
    }
  },

  copyToClipboard(e) {
    const text = e.currentTarget.dataset.text
    wx.setClipboardData({
      data: text,
      success: () => {
        util.showToast('已复制')
      }
    })
  }
})
