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
    adviceId: null
  },

  onLoad(options) {
    const conversationId = options.id
    const isGenerating = options.generating === 'true'
    const adviceId = options.adviceId ? parseInt(options.adviceId) : null

    // 恢复上次的选择
    this.restoreLastSelection()

    if (conversationId) {
      // 继续对话
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
    const maxPolls = 120 // 最多轮询120次（120次 * 0.5秒 = 60秒）

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
    const maxPolls = 40 // 最多轮询40次（40秒 * 2 = 80秒）

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
    util.showLoading('加载中...')
    try {
      const res = await api.getConversationMessages(conversationId)
      const messages = []

      // 将消息转换为聊天格式
      // 后端返回结构: { success: true, data: { messages: [...] } }
      const messageList = res.data?.messages || []

      messageList.forEach(msg => {
        // 格式化时间，去掉毫秒
        const formattedTime = util.formatDate(new Date(msg.created_at), 'YYYY-MM-DD HH:mm:ss')

        messages.push({
          id: msg.id,
          role: 'user',
          content: msg.question,
          created_at: formattedTime
        })
        // AI消息转换为Markdown
        const aiContent = msg.answer || ''
        messages.push({
          id: msg.id + 1000,
          role: 'ai',
          content: aiContent,
          previewText: this.stripMarkdown(aiContent),
          previewShort: this.generatePreviewText(aiContent),
          markdownData: this.convertMarkdown(aiContent),
          created_at: formattedTime,
          prompt_sent: msg.prompt_sent,
          expanded: false
        })
      })

      // 获取对话中最后一条消息使用的报告ID
      const lastSelectedReports = res.data?.last_selected_reports || []

      this.setData({
        messages,
        selectedReportIds: lastSelectedReports,
        lastMessageId: messages.length > 0 ? messages[messages.length - 1].id : null
      })

      console.log('[对话] 已加载上一轮对话的报告设置:', lastSelectedReports)
    } catch (err) {
      console.error('加载对话失败:', err)
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
      let html = content
        // 转义HTML特殊字符
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        // 代码块（必须在行内代码之前处理）
        .replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
          return `<pre style="background:#282C34;color:#ABB2BF;padding:12px;border-radius:8px;margin:8px 0;overflow-x:auto;"><code style="font-family:monospace;font-size:14px;line-height:1.6;">${code.trim()}</code></pre>`
        })
        // 行内代码
        .replace(/`([^`]+)`/g, '<code style="background:#F5F5F5;color:#E83E8C;padding:2px 6px;border-radius:4px;font-family:monospace;font-size:14px;">$1</code>')
        // 粗体
        .replace(/\*\*([^*]+)\*\*/g, '<strong style="font-weight:bold;color:#333;">$1</strong>')
        // 斜体
        .replace(/\*([^*]+)\*/g, '<em style="font-style:italic;color:#555;">$1</em>')
        // 标题
        .replace(/^### (.*$)/gim, '<h3 style="font-size:16px;font-weight:bold;margin:12px 0 8px;color:#333;">$1</h3>')
        .replace(/^## (.*$)/gim, '<h2 style="font-size:18px;font-weight:bold;margin:16px 0 10px;color:#333;">$1</h2>')
        .replace(/^# (.*$)/gim, '<h1 style="font-size:20px;font-weight:bold;margin:20px 0 12px;color:#333;">$1</h1>')
        // 无序列表
        .replace(/^\s*-\s+(.*$)/gim, '<li style="margin:4px 0;padding-left:16px;">$1</li>')
        .replace(/(<li[^>]*>.*<\/li>)/s, '<ul style="margin:8px 0;padding-left:16px;">$1</ul>')
        // 引用
        .replace(/^>\s+(.*$)/gim, '<blockquote style="border-left:4px solid #667eea;padding-left:12px;margin:8px 0;color:#666;background:#F9F9F9;padding:8px 12px;">$1</blockquote>')
        // 换行
        .replace(/\n\n/g, '<br/><br/>')
        .replace(/\n/g, '<br/>')

      return html
    } catch (e) {
      console.error('Markdown转换失败:', e)
      return null
    }
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
      console.log('[对话] 开始加载报告列表...')

      const res = await api.getCheckups({ page_size: 100 })
      console.log('[对话] API响应:', res)

      // 后端返回格式: { success: true, checkups: [...], count: ... }
      const checkupsData = res.checkups || res.data || res.results || []
      console.log('[对话] 解析后的报告数据:', checkupsData)

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

      console.log(`[对话] 成功加载 ${reports.length} 份报告:`, reports)

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

      console.log(`[对话] 成功加载 ${medications.length} 份药单`)
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
        console.log('[对话] 恢复上次选择:', lastSelection)
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
      console.log('[对话] 保存选择:', selection)
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
        console.log('[对话] 继续对话，使用报告设置:', this.data.selectedReportIds)

        // 如果有使用报告，给用户提示
        if (this.data.selectedReportIds.length > 0) {
          console.log(`[对话] 本次对话将引用 ${this.data.selectedReportIds.length} 份报告`)
        }
      }

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
      console.log('切换展开状态:', {
        index,
        oldExpanded: msg.expanded,
        newExpanded,
        contentLength: msg.content ? msg.content.length : 0,
        contentPreview: msg.content ? msg.content.substring(0, 50) : 'NO CONTENT',
        contentSub100: msg.content ? msg.content.substring(0, 100) : 'NO CONTENT'
      })

      // 创建全新的消息数组
      const newMessages = this.data.messages.map((m, i) => {
        if (i === index) {
          return { ...m, expanded: newExpanded }
        }
        return m
      })

      this.setData({
        messages: newMessages
      }, () => {
        // setData 回调中验证数据
        console.log('setData后的数据:', {
          expanded: this.data.messages[index].expanded,
          content: this.data.messages[index].content ? this.data.messages[index].content.substring(0, 50) : 'EMPTY'
        })
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
      const baseUrl = 'https://www.zctestbench.asia/health'
      const exportUrl = index === 0
        ? `${baseUrl}/api/miniprogram/conversations/${this.data.conversationId}/export/pdf/`
        : `${baseUrl}/api/miniprogram/conversations/${this.data.conversationId}/export/word/`

      console.log('[导出] 开始下载:', exportUrl)

      // 下载文件
      const downloadRes = await new Promise((resolve, reject) => {
        wx.downloadFile({
          url: exportUrl,
          header: {
            'Authorization': `Token ${token}`
          },
          success: (res) => {
            console.log('[导出] 下载响应状态码:', res.statusCode)
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
          console.log('[导出] 文档打开成功')
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
  }
})
