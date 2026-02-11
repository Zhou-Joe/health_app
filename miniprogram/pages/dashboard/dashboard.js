/**
 * 仪表板页面
 * 显示用户健康数据概览、异常指标提醒、健康趋势等
 */

const app = getApp()
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    userInfo: {},
    // 日期显示
    currentDay: '',
    currentMonth: '',
    // 健康评分
    healthScore: 85,
    healthTrend: 'up',
    scoreComment: '健康状况良好',
    // 统计数据
    stats: {
      checkupCount: 0,
      indicatorCount: 0,
      conversationCount: 0,
      abnormalCount: 0,
      eventCount: 0
    },
    // 异常指标
    abnormalIndicators: [],
    // 事件时间轴（首页）
    recentEvents: [],
    showAggregateTip: true,
    autoAggregating: false,
    // 健康趋势数据
    trendData: [],
    // 当前显示的趋势类型
    currentTrendType: '',
    currentTrendTypeName: '',
    // 趋势类型列表（动态加载）
    trendTypes: [],
    // 加载状态
    loading: false,
    refreshing: false
  },

  onLoad() {
    this.initDateDisplay()
    this.calculateHealthScore()
    this.initAggregateTip()
    this.checkLogin()
    this.loadData()
  },

  onShow() {
    // 从其他页面返回时刷新数据
    this.initDateDisplay()
    this.calculateHealthScore()
    this.loadData()
  },

  /**
   * 初始化日期显示
   */
  initDateDisplay() {
    const now = new Date()
    const day = now.getDate()
    const months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    const month = months[now.getMonth()]

    this.setData({
      currentDay: day,
      currentMonth: month
    })
  },

  /**
   * 初始化自动整合提示显示状态
   */
  initAggregateTip() {
    const seen = wx.getStorageSync('eventAutoAggregateTipSeen')
    this.setData({
      showAggregateTip: !seen
    })
  },

  /**
   * 计算健康评分
   */
  calculateHealthScore() {
    // 基于异常指标数量计算评分
    const abnormalCount = this.data.abnormalIndicators.length || 0
    const baseScore = 95
    const score = Math.max(60, baseScore - abnormalCount * 5)

    let trend = 'stable'
    let comment = '健康状况良好'

    if (score >= 90) {
      comment = '非常健康，继续保持'
      trend = 'up'
    } else if (score >= 80) {
      comment = '健康状况良好'
      trend = 'stable'
    } else if (score >= 70) {
      comment = '需要关注一些指标'
      trend = 'stable'
    } else {
      comment = '建议咨询医生'
      trend = 'down'
    }

    this.setData({
      healthScore: score,
      healthTrend: trend,
      scoreComment: comment
    })
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    this.setData({ refreshing: true })
    this.loadData().finally(() => {
      wx.stopPullDownRefresh()
      this.setData({ refreshing: false })
    })
  },

  /**
   * 检查登录状态
   */
  checkLogin() {
    const config = require('../../config.js')
    const token = wx.getStorageSync(config.storageKeys.TOKEN)

    // 优先检查本地存储的token，而不是依赖全局状态
    if (!token && !app.globalData.isLogin) {
      wx.reLaunch({ url: '/pages/login/login' })
    }
  },

  /**
   * 加载所有数据
   */
  async loadData() {
    if (this.data.loading) return

    this.setData({ loading: true })

    try {
      this.setData({ userInfo: app.globalData.userInfo })

      // 并发请求多个接口
      const [checkupsRes, abnormalRes, conversationsRes, indicatorTypesRes, eventsRes] = await Promise.all([
        api.getCheckups({ page: 1, page_size: 5 }),
        this.loadAbnormalIndicators(),
        api.getConversations(),
        this.loadIndicatorTypes(),
        this.loadEventsTimeline()
      ])

      const checkups = checkupsRes.data || checkupsRes.results || []
      let indicatorCount = 0

      checkups.forEach(c => {
        indicatorCount += c.indicators_count || 0
      })

      // 设置趋势类型和默认选中第一个
      const trendTypes = indicatorTypesRes.data || []
      const currentTrendType = trendTypes.length > 0 ? trendTypes[0].type : ''
      const currentTypeName = trendTypes.length > 0 ? trendTypes[0].name : ''

      this.setData({
        stats: {
          checkupCount: checkupsRes.total || checkupsRes.count || 0,
          indicatorCount: indicatorCount,
          conversationCount: conversationsRes.total || conversationsRes.count || 0,
          abnormalCount: this.data.abnormalIndicators.length,
          eventCount: eventsRes.count || 0
        },
        trendTypes: trendTypes,
        currentTrendType: currentTrendType,
        currentTrendTypeName: currentTypeName
      })

      // 计算健康评分
      this.calculateHealthScore()

      // 加载第一个趋势类型的数据
      if (currentTrendType) {
        await this.loadTrendData()
      }
    } catch (err) {
      console.error('加载数据失败:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      this.setData({ loading: false })
    }
  },

  /**
   * 加载异常指标
   */
  async loadAbnormalIndicators() {
    try {
      const res = await api.getIndicators({
        status: 'abnormal',
        page_size: 20
      })

      let indicators = res.data || res.results || []

      // 客户端二次验证，确保只显示异常指标
      indicators = indicators.filter(item => {
        // 必须明确标记为 abnormal
        return item.status === 'abnormal'
      }).slice(0, 5) // 只取前5个

      this.setData({
        abnormalIndicators: indicators.map(item => ({
          ...item,
          checkup_id: item.checkup?.id || item.checkup_id,
          checkup_date: util.formatDate(item.checkup_date, 'MM-DD')
        }))
      })
    } catch (err) {
      console.error('加载异常指标失败:', err)
      this.setData({ abnormalIndicators: [] })
    }
  },

  /**
   * 加载指标类型列表
   */
  async loadIndicatorTypes() {
    try {
      const res = await api.getIndicatorTypes()
      return { data: res.data || [] }
    } catch (err) {
      console.error('加载指标类型失败:', err)
      // 如果加载失败，返回空数组
      return { data: [] }
    }
  },

  /**
   * 首页事件时间轴（按时间倒序）
   */
  async loadEventsTimeline() {
    try {
      const res = await api.getEvents({ limit: 20 })
      const rawEvents = res.events || res.data || []
      const parseTime = (value) => {
        const ts = new Date(value || 0).getTime()
        return Number.isFinite(ts) ? ts : 0
      }

      const sorted = [...rawEvents].sort((a, b) => {
        const aStart = parseTime(a.start_date || a.created_at)
        const bStart = parseTime(b.start_date || b.created_at)
        if (bStart !== aStart) {
          return bStart - aStart
        }
        const aCreated = parseTime(a.created_at)
        const bCreated = parseTime(b.created_at)
        return bCreated - aCreated
      })

      const recentEvents = sorted.slice(0, 5).map(event => ({
        ...event,
        event_type_label: this.getEventTypeLabel(event.event_type),
        date_range: this.getEventDateRange(event)
      }))

      if (sorted.length > 0 && this.data.showAggregateTip) {
        this.setData({ showAggregateTip: false })
        wx.setStorageSync('eventAutoAggregateTipSeen', true)
      }

      this.setData({ recentEvents })
      return { count: sorted.length }
    } catch (err) {
      console.error('加载事件时间轴失败:', err)
      this.setData({ recentEvents: [] })
      return { count: 0 }
    }
  },

  getEventTypeLabel(type) {
    const labelMap = {
      illness: '疾病事件',
      checkup: '体检事件',
      chronic_management: '慢病管理',
      emergency: '急诊事件',
      wellness: '健康管理',
      medication_course: '用药疗程',
      other: '其他'
    }
    return labelMap[type] || '其他'
  },

  getEventDateRange(event) {
    const start = event.start_date || ''
    const end = event.end_date || ''
    if (start && end && start !== end) {
      return `${start} ~ ${end}`
    }
    return start || end || ''
  },

  /**
   * 加载趋势数据
   */
  async loadTrendData() {
    try {
      const res = await api.getIndicators({
        type: this.data.currentTrendType,
        ordering: '-checkup__checkup_date',
        page_size: 50
      })

      // 按指标名称分组
      const indicators = res.data || res.results || []
      const grouped = {}

      indicators.forEach(item => {
        if (!grouped[item.indicator_name]) {
          grouped[item.indicator_name] = []
        }
        grouped[item.indicator_name].push({
          date: util.formatDate(item.checkup.checkup_date, 'YYYY-MM-DD'),
          value: item.value,
          value_display: item.value_display || item.value,
          unit: item.unit,
          status: item.status
        })
      })

      // 转换为数组格式，并确保每个指标的 values 按日期降序排序（新的在前）
      const trendData = Object.keys(grouped).map(name => {
        const values = grouped[name]
        // 按日期降序排序
        values.sort((a, b) => new Date(b.date) - new Date(a.date))
        return {
          name,
          values,
          unit: values[0].unit
        }
      })

      this.setData({ trendData })
    } catch (err) {
      console.error('加载趋势数据失败:', err)
      this.setData({ trendData: [] })
    }
  },

  /**
   * 切换趋势类型
   */
  switchTrendType(e) {
    const type = e.currentTarget.dataset.type
    const currentType = this.data.trendTypes.find(t => t.type === type)
    const currentTypeName = currentType ? currentType.name : ''

    this.setData({
      currentTrendType: type,
      currentTrendTypeName: currentTypeName
    }, () => {
      // 在 setData 完成后再加载趋势数据
      this.loadTrendData()
    })
  },

  /**
   * 查看趋势详情
   */
  viewTrendDetail(e) {
    const index = e.currentTarget.dataset.index
    const trend = this.data.trendData[index]
    // 可以导航到详细趋势页面
  },

  /**
   * 一键自动整合事件（按时间自动聚类）
   */
  async autoAggregateEvents() {
    if (this.data.autoAggregating) return

    this.setData({
      autoAggregating: true,
      showAggregateTip: false
    })
    wx.setStorageSync('eventAutoAggregateTipSeen', true)

    util.showLoading('正在自动整合...')
    try {
      const res = await api.autoClusterEvents({ days_threshold: 7 })
      const created = Number(res.events_created || 0)

      await this.loadData()
      util.showToast(created > 0 ? `已新增 ${created} 个事件` : '已完成自动整合')
    } catch (err) {
      console.error('自动整合事件失败:', err)
      util.showToast(err.message || '自动整合失败')
    } finally {
      util.hideLoading()
      this.setData({ autoAggregating: false })
    }
  },

  // ==================== 页面跳转 ====================

  goToCheckups() {
    wx.switchTab({ url: '/pages/checkups/checkups' })
  },

  goToUpload() {
    wx.switchTab({ url: '/pages/upload/upload' })
  },

  goToConversations() {
    wx.switchTab({ url: '/pages/ai-advice/ai-advice' })
  },

  goToIntegration() {
    wx.navigateTo({ url: '/pages/integration/integration' })
  },

  goToMedications() {
    wx.navigateTo({ url: '/pages/medications/medications' })
  },

  goToTrends() {
    wx.navigateTo({ url: '/pages/trends/trends' })
  },

  goToAIAdvice() {
    wx.switchTab({ url: '/pages/ai-advice/ai-advice' })
  },

  goToEventDetail(e) {
    const id = e.currentTarget.dataset.id
    if (!id) return
    wx.navigateTo({
      url: `/pages/event-detail/event-detail?id=${id}`
    })
  },

  goToSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' })
  }
})
