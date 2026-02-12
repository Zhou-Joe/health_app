/**
 * AI 对话页面
 * 统一使用 Django 网页端同逻辑的同步接口（/api/stream-advice-sync/）
 */

const api = require('../../utils/api.js')
const util = require('../../utils/util.js')
const config = require('../../config.js')

function buildWelcomeMessage() {
  return '您好，我是 AI 健康助手。\n\n您可以直接提问，也可以附加体检报告和药单信息，我会结合历史对话给出连续建议。'
}

Page({
  data: {
    conversationId: null,
    conversationMode: 'new', // new | continue

    messages: [],
    lastMessageId: null,
    scrollToView: '',

    inputText: '',
    sending: false,
    userAvatarUrl: '',
    userAvatarLoadFailed: false,
    userDisplayInitial: '我',

    reports: [],
    selectedReportIds: [],
    reportsNoSelection: false,
    reportsLoading: false,
    reportsLoaded: false,
    reportsError: null,

    medications: [],
    selectedMedicationIds: [],
    medicationsNoSelection: false,
    medicationsLoading: false,
    medicationsLoaded: false,
    medicationsError: null,

    activeSelector: '',
    activeSelectorTitle: '',
    activeSelectorNoSelection: false,
    activeSelectorNoSelectionTitle: '',
    activeSelectorNoSelectionDesc: '',
    activeSelectorItems: [],
    activeSelectorLoading: false,
    activeSelectorError: '',
    bindingSummary: '未绑定资料',

    showAttachmentMenu: false,
    isGenerating: false
  },

  onLoad(options) {
    const isNewFromAdvice = options.new === 'true' && options.data === '1'
    const conversationId = options.id ? parseInt(options.id, 10) : null

    this.restoreLastSelection()
    this.updateBindingSummary()
    this.loadUserAvatar()

    // 预加载可选数据，减少首次打开弹窗等待
    this.loadReports()
    this.loadMedications()

    if (isNewFromAdvice) {
      this.handlePendingAdviceRequest()
      return
    }

    if (conversationId) {
      this.setData({
        conversationId,
        conversationMode: 'continue'
      })
      this.loadConversation(conversationId)
      return
    }

    const welcomeMessage = buildWelcomeMessage()
    this.setData({
      conversationMode: 'new',
      messages: [{
        id: 0,
        role: 'ai',
        content: welcomeMessage,
        previewText: this.stripMarkdown(welcomeMessage),
        previewShort: this.generatePreviewText(welcomeMessage),
        created_at: util.formatDate(new Date(), 'YYYY-MM-DD HH:mm:ss'),
        expanded: false
      }],
      lastMessageId: 0
    })
    this.scrollToBottom(0)
  },

  onUnload() {
    if (this._clearScrollToViewTimer) {
      clearTimeout(this._clearScrollToViewTimer)
      this._clearScrollToViewTimer = null
    }
  },

  onShow() {
    this.loadUserAvatar()
  },

  normalizeAvatarUrl(url) {
    if (!url) return ''
    const trimmed = String(url).trim()
    if (!trimmed) return ''
    if (/^https?:\/\//i.test(trimmed)) {
      return trimmed
    }
    if (trimmed.startsWith('/')) {
      return `${util.getBaseURL()}${trimmed}`
    }
    return trimmed
  },

  loadUserAvatar() {
    try {
      const app = getApp()
      const cachedUserInfo = wx.getStorageSync(config.storageKeys.USER_INFO) || app.globalData.userInfo || {}
      const localWechatAvatar = wx.getStorageSync('wechat_avatar') || ''

      const avatarUrl = this.normalizeAvatarUrl(cachedUserInfo.avatar_url || localWechatAvatar || '')
      const displayName = cachedUserInfo.first_name || cachedUserInfo.nickname || cachedUserInfo.username || ''
      const userDisplayInitial = displayName ? String(displayName).trim().charAt(0) : '我'

      this.setData({
        userAvatarUrl: avatarUrl,
        userAvatarLoadFailed: false,
        userDisplayInitial: userDisplayInitial || '我'
      })
    } catch (err) {
      console.error('[conversation] loadUserAvatar failed:', err)
      this.setData({
        userAvatarUrl: '',
        userAvatarLoadFailed: false,
        userDisplayInitial: '我'
      })
    }
  },

  onUserAvatarError(e) {
    console.error('[conversation] user avatar load failed:', e)
    this.setData({ userAvatarLoadFailed: true })
  },

  async loadConversation(conversationId) {
    util.showLoading('加载中...')

    const timeout = setTimeout(() => {
      util.hideLoading()
      util.showToast('加载超时，请重试')
    }, 15000)

    try {
      const res = await api.getConversationMessages(conversationId)
      clearTimeout(timeout)

      const rawMessages = res.data?.messages || []
      const messages = []

      rawMessages.forEach((msg) => {
        const time = util.formatDate(new Date(msg.created_at), 'YYYY-MM-DD HH:mm:ss')

        messages.push({
          id: msg.id,
          role: 'user',
          content: msg.question,
          created_at: time
        })

        const aiContent = msg.answer || ''
        const aiMsg = {
          id: msg.id + 100000,
          role: 'ai',
          content: aiContent,
          previewText: this.stripMarkdown(aiContent),
          previewShort: this.generatePreviewText(aiContent),
          prompt_sent: msg.prompt_sent,
          created_at: time,
          expanded: false
        }

        if (aiContent.length < 5000) {
          aiMsg.markdownData = this.convertMarkdown(aiContent)
        }

        messages.push(aiMsg)
      })

      const lastSelectedReports = res.data?.last_selected_reports || []
      const lastSelectedMedications = res.data?.last_selected_medications || []

      this.setData({
        messages,
        selectedReportIds: lastSelectedReports,
        selectedMedicationIds: lastSelectedMedications,
        reportsNoSelection: false,
        medicationsNoSelection: false,
        lastMessageId: messages.length ? messages[messages.length - 1].id : null
      }, () => {
        this.updateBindingSummary()
        this.restoreReportSelection()
        this.restoreMedicationSelection()
      })

      // 长文本延迟 markdown 转换
      setTimeout(() => {
        const updated = this.data.messages.map((msg) => {
          if (msg.role === 'ai' && !msg.markdownData && msg.content) {
            return {
              ...msg,
              markdownData: this.convertMarkdown(msg.content)
            }
          }
          return msg
        })
        this.setData({ messages: updated })
      }, 100)

      this.scrollToBottom()
    } catch (err) {
      clearTimeout(timeout)
      console.error('[conversation] loadConversation failed:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      util.hideLoading()
    }
  },

  convertMarkdown(content) {
    if (!content) {
      return null
    }

    try {
      let text = content
      const maxLength = 10000
      if (text.length > maxLength) {
        text = text.substring(0, maxLength) + '\n\n...(内容过长，已截断)'
      }

      let html = text

      html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        return `<pre><code>${this.escapeHtml(code.trim())}</code></pre>`
      })

      html = this.escapeHtml(html)

      html = html.replace(/^######\s+(.*)$/gm, '<h6>$1</h6>')
      html = html.replace(/^#####\s+(.*)$/gm, '<h5>$1</h5>')
      html = html.replace(/^####\s+(.*)$/gm, '<h4>$1</h4>')
      html = html.replace(/^###\s+(.*)$/gm, '<h3>$1</h3>')
      html = html.replace(/^##\s+(.*)$/gm, '<h2>$1</h2>')
      html = html.replace(/^#\s+(.*)$/gm, '<h1>$1</h1>')

      html = html.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>')
      html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
      html = html.replace(/`([^`]+)`/g, '<code>$1</code>')

      html = html.replace(/\n\n+/g, '</p><p>')
      html = html.replace(/\n/g, '<br>')
      html = `<p>${html}</p>`

      return html
    } catch (err) {
      console.error('[conversation] convertMarkdown failed:', err)
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
    return text.replace(/[&<>"']/g, (m) => map[m])
  },

  stripMarkdown(content) {
    if (!content) {
      return ''
    }

    return content
      .replace(/```[\s\S]*?```/g, (match) => {
        const code = match.replace(/```\w*\n?/g, '').replace(/```/g, '')
        return code.trim() || '代码'
      })
      .replace(/`([^`]+)`/g, '$1')
      .replace(/\*\*/g, '')
      .replace(/\*/g, '')
      .replace(/^#{1,6}\s+/gm, '')
      .replace(/^\s*[-*+]\s+/gm, '')
      .replace(/^>\s+/gm, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/\n+/g, ' ')
      .replace(/\s{2,}/g, ' ')
      .trim()
  },

  generatePreviewText(content) {
    const text = this.stripMarkdown(content)
    return text.length > 100 ? text.substring(0, 100) : text
  },

  updateBindingSummary() {
    const reportCount = this.data.selectedReportIds.length
    const medicationCount = this.data.selectedMedicationIds.length
    const bindingSummary = (reportCount === 0 && medicationCount === 0)
      ? '未绑定资料'
      : `已绑定 报告${reportCount} · 药单${medicationCount}`
    this.setData({ bindingSummary })
  },

  syncActiveSelectorState() {
    const type = this.data.activeSelector
    if (!type) {
      return
    }

    const isReport = type === 'report'
    const source = isReport ? this.data.reports : this.data.medications
    const activeSelectorItems = source.map((item) => ({
      id: item.id,
      selected: !!item.selected,
      icon: isReport ? '检' : '药',
      title: isReport ? item.hospital : item.medicine_name,
      desc: isReport
        ? `${item.checkup_date} · ${item.indicators_count} 项指标`
        : (item.dosage || '用药信息')
    }))

    this.setData({
      activeSelectorTitle: isReport ? '选择体检报告' : '选择药单',
      activeSelectorNoSelection: isReport
        ? (this.data.selectedReportIds.length === 0 && this.data.reportsNoSelection)
        : (this.data.selectedMedicationIds.length === 0 && this.data.medicationsNoSelection),
      activeSelectorNoSelectionTitle: isReport ? '不使用报告' : '不使用药单',
      activeSelectorNoSelectionDesc: isReport ? '仅基于问题咨询' : '仅咨询健康问题',
      activeSelectorItems,
      activeSelectorLoading: isReport ? this.data.reportsLoading : this.data.medicationsLoading,
      activeSelectorError: isReport ? (this.data.reportsError || '') : (this.data.medicationsError || '')
    })
  },

  async loadReports() {
    try {
      this.setData({ reportsLoading: true, reportsError: null }, () => {
        this.syncActiveSelectorState()
      })
      const res = await api.getCheckups({ page_size: 100 })
      const checkups = res.checkups || res.data || res.results || []

      const reports = checkups.map((r) => {
        let date = ''
        try {
          date = util.formatDate(r.checkup_date, 'YYYY-MM-DD')
        } catch {
          date = r.checkup_date || ''
        }

        return {
          id: r.id,
          hospital: r.hospital || '未知机构',
          checkup_date: date,
          indicators_count: r.indicator_count || r.indicators_count || 0,
          selected: false
        }
      })

      this.setData({
        reports,
        reportsLoading: false,
        reportsLoaded: true
      }, () => {
        this.restoreReportSelection()
      })
    } catch (err) {
      console.error('[conversation] loadReports failed:', err)
      this.setData({
        reportsLoading: false,
        reportsError: err.message || '加载报告失败',
        reportsLoaded: true
      }, () => {
        this.syncActiveSelectorState()
      })
    }
  },

  async loadMedications() {
    try {
      this.setData({ medicationsLoading: true, medicationsError: null }, () => {
        this.syncActiveSelectorState()
      })
      const res = await api.getMedications()
      const medications = (res.medications || []).map((m) => ({
        ...m,
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
      }, () => {
        this.restoreMedicationSelection()
      })
    } catch (err) {
      console.error('[conversation] loadMedications failed:', err)
      this.setData({
        medicationsLoading: false,
        medicationsError: err.message || '加载药单失败',
        medicationsLoaded: true
      }, () => {
        this.syncActiveSelectorState()
      })
    }
  },

  restoreLastSelection() {
    try {
      const lastSelection = wx.getStorageSync('lastConsultationSelection')
      if (!lastSelection) {
        return
      }

      this.setData({
        selectedReportIds: lastSelection.selectedReportIds || [],
        selectedMedicationIds: lastSelection.selectedMedicationIds || [],
        reportsNoSelection: !!lastSelection.reportsNoSelection,
        medicationsNoSelection: !!lastSelection.medicationsNoSelection
      }, () => {
        this.updateBindingSummary()
        this.syncActiveSelectorState()
      })
    } catch (err) {
      console.error('[conversation] restoreLastSelection failed:', err)
    }
  },

  restoreReportSelection() {
    const selectedSet = new Set(this.data.selectedReportIds || [])
    const reports = this.data.reports.map((r) => ({
      ...r,
      selected: selectedSet.has(r.id)
    }))
    this.setData({ reports }, () => {
      this.syncActiveSelectorState()
    })
  },

  restoreMedicationSelection() {
    const selectedSet = new Set(this.data.selectedMedicationIds || [])
    const medications = this.data.medications.map((m) => ({
      ...m,
      selected: selectedSet.has(m.id)
    }))
    this.setData({ medications }, () => {
      this.syncActiveSelectorState()
    })
  },

  saveCurrentSelection() {
    try {
      wx.setStorageSync('lastConsultationSelection', {
        selectedReportIds: this.data.selectedReportIds,
        selectedMedicationIds: this.data.selectedMedicationIds,
        reportsNoSelection: this.data.reportsNoSelection,
        medicationsNoSelection: this.data.medicationsNoSelection,
        timestamp: Date.now()
      })
      this.updateBindingSummary()
      this.syncActiveSelectorState()
    } catch (err) {
      console.error('[conversation] saveCurrentSelection failed:', err)
    }
  },

  openSelector(type) {
    if (type !== 'report' && type !== 'medication') {
      return
    }

    this.setData({
      showAttachmentMenu: false,
      activeSelector: type
    }, () => {
      this.syncActiveSelectorState()
    })

    if (type === 'report' && !this.data.reportsLoaded) {
      this.loadReports()
    }
    if (type === 'medication' && !this.data.medicationsLoaded) {
      this.loadMedications()
    }
  },

  openReportSelector() {
    this.openSelector('report')
  },

  openMedicationSelector() {
    this.openSelector('medication')
  },

  closeSelector() {
    this.setData({ activeSelector: '' })
  },

  retryActiveSelector() {
    if (this.data.activeSelector === 'report') {
      this.loadReports()
      return
    }
    if (this.data.activeSelector === 'medication') {
      this.loadMedications()
    }
  },

  selectNoCurrent() {
    if (this.data.activeSelector === 'report') {
      const reports = this.data.reports.map((r) => ({ ...r, selected: false }))
      this.setData({
        reports,
        selectedReportIds: [],
        reportsNoSelection: true
      }, () => {
        this.saveCurrentSelection()
      })
      util.showToast('已设置为不使用报告')
      return
    }

    if (this.data.activeSelector === 'medication') {
      const medications = this.data.medications.map((m) => ({ ...m, selected: false }))
      this.setData({
        medications,
        selectedMedicationIds: [],
        medicationsNoSelection: true
      }, () => {
        this.saveCurrentSelection()
      })
      util.showToast('已设置为不使用药单')
    }
  },

  toggleSelectorItem(e) {
    const rawId = e.currentTarget.dataset.id
    const isSameId = (id) => String(id) === String(rawId)

    if (this.data.activeSelector === 'report') {
      const reports = this.data.reports.map((r) => {
        if (isSameId(r.id)) {
          return { ...r, selected: !r.selected }
        }
        return r
      })
      const selectedReportIds = reports.filter((r) => r.selected).map((r) => r.id)
      this.setData({
        reports,
        selectedReportIds,
        reportsNoSelection: false
      }, () => {
        this.saveCurrentSelection()
      })
      return
    }

    if (this.data.activeSelector === 'medication') {
      const medications = this.data.medications.map((m) => {
        if (isSameId(m.id)) {
          return { ...m, selected: !m.selected }
        }
        return m
      })
      const selectedMedicationIds = medications.filter((m) => m.selected).map((m) => m.id)
      this.setData({
        medications,
        selectedMedicationIds,
        medicationsNoSelection: false
      }, () => {
        this.saveCurrentSelection()
      })
    }
  },

  toggleSelectAllCurrent() {
    if (this.data.activeSelector === 'report') {
      if (!this.data.reports.length) {
        return
      }
      const allSelected = this.data.selectedReportIds.length === this.data.reports.length
      const reports = this.data.reports.map((r) => ({
        ...r,
        selected: !allSelected
      }))
      this.setData({
        reports,
        selectedReportIds: allSelected ? [] : reports.map((r) => r.id),
        reportsNoSelection: false
      }, () => {
        this.saveCurrentSelection()
      })
      return
    }

    if (this.data.activeSelector === 'medication') {
      if (!this.data.medications.length) {
        return
      }
      const allSelected = this.data.selectedMedicationIds.length === this.data.medications.length
      const medications = this.data.medications.map((m) => ({
        ...m,
        selected: !allSelected
      }))
      this.setData({
        medications,
        selectedMedicationIds: allSelected ? [] : medications.map((m) => m.id),
        medicationsNoSelection: false
      }, () => {
        this.saveCurrentSelection()
      })
    }
  },

  onInputChange(e) {
    this.setData({ inputText: e.detail.value })
  },

  normalizeAdviceRequest(rawData = {}) {
    const selectedReportIds = Array.isArray(rawData.selected_report_ids)
      ? rawData.selected_report_ids
      : (Array.isArray(rawData.selected_reports) ? rawData.selected_reports : [])

    const selectedMedicationIds = Array.isArray(rawData.selected_medication_ids)
      ? rawData.selected_medication_ids
      : (Array.isArray(rawData.selected_medications) ? rawData.selected_medications : [])

    const hasConversation = !!rawData.conversation_id

    const requestData = {
      question: (rawData.question || '').trim(),
      conversation_mode: rawData.conversation_mode || (hasConversation ? 'continue_conversation' : 'new_conversation'),
      report_mode: rawData.report_mode || (selectedReportIds.length > 0 ? 'select' : 'no_reports'),
      medication_mode: rawData.medication_mode || (selectedMedicationIds.length > 0 ? 'select' : 'no_medications')
    }

    if (hasConversation) {
      requestData.conversation_id = rawData.conversation_id
    }

    if (selectedReportIds.length > 0) {
      requestData.selected_report_ids = selectedReportIds
    }

    if (selectedMedicationIds.length > 0) {
      requestData.selected_medication_ids = selectedMedicationIds
    }

    return requestData
  },

  buildAdviceRequest(question) {
    const isContinue = this.data.conversationMode === 'continue' && !!this.data.conversationId

    const requestData = {
      question,
      conversation_mode: isContinue ? 'continue_conversation' : 'new_conversation',
      report_mode: 'no_reports',
      medication_mode: 'no_medications'
    }

    if (isContinue) {
      requestData.conversation_id = this.data.conversationId
    }

    if (this.data.selectedReportIds.length > 0) {
      requestData.selected_report_ids = this.data.selectedReportIds
      requestData.report_mode = 'select'
    } else if (this.data.reportsNoSelection) {
      requestData.report_mode = 'no_reports'
    } else {
      // 继续对话未显式取消时，允许后端复用上一轮选择
      requestData.report_mode = isContinue ? 'select' : 'no_reports'
    }

    if (this.data.selectedMedicationIds.length > 0) {
      requestData.selected_medication_ids = this.data.selectedMedicationIds
      requestData.medication_mode = 'select'
    } else if (this.data.medicationsNoSelection) {
      requestData.medication_mode = 'no_medications'
    } else {
      // 继续对话未显式取消时，允许后端复用上一轮选择
      requestData.medication_mode = isContinue ? 'select' : 'no_medications'
    }

    return requestData
  },

  async callAiAdvice(requestData) {
    return api.streamAdviceSync(requestData)
  },

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

    if (this.data.sending) {
      return
    }

    const nowText = util.formatDate(new Date(), 'YYYY-MM-DD HH:mm:ss')

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: inputText,
      created_at: nowText
    }

    const aiPlaceholderId = Date.now() + 1
    const aiPlaceholder = {
      id: aiPlaceholderId,
      role: 'ai',
      content: '正在分析，请稍候...',
      previewText: '正在分析，请稍候...',
      previewShort: '正在分析，请稍候...',
      created_at: nowText,
      expanded: false,
      isThinking: true
    }

    this.setData({
      messages: [...this.data.messages, userMsg, aiPlaceholder],
      inputText: '',
      sending: true,
      isGenerating: true,
      lastMessageId: aiPlaceholderId
    })

    this.scrollToBottom(aiPlaceholderId)

    try {
      const requestData = this.buildAdviceRequest(inputText)
      const res = await this.callAiAdvice(requestData)

      const aiAnswer = res.answer || res.data?.answer || '抱歉，AI 医生暂时无法回复，请稍后重试。'
      const conversationId = res.conversation_id || res.data?.conversation_id || this.data.conversationId

      const updatedMessages = this.data.messages.map((msg) => {
        if (msg.id !== aiPlaceholderId) {
          return msg
        }
        return {
          ...msg,
          content: aiAnswer,
          previewText: this.stripMarkdown(aiAnswer),
          previewShort: this.generatePreviewText(aiAnswer),
          markdownData: this.convertMarkdown(aiAnswer),
          prompt_sent: res.prompt || res.data?.prompt,
          isThinking: false
        }
      })

      this.setData({
        messages: updatedMessages,
        sending: false,
        isGenerating: false,
        conversationId: conversationId || null,
        conversationMode: conversationId ? 'continue' : 'new',
        lastMessageId: aiPlaceholderId
      })

      this.saveCurrentSelection()
      this.scrollToBottom(aiPlaceholderId)
    } catch (err) {
      console.error('[conversation] sendMessage failed:', err)

      const keptMessages = this.data.messages.filter((msg) => msg.id !== aiPlaceholderId)
      this.setData({
        messages: keptMessages,
        sending: false,
        isGenerating: false
      })
      util.showToast(err.message || '发送失败，请重试')
    }
  },

  toggleExpand(e) {
    const index = e.currentTarget.dataset.index
    const target = this.data.messages[index]
    if (!target || target.role !== 'ai') {
      return
    }

    const expanded = !target.expanded
    const messages = this.data.messages.map((m, i) => {
      if (i !== index) {
        return m
      }
      return { ...m, expanded }
    })

    this.setData({ messages })
  },

  scrollToBottom(messageId) {
    const id = messageId !== undefined && messageId !== null
      ? messageId
      : this.data.lastMessageId

    if (id === undefined || id === null) {
      return
    }

    // 触发 scroll-into-view 需要值发生变化；随后清空避免锁定手势滚动
    if (this._clearScrollToViewTimer) {
      clearTimeout(this._clearScrollToViewTimer)
      this._clearScrollToViewTimer = null
    }
    this.setData({ scrollToView: '' })
    setTimeout(() => {
      const target = `msg-${id}`
      this.setData({ scrollToView: target })
      this._clearScrollToViewTimer = setTimeout(() => {
        if (this.data.scrollToView === target) {
          this.setData({ scrollToView: '' })
        }
      }, 320)
    }, 20)
  },

  goBack() {
    if (getCurrentPages().length > 1) {
      wx.navigateBack()
    } else {
      wx.switchTab({ url: '/pages/ai-advice/ai-advice' })
    }
  },

  showAttachmentMenu() {
    this.setData({ showAttachmentMenu: true })
  },

  hideAttachmentMenu() {
    this.setData({ showAttachmentMenu: false })
  },

  stopPropagation() {
    // no-op
  },

  async handlePendingAdviceRequest() {
    try {
      const raw = wx.getStorageSync('pendingAdviceRequest')
      wx.removeStorageSync('pendingAdviceRequest')

      if (!raw || !raw.question) {
        util.showToast('请求数据丢失，请重新提交')
        const welcomeMessage = buildWelcomeMessage()
        this.setData({
          conversationMode: 'new',
          messages: [{
            id: 0,
            role: 'ai',
            content: welcomeMessage,
            previewText: this.stripMarkdown(welcomeMessage),
            previewShort: this.generatePreviewText(welcomeMessage),
            created_at: util.formatDate(new Date(), 'YYYY-MM-DD HH:mm:ss'),
            expanded: false
          }],
          lastMessageId: 0
        })
        this.scrollToBottom(0)
        return
      }

      const requestData = this.normalizeAdviceRequest(raw)
      const nowText = util.formatDate(new Date(), 'YYYY-MM-DD HH:mm:ss')

      const userMsg = {
        id: Date.now(),
        role: 'user',
        content: requestData.question,
        created_at: nowText
      }

      const aiPlaceholderId = Date.now() + 1
      const aiPlaceholder = {
        id: aiPlaceholderId,
        role: 'ai',
        content: '正在分析，请稍候...',
        previewText: '正在分析，请稍候...',
        previewShort: '正在分析，请稍候...',
        created_at: nowText,
        expanded: false,
        isThinking: true
      }

      this.setData({
        messages: [userMsg, aiPlaceholder],
        sending: true,
        isGenerating: true,
        lastMessageId: aiPlaceholderId,
        conversationMode: requestData.conversation_mode === 'continue_conversation' ? 'continue' : 'new',
        selectedReportIds: requestData.selected_report_ids || [],
        selectedMedicationIds: requestData.selected_medication_ids || [],
        reportsNoSelection: requestData.report_mode === 'no_reports',
        medicationsNoSelection: requestData.medication_mode === 'no_medications'
      }, () => {
        this.updateBindingSummary()
        this.restoreReportSelection()
        this.restoreMedicationSelection()
      })
      this.scrollToBottom(aiPlaceholderId)

      const res = await this.callAiAdvice(requestData)
      const aiAnswer = res.answer || res.data?.answer || '抱歉，AI 医生暂时无法回复，请稍后重试。'
      const conversationId = res.conversation_id || res.data?.conversation_id || requestData.conversation_id

      const updatedMessages = this.data.messages.map((msg) => {
        if (msg.id !== aiPlaceholderId) {
          return msg
        }
        return {
          ...msg,
          content: aiAnswer,
          previewText: this.stripMarkdown(aiAnswer),
          previewShort: this.generatePreviewText(aiAnswer),
          markdownData: this.convertMarkdown(aiAnswer),
          prompt_sent: res.prompt || res.data?.prompt,
          isThinking: false
        }
      })

      this.setData({
        messages: updatedMessages,
        sending: false,
        isGenerating: false,
        conversationId: conversationId || null,
        conversationMode: conversationId ? 'continue' : this.data.conversationMode,
        lastMessageId: aiPlaceholderId
      })

      this.saveCurrentSelection()
      this.scrollToBottom(aiPlaceholderId)
    } catch (err) {
      console.error('[conversation] handlePendingAdviceRequest failed:', err)

      const messages = this.data.messages.filter((m) => !m.isThinking)
      this.setData({
        messages,
        sending: false,
        isGenerating: false
      })
      util.showToast(err.message || '请求失败，请重试')
    }
  }
})
