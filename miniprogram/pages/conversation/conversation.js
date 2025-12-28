const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    conversationId: null,
    messages: [],
    inputText: '',
    sending: false
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ conversationId: options.id })
      this.loadMessages(options.id)
    } else {
      this.setData({
        messages: [{ id: 0, role: 'ai', content: '您好！我是AI健康助手，请问有什么可以帮您？' }]
      })
    }
  },

  async loadMessages(id) {
    util.showLoading()
    try {
      const res = await api.getConversationDetail(id)
      const messages = []
      res.data.messages.forEach(m => {
        messages.push({ id: m.id, role: 'user', content: m.question })
        messages.push({ id: m.id + 1000, role: 'ai', content: m.answer })
      })
      this.setData({ messages })
    } catch (err) {
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
    }
  },

  onInputChange(e) {
    this.setData({ inputText: e.detail.value })
  },

  async sendMessage() {
    if (!this.data.inputText || this.data.sending) return

    const userMsg = { id: Date.now(), role: 'user', content: this.data.inputText }
    const messages = [...this.data.messages, userMsg]
    this.setData({ messages, sending: true, inputText: '' })

    // 调用AI API（这里简化处理）
    setTimeout(() => {
      const aiMsg = { id: Date.now() + 1, role: 'ai', content: 'AI正在回复中...' }
      this.setData({ messages: [...messages, aiMsg], sending: false })

      // 实际应该调用AI咨询API
      this.callAI(userMsg.content)
    }, 500)
  },

  async callAI(question) {
    try {
      // 这里简化处理，实际应该调用AI对话API
      const response = '收到您的问题：' + question + '。AI正在分析中...'
      const lastMsg = this.data.messages[this.data.messages.length - 1]
      lastMsg.content = response
      this.setData({ messages: [...this.data.messages] })
    } catch (err) {
      util.showToast('AI回复失败')
    }
  }
})
