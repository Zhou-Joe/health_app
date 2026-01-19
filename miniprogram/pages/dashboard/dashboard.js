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
    currentTrendType: '',
    currentTrendTypeName: '',
    // 趋势类型列表（动态加载）
    trendTypes: [],
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
      const [checkupsRes, abnormalRes, conversationsRes, indicatorTypesRes] = await Promise.all([
        api.getCheckups({ page: 1, page_size: 5 }),
        this.loadAbnormalIndicators(),
        api.getConversations(),
        this.loadIndicatorTypes()
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
        recentCheckups: checkups,
        stats: {
          checkupCount: checkupsRes.total || checkupsRes.count || 0,
          indicatorCount: indicatorCount,
          conversationCount: conversationsRes.total || conversationsRes.count || 0,
          abnormalCount: this.data.abnormalIndicators.length
        },
        trendTypes: trendTypes,
        currentTrendType: currentTrendType,
        currentTrendTypeName: currentTypeName
      })

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
      console.log('加载指标类型:', res.data)
      return { data: res.data || [] }
    } catch (err) {
      console.error('加载指标类型失败:', err)
      // 如果加载失败，返回空数组
      return { data: [] }
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

  goToMedications() {
    wx.navigateTo({ url: '/pages/medications/medications' })
  },

  goToAIAdvice() {
    wx.switchTab({ url: '/pages/ai-advice/ai-advice' })
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
