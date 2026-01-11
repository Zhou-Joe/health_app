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
    // 统计数据
    stats: {
      checkupCount: 0,
      indicatorCount: 0,
      conversationCount: 0,
      abnormalCount: 0
    },
    // 最新报告
    recentCheckups: [],
    // 异常指标
    abnormalIndicators: [],
    // 健康趋势数据
    trendData: [],
    // 当前显示的趋势类型
    currentTrendType: 'blood_routine',
    // 趋势类型列表
    trendTypes: [
      { type: 'blood_routine', name: '血液常规', icon: '🩸' },
      { type: 'biochemistry', name: '生化检验', icon: '🧪' },
      { type: 'liver_function', name: '肝功能', icon: '🫀' },
      { type: 'kidney_function', name: '肾功能', icon: '⚕️' }
    ],
    // 加载状态
    loading: false,
    refreshing: false
  },

  onLoad() {
    this.checkLogin()
    this.loadData()
  },

  onShow() {
    // 从其他页面返回时刷新数据
    this.loadData()
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
    if (!app.globalData.isLogin) {
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
      const [checkupsRes, abnormalRes, conversationsRes] = await Promise.all([
        api.getCheckups({ page: 1, page_size: 5 }),
        this.loadAbnormalIndicators(),
        api.getConversations()
      ])

      const checkups = checkupsRes.data || checkupsRes.results || []
      let indicatorCount = 0
      let abnormalCount = 0

      checkups.forEach(c => {
        indicatorCount += c.indicators_count || 0
      })

      // 加载趋势数据
      await this.loadTrendData()

      this.setData({
        recentCheckups: checkups,
        stats: {
          checkupCount: checkupsRes.total || checkupsRes.count || 0,
          indicatorCount: indicatorCount,
          conversationCount: conversationsRes.total || conversationsRes.count || 0,
          abnormalCount: this.data.abnormalIndicators.length
        }
      })
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
        page_size: 5
      })

      const indicators = res.data || res.results || []
      this.setData({
        abnormalIndicators: indicators.map(item => ({
          ...item,
          checkup_date: util.formatDate(item.checkup_date, 'MM-DD')
        }))
      })
    } catch (err) {
      console.error('加载异常指标失败:', err)
      this.setData({ abnormalIndicators: [] })
    }
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

      // 转换为数组格式
      const trendData = Object.keys(grouped).map(name => ({
        name,
        values: grouped[name],
        unit: grouped[name][0].unit
      }))

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
    this.setData({ currentTrendType: type })
    this.loadTrendData()
  },

  /**
   * 查看趋势详情
   */
  viewTrendDetail(e) {
    const index = e.currentTarget.dataset.index
    const trend = this.data.trendData[index]
    // 可以导航到详细趋势页面
    console.log('查看趋势:', trend)
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

  goToAIAdvice() {
    wx.switchTab({ url: '/pages/ai-advice/ai-advice' })
  },

  goToManualInput() {
    wx.navigateTo({ url: '/pages/indicator-edit/indicator-edit' })
  },

  goToCheckupDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({
      url: `/pages/checkup-detail/checkup-detail?id=${id}`
    })
  },

  goToAbnormalIndicator(e) {
    const id = e.currentTarget.dataset.id
    const checkupId = e.currentTarget.dataset.checkup
    wx.navigateTo({
      url: `/pages/checkup-detail/checkup-detail?id=${checkupId}`
    })
  },

  goToSettings() {
    wx.navigateTo({ url: '/pages/settings/settings' })
  }
})
