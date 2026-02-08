/**
 * AI对话页面
 * 支持新建对话和继续对话，报告选择，流式响应等
 */

const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')
const config = require('../../config.js')

Page({
  data: {
    conversationId: null,
    messages: [],
    lastMessageId: null,
    inputText: '',
    sending: false,
    // 报告选择
    reports: [],
    selectedReportIds: [],
    showReportSelector: false,
    reportsNoSelection: false, // 标记是否选择了"不使用报告"
    reportsLoading: false, // 报告加载状态（改为false）
    reportsError: null, // 报告加载错误
    reportsLoaded: false, // 是否已加载过报告
    // 药单选择
    medications: [],
    selectedMedicationIds: [],
    showMedicationSelector: false,
    includeMedications: false, // 是否包含药单信息
    medicationsNoSelection: false, // 标记是否选择了"不使用药单"
    medicationsLoading: false, // 药单加载状态（改为false）
    medicationsError: null, // 药单加载错误
    medicationsLoaded: false, // 是否已加载过药单
    // 对话模式
    conversationMode: 'new', // 'new' 或 'continue'
    // AI响应流式内容
    streamingContent: '',
    isStreaming: false,
    // 轮询相关
    isGenerating: false,
    pollTimer: null,
    streamTimer: null,
    adviceId: null,
    // 新增字段
    showAttachmentMenu: false,
    scrollToView: ''
  },

  onLoad(options) {
    const conversationId = options.id
    const isGenerating = options.generating === 'true'
    const adviceId = options.adviceId ? parseInt(options.adviceId) : null

    // 恢复上次的选择
    this.restoreLastSelection()

    if (conversationId) {
      // 继续对话
      console.log('[小程序对话页] 加载对话 - conversation_id:', conversationId, '继续对话模式')
      this.setData({
        conversationId: parseInt(conversationId),
        conversationMode: 'continue',
        isGenerating: isGenerating,
        adviceId: adviceId
      })

      if (isGenerating && adviceId) {
        // 如果是正在生成状态且有adviceId，显示思考提示并开始流式轮询
        const thinkingMsg = 'AI正在思考中...'
        this.setData({
          messages: [{
            id: adviceId,
            role: 'ai',
            content: thinkingMsg,
            previewText: thinkingMsg,
            previewShort: thinkingMsg,
            isStreaming: true,
            expanded: false
          }],
          lastMessageId: adviceId
        })
        this.startStreamingPoll()
      } else if (isGenerating) {
        // 没有adviceId，使用普通轮询
        const thinkingMsg = 'AI医生诊断中...'
        this.setData({
          messages: [{
            id: 'thinking',
            role: 'ai',
            content: thinkingMsg,
            previewText: thinkingMsg,
            previewShort: thinkingMsg,
            isThinking: true,
            expanded: false
          }],
          lastMessageId: 'thinking'
        })
        this.startPolling()
      } else {
        this.loadConversation(conversationId)
      }
    } else {
      // 新对话
      const welcomeMessage = '您好！我是AI健康助手。请问有什么可以帮您？\n\n您可以：\n• 直接向我咨询健康问题\n• 选择体检报告让我分析\n• 我会基于您的数据提供专业建议'
      this.setData({
        conversationMode: 'new',
        messages: [{
          id: 0,
          role: 'ai',
          content: welcomeMessage,
          previewText: this.stripMarkdown(welcomeMessage),
          previewShort: this.generatePreviewText(welcomeMessage),
          expanded: false
        }],
        lastMessageId: 0
      })
      this.loadReports()
      this.loadMedications()
    }
  },

  onUnload() {
    // 页面卸载时清除轮询定时器
    if (this.data.pollTimer) {
      clearInterval(this.data.pollTimer)
    }
    if (this.data.streamTimer) {
      clearInterval(this.data.streamTimer)
    }
  },

  /**
   * 开始流式轮询（高频轮询获取AI生成内容）
   */
  startStreamingPoll() {
    let pollCount = 0
    const maxPolls = 600 // 最多轮询600次（600次 * 0.5秒 = 300秒 = 5分钟）

    this.data.streamTimer = setInterval(async () => {
      pollCount++

      try {
        const res = await api.getAdviceMessageStatus(this.data.adviceId)
        const messageData = res.data

        if (messageData) {
          const currentAnswer = messageData.answer || ''
          const isGenerating = messageData.is_generating

          // 如果生成完成（有内容且不在生成中），显示完整回答
          if (!isGenerating && currentAnswer.length > 0) {
            clearInterval(this.data.streamTimer)
            this.setData({ streamTimer: null, isGenerating: false })

            // 更新消息内容
            const messages = this.data.messages.map(msg => {
              if (msg.id === this.data.adviceId) {
                return {
                  ...msg,
                  content: currentAnswer,
                  previewText: this.stripMarkdown(currentAnswer),
                  previewShort: this.generatePreviewText(currentAnswer),
                  markdownData: this.convertMarkdown(currentAnswer),
                  isStreaming: false
                }
              }
              return msg
            })

            this.setData({
              messages,
              lastMessageId: messages.length > 0 ? messages[messages.length - 1].id : null
            })
            util.showToast('AI回复已生成')
          } else if (pollCount >= maxPolls) {
            // 超过最大轮询次数
            clearInterval(this.data.streamTimer)
            this.setData({ streamTimer: null, isGenerating: false })
            util.showToast('AI响应超时，请稍后刷新', 'warning')
          }
        }
      } catch (err) {
        console.error('流式轮询失败:', err)
      }
    }, 500) // 每500毫秒轮询一次（高频）
  },

  /**
   * 开始普通轮询等待AI响应
   */
  startPolling() {
    let pollCount = 0
    const maxPolls = 150 // 最多轮询150次（150次 * 2秒 = 300秒 = 5分钟）

    this.data.pollTimer = setInterval(async () => {
      pollCount++

      try {
        const res = await api.getConversationMessages(this.data.conversationId)
        const messageList = res.data?.messages || []

        // 如果有消息了，说明AI已经生成完成
        if (messageList.length > 0) {
          // 停止轮询
          clearInterval(this.data.pollTimer)
          this.setData({ pollTimer: null, isGenerating: false })

          // 重新加载对话
          this.loadConversation(this.data.conversationId)
          util.showToast('AI回复已生成')
        } else if (pollCount >= maxPolls) {
          // 超过最大轮询次数
          clearInterval(this.data.pollTimer)
          this.setData({ pollTimer: null, isGenerating: false })
          util.showToast('AI响应超时，请稍后刷新', 'warning')
        }
      } catch (err) {
        console.error('轮询失败:', err)
      }
    }, 2000) // 每2秒轮询一次
  },

  /**
   * 滚动到底部
   */
  scrollToBottom() {
    wx.createSelectorQuery()
      .select('#message-list')
      .boundingClientRect()
      .exec(function(res) {
        if (res[0]) {
          wx.pageScrollTo({
            scrollTop: res[0].bottom,
            duration: 300
          })
        }
      })
  },

  /**
   * 加载对话历史
   */
  async loadConversation(conversationId) {
    console.log('[loadConversation] 开始加载对话, conversationId:', conversationId)
    util.showLoading('加载中...')

    // 设置超时保护
    const timeout = setTimeout(() => {
      console.error('[loadConversation] 加载超时')
      util.hideLoading()
      util.showToast('加载超时，请重试')
    }, 15000) // 15秒超时

    try {
      console.log('[loadConversation] 调用API获取对话消息...')
      const res = await api.getConversationMessages(conversationId)
      console.log('[loadConversation] API返回:', res)

      clearTimeout(timeout)

      const messages = []

      // 将消息转换为聊天格式
      // 后端返回结构: { success: true, data: { messages: [...] } }
      const messageList = res.data?.messages || []
      console.log('[loadConversation] 消息列表长度:', messageList.length)

      messageList.forEach((msg, index) => {
        console.log(`[loadConversation] 处理消息 ${index + 1}/${messageList.length}, answer长度:`, msg.answer?.length || 0)

        // 格式化时间，去掉毫秒
        const formattedTime = util.formatDate(new Date(msg.created_at), 'YYYY-MM-DD HH:mm:ss')

        messages.push({
          id: msg.id,
          role: 'user',
          content: msg.question,
          created_at: formattedTime
        })

        // AI消息转换为Markdown（延迟处理，避免阻塞）
        const aiContent = msg.answer || ''
        const aiMsg = {
          id: msg.id + 1000,
          role: 'ai',
          content: aiContent,
          previewText: this.stripMarkdown(aiContent),
          previewShort: this.generatePreviewText(aiContent),
          created_at: formattedTime,
          prompt_sent: msg.prompt_sent,
          expanded: false
        }

        // 如果内容不太长，立即转换markdown
        if (aiContent.length < 5000) {
          aiMsg.markdownData = this.convertMarkdown(aiContent)
        }

        messages.push(aiMsg)
      })

      // 获取对话中最后一条消息使用的报告ID
      const lastSelectedReports = res.data?.last_selected_reports || []

      console.log('[loadConversation] 设置数据，消息数量:', messages.length)

      this.setData({
        messages,
        selectedReportIds: lastSelectedReports,
        lastMessageId: messages.length > 0 ? messages[messages.length - 1].id : null
      })

      console.log('[loadConversation] 加载完成')

      // 延迟处理长文本的markdown转换
      setTimeout(() => {
        const updatedMessages = this.data.messages.map(msg => {
          if (msg.role === 'ai' && !msg.markdownData && msg.content) {
            return {
              ...msg,
              markdownData: this.convertMarkdown(msg.content)
            }
          }
          return msg
        })
        this.setData({ messages: updatedMessages })
        console.log('[loadConversation] Markdown转换完成（延迟处理）')
      }, 100)

    } catch (err) {
      clearTimeout(timeout)
      console.error('[loadConversation] 加载对话失败:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
    }
  },

  /**
   * 将Markdown文本转换为HTML
   * 使用小程序rich-text组件渲染
   */
  convertMarkdown(content) {
    if (!content) {
      return null
    }

    try {
      console.log('[convertMarkdown] 开始转换，内容长度:', content.length)

      // 限制处理长度，避免性能问题
      const maxLength = 10000 // 最大处理10万字符
      if (content.length > maxLength) {
        console.warn('[convertMarkdown] 内容过长，截断处理:', content.length, '->', maxLength)
        content = content.substring(0, maxLength) + '\n\n...(内容过长，已截断)'
      }

      let html = content

      // 简化处理：只处理常用的markdown格式
      // 1. 代码块
      html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        return `<pre><code>${this.escapeHtml(code.trim())}</code></pre>`
      })

      // 2. 转义HTML特殊字符
      html = this.escapeHtml(html)

      // 3. 标题（h1-h6）
      html = html.replace(/^######\s+(.*)$/gm, '<h6>$1</h6>')
      html = html.replace(/^#####\s+(.*)$/gm, '<h5>$1</h5>')
      html = html.replace(/^####\s+(.*)$/gm, '<h4>$1</h4>')
      html = html.replace(/^###\s+(.*)$/gm, '<h3>$1</h3>')
      html = html.replace(/^##\s+(.*)$/gm, '<h2>$1</h2>')
      html = html.replace(/^#\s+(.*)$/gm, '<h1>$1</h1>')

      // 4. 粗体和斜体
      html = html.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>')
      html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')

      // 5. 行内代码
      html = html.replace(/`([^`]+)`/g, '<code>$1</code>')

      // 6. 换行处理
      html = html.replace(/\n\n+/g, '</p><p>')
      html = html.replace(/\n/g, '<br>')

      // 包裹在段落中
      html = `<p>${html}</p>`

      console.log('[convertMarkdown] 转换完成')
      return html
    } catch (e) {
      console.error('[convertMarkdown] 转换失败:', e)
      return null
    }
  },

  escapeHtml(text) {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    }
    return text.replace(/[&<>"']/g, m => map[m])
  },

  /**
   * 去除Markdown格式，用于折叠状态预览
   */
  stripMarkdown(content) {
    if (!content) {
      return ''
    }

    return content
      // 去除代码块（保留内容）
      .replace(/```[\s\S]*?```/g, (match) => {
        const code = match.replace(/```\w*\n?/g, '').replace(/```/g, '')
        return code.trim() || '代码'
      })
      // 去除行内代码（保留内容）
      .replace(/`([^`]+)`/g, '$1')
      // 去除粗体和斜体标记（保留内容）
      .replace(/\*\*/g, '')
      .replace(/\*/g, '')
      // 去除标题标记（保留内容）
      .replace(/^#{1,3}\s+/gm, '')
      // 去除列表标记（保留内容）
      .replace(/^\s*[-*+]\s+/gm, '')
      // 去除引用标记（保留内容）
      .replace(/^>\s+/gm, '')
      // 去除链接格式 [text](url) -> text
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      // 将多个换行替换为空格
      .replace(/\n+/g, ' ')
      // 去除多余空格
      .replace(/\s{2,}/g, ' ')
      .trim()
  },

  /**
   * 生成预览文本（前100字）
   */
  generatePreviewText(content) {
    if (!content) {
      return ''
    }

    const plainText = this.stripMarkdown(content)
    return plainText.length > 100 ? plainText.substring(0, 100) : plainText
  },

  /**
   * 加载报告列表
   */
  async loadReports() {
    try {
      this.setData({ reportsLoading: true, reportsError: null })

      const res = await api.getCheckups({ page_size: 100 })

      // 后端返回格式: { success: true, checkups: [...], count: ... }
      const checkupsData = res.checkups || res.data || res.results || []

      const reports = checkupsData.map(r => {
        // 安全地格式化日期
        let formattedDate = ''
        try {
          formattedDate = util.formatDate(r.checkup_date, 'YYYY-MM-DD')
        } catch (e) {
          console.error('[对话] 日期格式化失败:', r.checkup_date, e)
          formattedDate = r.checkup_date || ''
        }

        return {
          id: r.id,
          hospital: r.hospital || '未知机构',
          checkup_date: formattedDate,
          indicators_count: r.indicator_count || r.indicators_count || 0,
          selected: false
        }
      })


      this.setData({
        reports,
        reportsLoading: false,
        reportsLoaded: true
      })

      // 恢复上次的选择
      this.restoreReportSelection()

    } catch (err) {
      console.error('[对话] 加载报告列表失败:', err)
      this.setData({
        reportsLoading: false,
        reportsError: err.message || '加载报告失败',
        reportsLoaded: true
      })
    }
  },

  /**
   * 加载药单列表
   */
  async loadMedications() {
    try {
      this.setData({ medicationsLoading: true, medicationsError: null })
      const res = await api.getMedications()

      // 后端返回格式: { success: true, medications: [...] }
      const medications = (res.medications || []).map(m => ({
        ...m,
        medicine_name: m.medicine_name,
        dosage: m.dosage,
        start_date: util.formatDate(m.start_date, 'YYYY-MM-DD'),
        end_date: util.formatDate(m.end_date, 'YYYY-MM-DD'),
        days_taken: m.days_taken || 0,
        total_days: m.total_days || 0,
        selected: false
      }))

      this.setData({
        medications,
        medicationsLoading: false,
        medicationsLoaded: true
      })

      // 恢复上次的选择
      this.restoreMedicationSelection()

    } catch (err) {
      console.error('加载药单列表失败:', err)
      this.setData({
        medicationsLoading: false,
        medicationsError: err.message || '加载药单失败',
        medicationsLoaded: true
      })
    }
  },

  /**
   * 恢复上次的选择
   */
  restoreLastSelection() {
    try {
      const lastSelection = wx.getStorageSync('lastConsultationSelection')
      if (lastSelection) {
        if (lastSelection.selectedReportIds && lastSelection.selectedReportIds.length > 0) {
          this.setData({
            selectedReportIds: lastSelection.selectedReportIds,
            reportsNoSelection: lastSelection.reportsNoSelection || false
          })
        }
        if (lastSelection.selectedMedicationIds && lastSelection.selectedMedicationIds.length > 0) {
          this.setData({
            selectedMedicationIds: lastSelection.selectedMedicationIds,
            medicationsNoSelection: lastSelection.medicationsNoSelection || false
          })
        }
      }
    } catch (err) {
      console.error('恢复选择失败:', err)
    }
  },

  /**
   * 恢复报告选择
   */
  restoreReportSelection() {
    try {
      const lastSelection = wx.getStorageSync('lastConsultationSelection')
      if (lastSelection && lastSelection.selectedReportIds && lastSelection.selectedReportIds.length > 0) {
        const reports = this.data.reports.map(r => ({
          ...r,
          selected: lastSelection.selectedReportIds.includes(r.id)
        }))
        this.setData({
          reports,
          selectedReportIds: lastSelection.selectedReportIds,
          reportsNoSelection: lastSelection.reportsNoSelection || false
        })
      }
    } catch (err) {
      console.error('恢复报告选择失败:', err)
    }
  },

  /**
   * 恢复药单选择
   */
  restoreMedicationSelection() {
    try {
      const lastSelection = wx.getStorageSync('lastConsultationSelection')
      if (lastSelection && lastSelection.selectedMedicationIds && lastSelection.selectedMedicationIds.length > 0) {
        const medications = this.data.medications.map(m => ({
          ...m,
          selected: lastSelection.selectedMedicationIds.includes(m.id)
        }))
        this.setData({
          medications,
          selectedMedicationIds: lastSelection.selectedMedicationIds,
          medicationsNoSelection: lastSelection.medicationsNoSelection || false
        })
      }
    } catch (err) {
      console.error('恢复药单选择失败:', err)
    }
  },

  /**
   * 保存当前选择
   */
  saveCurrentSelection() {
    try {
      const selection = {
        selectedReportIds: this.data.selectedReportIds,
        selectedMedicationIds: this.data.selectedMedicationIds,
        reportsNoSelection: this.data.reportsNoSelection,
        medicationsNoSelection: this.data.medicationsNoSelection,
        timestamp: new Date().getTime()
      }
      wx.setStorageSync('lastConsultationSelection', selection)
    } catch (err) {
      console.error('保存选择失败:', err)
    }
  },

  /**
   * 切换报告选择器
   */
  toggleReportSelector() {
    const willShow = !this.data.showReportSelector

    // 如果打开选择器且还没有加载过数据，则加载数据
    if (willShow && !this.data.reportsLoaded) {
      this.loadReports()
    }

    this.setData({
      showReportSelector: willShow
    })
  },

  /**
   * 打开报告选择器（同时关闭附件菜单）
   */
  openReportSelector() {
    // 先关闭附件菜单
    this.setData({ showAttachmentMenu: false })

    // 如果还没有加载过数据，则加载数据
    if (!this.data.reportsLoaded) {
      this.loadReports()
    }

    // 然后打开报告选择器
    setTimeout(() => {
      this.setData({ showReportSelector: true })
    }, 100)
  },

  /**
   * 切换报告选择
   */
  toggleReport(e) {
    const id = e.currentTarget.dataset.id
    const reports = this.data.reports.map(r => {
      if (r.id === id) {
        return { ...r, selected: !r.selected }
      }
      return r
    })

    const selectedReportIds = reports
      .filter(r => r.selected)
      .map(r => r.id)

    this.setData({
      reports,
      selectedReportIds,
      reportsNoSelection: false
    })

    // 保存选择
    this.saveCurrentSelection()
  },

  /**
   * 选择"不使用任何报告"
   */
  selectNoReports() {
    const reports = this.data.reports.map(r => ({ ...r, selected: false }))
    this.setData({
      reports,
      selectedReportIds: [],
      reportsNoSelection: true
    })
    util.showToast('已选择不使用任何报告')

    // 保存选择
    this.saveCurrentSelection()
  },

  /**
   * 全选/取消全选报告
   */
  toggleSelectAll() {
    const allSelected = this.data.selectedReportIds.length === this.data.reports.length
    const reports = this.data.reports.map(r => ({
      ...r,
      selected: !allSelected
    }))
    const selectedReportIds = !allSelected ? reports.map(r => r.id) : []

    this.setData({ reports, selectedReportIds })

    // 保存选择
    this.saveCurrentSelection()
  },

  /**
   * 切换药单选择器
   */
  toggleMedicationSelector() {
    const willShow = !this.data.showMedicationSelector

    // 如果打开选择器且还没有加载过数据，则加载数据
    if (willShow && !this.data.medicationsLoaded) {
      this.loadMedications()
    }

    this.setData({
      showMedicationSelector: willShow
    })
  },

  /**
   * 打吃药单选择器（同时关闭附件菜单）
   */
  openMedicationSelector() {
    // 先关闭附件菜单
    this.setData({ showAttachmentMenu: false })

    // 如果还没有加载过数据，则加载数据
    if (!this.data.medicationsLoaded) {
      this.loadMedications()
    }

    // 然后吃药单选择器
    setTimeout(() => {
      this.setData({ showMedicationSelector: true })
    }, 100)
  },

  /**
   * 切换是否包含药单
   */
  toggleIncludeMedications() {
    this.setData({
      includeMedications: !this.data.includeMedications
    })
  },

  /**
   * 选择"不使用任何药单"
   */
  selectNoMedications() {
    const medications = this.data.medications.map(m => ({ ...m, selected: false }))
    this.setData({
      medications,
      selectedMedicationIds: [],
      medicationsNoSelection: true
    })
    util.showToast('已选择不使用任何药单')

    // 保存选择
    this.saveCurrentSelection()
  },

  /**
   * 切换药单选择
   */
  toggleMedication(e) {
    const id = e.currentTarget.dataset.id
    const medications = this.data.medications.map(m => {
      if (m.id === id) {
        return { ...m, selected: !m.selected }
      }
      return m
    })

    const selectedMedicationIds = medications
      .filter(m => m.selected)
      .map(m => m.id)

    this.setData({
      medications,
      selectedMedicationIds,
      medicationsNoSelection: false
    })

    // 保存选择
    this.saveCurrentSelection()
  },

  /**
   * 全选/取消全选药单
   */
  toggleSelectAllMedications() {
    const allSelected = this.data.selectedMedicationIds.length === this.data.medications.length
    const medications = this.data.medications.map(m => ({
      ...m,
      selected: !allSelected
    }))
    const selectedMedicationIds = !allSelected ? medications.map(m => m.id) : []

    this.setData({ medications, selectedMedicationIds })

    // 保存选择
    this.saveCurrentSelection()
  },

  /**
   * 输入框内容变化
   */
  onInputChange(e) {
    this.setData({ inputText: e.detail.value })
  },

  /**
   * 处理发送按钮点击
   */
  handleSendTap() {
    const inputText = this.data.inputText.trim()

    if (!inputText) {
      util.showToast('请输入您的健康问题')
      return
    }

    if (this.data.sending) return

    this.sendMessage()
  },

  /**
   * 处理导出按钮点击
   */
  handleExport() {
    this.exportConversation()
  },

  /**
   * 发送消息
   */
  async sendMessage() {
    const inputText = this.data.inputText.trim()

    if (!inputText) {
      util.showToast('请输入您的健康问题')
      return
    }

    if (inputText.length < 5) {
      util.showToast('请详细描述您的问题，至少5个字符')
      return
    }

    if (this.data.sending) return

    // 添加用户消息
    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: inputText,
      created_at: util.formatDate(new Date(), 'YYYY-MM-DD HH:mm:ss')
    }

    const messages = [...this.data.messages, userMsg]
    this.setData({
      messages,
      inputText: '',
      sending: true,
      isStreaming: true,
      streamingContent: '',
      lastMessageId: userMsg.id
    })

    // 滚动到底部
    this.scrollToBottom()

    try {
      // 准备请求数据
      const requestData = {
        question: inputText,
        selected_reports: this.data.selectedReportIds
      }

      // 如果选择了药单（且不是"不使用药单"），添加药单信息
      if (this.data.selectedMedicationIds.length > 0 && !this.data.medicationsNoSelection) {
        requestData.selected_medications = this.data.selectedMedicationIds
      }

      if (this.data.conversationMode === 'continue' && this.data.conversationId) {
        requestData.conversation_id = this.data.conversationId
        console.log('[小程序对话页] 继续对话模式 - conversation_id:', this.data.conversationId)
      } else {
        console.log('[小程序对话页] 新对话模式')
      }

      console.log('[小程序对话页] 发送消息请求数据:', JSON.stringify({
        question: requestData.question.substring(0, 50) + '...',
        conversation_id: requestData.conversation_id || '(none)',
        has_reports: (this.data.selectedReportIds || []).length > 0
      }))

      // 由于小程序不支持SSE，使用普通请求
      // 添加AI占位消息
      const analyzingMsg = '正在分析您的健康数据，请稍候...'
      const aiMsg = {
        id: Date.now() + 1,
        role: 'ai',
        content: analyzingMsg,
        previewText: analyzingMsg,
        previewShort: analyzingMsg,
        created_at: util.formatDate(new Date(), 'YYYY-MM-DD HH:mm:ss'),
        expanded: false
      }

      this.setData({
        messages: [...messages, aiMsg],
        lastMessageId: aiMsg.id
      })

      this.scrollToBottom()

      // 调用API
      const res = await api.getAdvice(requestData)

      // 更新AI消息内容
      const aiAnswer = res.answer || res.data?.answer || '抱歉，AI医生暂时无法回复，请稍后重试。'
      const updatedMessages = this.data.messages.map(msg => {
        if (msg.id === aiMsg.id) {
          return {
            ...msg,
            content: aiAnswer,
            previewText: this.stripMarkdown(aiAnswer),
            previewShort: this.generatePreviewText(aiAnswer),
            markdownData: this.convertMarkdown(aiAnswer),
            prompt_sent: res.prompt || res.data?.prompt
          }
        }
        return msg
      })

      // 更新对话ID
      const conversationId = res.conversation_id || res.data?.conversation_id || this.data.conversationId

      this.setData({
        messages: updatedMessages,
        sending: false,
        isStreaming: false,
        conversationId: conversationId || null,
        conversationMode: conversationId ? 'continue' : 'new',
        lastMessageId: aiMsg.id
      })

      this.scrollToBottom()

    } catch (err) {
      console.error('发送消息失败:', err)

      // 移除AI占位消息或显示错误
      const messages = this.data.messages.filter(m => m.role !== 'ai' || m.id !== Date.now() + 1)

      this.setData({
        messages,
        sending: false,
        isStreaming: false
      })

      util.showToast(err.message || '发送失败，请重试')
    }
  },

  /**
   * 重新生成AI回复
   */
  async regenerateResponse(userMsgIndex) {
    if (this.data.sending) return

    const userMsg = this.data.messages[userMsgIndex]
    if (!userMsg || userMsg.role !== 'user') return

    // 移除该用户消息之后的所有消息
    const messages = this.data.messages.slice(0, userMsgIndex + 1)

    this.setData({
      messages,
      sending: true,
      isStreaming: true,
      lastMessageId: userMsg.id
    })

    try {
      const requestData = {
        question: userMsg.content,
        selected_reports: this.data.selectedReportIds
      }

      if (this.data.conversationId) {
        requestData.conversation_id = this.data.conversationId
      }

      const res = await api.getAdvice(requestData)

      const aiAnswer = res.answer || res.data?.answer || '抱歉，AI医生暂时无法回复。'
      const aiMsg = {
        id: Date.now(),
        role: 'ai',
        content: aiAnswer,
        previewText: this.stripMarkdown(aiAnswer),
        previewShort: this.generatePreviewText(aiAnswer),
        created_at: util.formatDate(new Date(), 'YYYY-MM-DD HH:mm:ss'),
        expanded: false
      }

      this.setData({
        messages: [...messages, aiMsg],
        sending: false,
        isStreaming: false,
        lastMessageId: aiMsg.id
      })

      this.scrollToBottom()

    } catch (err) {
      console.error('重新生成失败:', err)
      this.setData({ sending: false, isStreaming: false })
      util.showToast(err.message || '重新生成失败')
    }
  },

  /**
   * 查看发送给AI的内容
   */
  viewPrompt(e) {
    const index = e.currentTarget.dataset.index
    const msg = this.data.messages[index]

    if (msg && msg.prompt_sent) {
      wx.showModal({
        title: '发送给AI的内容',
        content: msg.prompt_sent,
        showCancel: false
      })
    }
  },

  /**
   * 滚动到底部
   */
  scrollToBottom() {
    setTimeout(() => {
      wx.createSelectorQuery()
        .select('#chat-container')
        .boundingClientRect((rect) => {
          if (rect) {
            wx.pageScrollTo({
              scrollTop: rect.bottom,
              duration: 300
            })
          }
        })
        .exec()
    }, 100)
  },

  /**
   * 复制消息内容
   */
  copyContent(e) {
    const content = e.currentTarget.dataset.content
    wx.setClipboardData({
      data: content,
      success: () => {
        util.showToast('已复制')
      }
    })
  },

  /**
   * 切换AI消息展开/折叠状态
   */
  toggleExpand(e) {
    const index = e.currentTarget.dataset.index
    const msg = this.data.messages[index]

    if (msg) {
      const newExpanded = !msg.expanded

      // 创建全新的消息数组
      const newMessages = this.data.messages.map((m, i) => {
        if (i === index) {
          return { ...m, expanded: newExpanded }
        }
        return m
      })

      this.setData({
        messages: newMessages
      })
    }
  },

  /**
   * 导出对话
   */
  async exportConversation() {
    if (!this.data.conversationId) {
      util.showToast('请先进行对话')
      return
    }

    const items = ['导出为PDF', '导出为Word']
    const index = await util.showActionSheet(items)

    if (index !== 0 && index !== 1) {
      return
    }

    util.showLoading('生成中...')
    try {
      const token = wx.getStorageSync('token')
      const baseUrl = 'https://www.zctestbench.asia'
      const exportUrl = index === 0
        ? `${baseUrl}/api/miniprogram/conversations/${this.data.conversationId}/export/pdf/`
        : `${baseUrl}/api/miniprogram/conversations/${this.data.conversationId}/export/word/`


      // 下载文件
      const downloadRes = await new Promise((resolve, reject) => {
        wx.downloadFile({
          url: exportUrl,
          header: {
            'Authorization': `Token ${token}`
          },
          success: (res) => {
            if (res.statusCode === 200) {
              resolve(res.tempFilePath)
            } else {
              reject(new Error(`下载失败，状态码: ${res.statusCode}`))
            }
          },
          fail: (err) => {
            console.error('[导出] 下载失败:', err)
            reject(new Error('网络下载失败，请检查网络连接'))
          }
        })
      })

      util.hideLoading()

      // 打开文档
      wx.openDocument({
        filePath: downloadRes,
        fileType: index === 0 ? 'pdf' : 'docx',
        showMenu: true,
        success: () => {
          util.showToast('导出成功')
        },
        fail: (err) => {
          console.error('[导出] 打开文档失败:', err)
          util.showToast('打开文档失败')
        }
      })

    } catch (err) {
      console.error('[导出] 导出失败:', err)
      util.showToast(err.message || '导出失败，请稍后重试')
      util.hideLoading()
    }
  },

  /**
   * 返回上一页
   */
  goBack() {
    wx.navigateBack()
  },

  /**
   * 删除对话
   */
  async deleteConversation() {
    if (!this.data.conversationId) {
      util.showToast('无法删除新对话')
      return
    }

    const confirm = await util.showConfirm('确定要删除这个对话吗？删除后无法恢复。')
    if (!confirm) return

    util.showLoading('删除中...')
    try {
      await api.deleteConversation(this.data.conversationId)
      util.showToast('删除成功')

      // 返回上一页
      setTimeout(() => {
        wx.navigateBack()
      }, 1500)
    } catch (err) {
      console.error('删除失败:', err)
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  },

  /**
   * 设置快捷问题
   */
  setQuickQuestion(e) {
    const question = e.currentTarget.dataset.question
    this.setData({ inputText: question })
  },

  /**
   * 显示附件菜单
   */
  showAttachmentMenu() {
    this.setData({ showAttachmentMenu: true })
  },

  /**
   * 隐藏附件菜单
   */
  hideAttachmentMenu() {
    this.setData({ showAttachmentMenu: false })
  },

  /**
   * 阻止事件冒泡
   */
  stopPropagation() {
    // 空方法，用于阻止点击事件冒泡
  },

  /**
   * 输入框聚焦
   */
  onInputFocus() {
    // 可以在这里添加输入框聚焦时的逻辑
  },

  /**
   * 输入框失焦
   */
  onInputBlur() {
    // 可以在这里添加输入框失焦时的逻辑
  },

  /**
   * 输入框内容变化
   */
  onInputChange(e) {
    this.setData({ inputText: e.detail.value })
  }
})
