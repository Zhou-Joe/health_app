/**
 * 健康趋势页面
 * 按指标类型分组，展示同一指标的趋势
 */

const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    // 按类型分组的趋势数据
    trendGroups: [],
    loading: true
  },

  onLoad() {
    this.loadAllTrends()
  },

  /**
   * 加载所有指标的趋势数据
   */
  async loadAllTrends() {
    this.setData({ loading: true })

    try {
      // 1. 获取用户所有的指标数据
      const res = await api.getIndicators({
        ordering: '-checkup__checkup_date',
        page_size: 500
      })

      const allIndicators = res.data || res.results || []
      console.log('获取到所有指标:', allIndicators.length, '个')

      if (allIndicators.length === 0) {
        this.setData({ loading: false, trendGroups: [] })
        return
      }

      // 2. 按指标名称分组
      const indicatorGroups = {}
      allIndicators.forEach(indicator => {
        const name = indicator.indicator_name
        if (!indicatorGroups[name]) {
          indicatorGroups[name] = []
        }
        indicatorGroups[name].push(indicator)
      })

      console.log('按名称分组后，共有', Object.keys(indicatorGroups).length, '种不同的指标')

      // 3. 为每个指标名称计算趋势
      const indicatorTrends = Object.keys(indicatorGroups)
        .map(name => {
          const indicators = indicatorGroups[name]
          // 按检查日期排序
          indicators.sort((a, b) => {
            return new Date(a.checkup.checkup_date) - new Date(b.checkup.checkup_date)
          })

          return {
            name: name,
            indicators: indicators,
            type: indicators[0].indicator_type // 获取指标类型
          }
        })
        .filter(item => item.indicators.length >= 2) // 至少有2次数据才能看趋势
        .map(item => this.calculateTrend(item))
        .filter(trend => trend !== null) // 过滤掉计算失败的

      console.log('最终趋势数据:', indicatorTrends.length, '个指标')

      // 4. 按指标类型分组
      const trendGroups = this.groupByType(indicatorTrends)

      this.setData({
        trendGroups,
        loading: false
      })

    } catch (err) {
      console.error('加载趋势数据失败:', err)
      util.showToast('加载失败')
      this.setData({ loading: false })
    }
  },

  /**
   * 按指标类型分组
   */
  groupByType(indicatorTrends) {
    // 指标类型名称映射
    const typeNames = {
      'blood_routine': '血液常规',
      'urine': '尿液检查',
      'biochemistry': '生化检查',
      'thyroid': '甲状腺',
      'lipid': '血脂',
      'liver': '肝功能',
      'kidney': '肾功能',
      'blood_sugar': '血糖',
      'tumor': '肿瘤标志物',
      'general_exam': '一般检查',
      'ultrasound': '超声检查',
      'special_organs': '专科检查',
      'ecg': '心电图',
      'xray': 'X光检查',
      'pathology': '病理检查',
      'other': '其他检查'
    }

    // 指标类型图标
    const typeIcons = {
      'blood_routine': '🩸',
      'urine': '💧',
      'biochemistry': '🧪',
      'thyroid': '🦋',
      'lipid': '🫀',
      'liver': '🫁',
      'kidney': '🫘',
      'blood_sugar': '🍬',
      'tumor': '🎯',
      'general_exam': '👤',
      'ultrasound': '📡',
      'special_organs': '👁️',
      'ecg': '💓',
      'xray': '📷',
      'pathology': '🔬',
      'other': '📋'
    }

    // 按类型分组
    const groups = {}
    indicatorTrends.forEach(indicator => {
      const type = indicator.type || 'other'
      if (!groups[type]) {
        groups[type] = []
      }
      groups[type].push(indicator)
    })

    // 转换为数组并添加展开状态
    return Object.keys(groups).map(type => ({
      typeName: typeNames[type] || type,
      typeIcon: typeIcons[type] || '📊',
      type: type,
      indicators: groups[type],
      expanded: false // 默认折叠
    }))
  },

  /**
   * 计算单个指标的趋势数据
   */
  calculateTrend(item) {
    const { name, indicators, type } = item

    if (!indicators || indicators.length === 0) {
      return null
    }

    // 提取数值和单位
    const unit = indicators[0].unit || ''
    const values = indicators.map(indicator => {
      const num = parseFloat(indicator.value)
      return isNaN(num) ? null : num
    }).filter(v => v !== null)

    if (values.length === 0) {
      return null
    }

    const maxValue = Math.max(...values)
    const minValue = Math.min(...values)
    const valueRange = maxValue - minValue || 1

    // 获取参考值（使用最新一次的参考值）
    const latestIndicator = indicators[indicators.length - 1]
    const reference = latestIndicator.reference_range || ''

    // 最新值和状态
    const latestValue = parseFloat(latestIndicator.value) || 0
    const latestStatus = latestIndicator.status === 'normal' ? 'normal' : 'abnormal'

    // 构建图表数据
    const chartData = indicators.map(indicator => {
      const value = parseFloat(indicator.value) || 0
      // 计算柱子高度（最小10%，避免太矮）
      const height = valueRange > 0
        ? Math.max(10, ((value - minValue) / valueRange) * 80 + 10)
        : 50

      // 根据状态设置颜色
      let color = '#2ECC71' // 正常
      if (indicator.status === 'abnormal_high' || indicator.status === 'abnormal_low' || indicator.status === 'abnormal') {
        color = '#E85D4C' // 异常
      } else if (indicator.status === 'attention') {
        color = '#F5A962' // 关注
      }

      return {
        id: indicator.id,
        value: value,
        height: height.toFixed(1),
        color: color,
        checkupId: indicator.checkup.id,
        date: indicator.checkup.checkup_date
      }
    })

    // 判断趋势
    let trendDirection = 'stable'
    let trendText = '稳定'

    if (values.length >= 2) {
      const recent = values.slice(-3) // 最近3次
      const earlier = values.slice(0, -3) // 之前的数据

      if (earlier.length > 0) {
        const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length
        const earlierAvg = earlier.reduce((a, b) => a + b, 0) / earlier.length
        const change = ((recentAvg - earlierAvg) / earlierAvg) * 100

        if (change > 5) {
          trendDirection = 'up'
          trendText = '上升 ↗'
        } else if (change < -5) {
          trendDirection = 'down'
          trendText = '下降 ↘'
        }
      }
    }

    return {
      id: name,
      name: name,
      type: type,
      unit: unit,
      count: indicators.length,
      latestValue: latestValue.toFixed(1),
      latestStatus: latestStatus,
      reference: reference,
      trendDirection: trendDirection,
      trendText: trendText,
      data: chartData
    }
  },

  /**
   * 切换分组展开/折叠状态
   */
  toggleGroup(e) {
    const index = e.currentTarget.dataset.index
    const key = `trendGroups[${index}].expanded`
    const currentValue = this.data.trendGroups[index].expanded

    this.setData({
      [key]: !currentValue
    })
  }
})
