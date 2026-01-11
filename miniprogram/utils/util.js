// utils/util.js - 工具函数

/**
 * 格式化日期
 */
function formatDate(date, format = 'YYYY-MM-DD') {
  if (!date) return ''

  const d = new Date(date)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hour = String(d.getHours()).padStart(2, '0')
  const minute = String(d.getMinutes()).padStart(2, '0')
  const second = String(d.getSeconds()).padStart(2, '0')

  return format
    .replace('YYYY', year)
    .replace('MM', month)
    .replace('DD', day)
    .replace('HH', hour)
    .replace('mm', minute)
    .replace('ss', second)
}

/**
 * 格式化相对时间（如：刚刚、5分钟前）
 */
function formatRelativeTime(date) {
  if (!date) return ''

  const now = new Date()
  const target = new Date(date)
  const diff = (now - target) / 1000 // 秒

  if (diff < 60) {
    return '刚刚'
  } else if (diff < 3600) {
    return `${Math.floor(diff / 60)}分钟前`
  } else if (diff < 86400) {
    return `${Math.floor(diff / 3600)}小时前`
  } else if (diff < 2592000) {
    return `${Math.floor(diff / 86400)}天前`
  } else if (diff < 31536000) {
    return `${Math.floor(diff / 2592000)}个月前`
  } else {
    return `${Math.floor(diff / 31536000)}年前`
  }
}

/**
 * 显示Toast提示
 */
function showToast(title, icon = 'none', duration = 2000) {
  wx.showToast({
    title,
    icon,
    duration
  })
}

/**
 * 显示Loading
 */
function showLoading(title = '加载中...') {
  wx.showLoading({
    title,
    mask: true
  })
}

/**
 * 隐藏Loading
 */
function hideLoading() {
  wx.hideLoading()
}

/**
 * 显示确认对话框
 */
function showConfirm(content, title = '提示') {
  return new Promise((resolve) => {
    wx.showModal({
      title,
      content,
      success: (res) => {
        resolve(res.confirm)
      }
    })
  })
}

/**
 * 显示操作菜单
 */
function showActionSheet(itemList) {
  return new Promise((resolve) => {
    wx.showActionSheet({
      itemList,
      success: (res) => {
        resolve(res.tapIndex)
      }
    })
  })
}

/**
 * 获取指标类型名称
 */
function getIndicatorTypeName(type) {
  const typeMap = {
    physical_exam: '体格检查',
    blood_routine: '血液常规',
    biochemistry: '生化检验',
    liver_function: '肝功能',
    kidney_function: '肾功能',
    thyroid_function: '甲状腺功能',
    tumor_markers: '肿瘤标志物',
    urine_exam: '尿液检查',
    other_exam: '其他检查'
  }
  return typeMap[type] || '未知'
}

/**
 * 获取指标状态信息
 */
function getIndicatorStatusInfo(status) {
  const statusMap = {
    normal: { text: '正常', class: 'status-normal' },
    abnormal: { text: '异常', class: 'status-abnormal' },
    attention: { text: '关注', class: 'status-attention' }
  }
  return statusMap[status] || { text: '未知', class: '' }
}

/**
 * 防抖函数
 */
function debounce(fn, delay = 500) {
  let timer = null
  return function(...args) {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      fn.apply(this, args)
    }, delay)
  }
}

/**
 * 节流函数
 */
function throttle(fn, delay = 500) {
  let last = 0
  return function(...args) {
    const now = Date.now()
    if (now - last > delay) {
      last = now
      fn.apply(this, args)
    }
  }
}

/**
 * 获取基础URL
 */
function getBaseURL() {
  const app = getApp()
  return app.globalData.baseUrl || ''
}

/**
 * 深拷贝对象
 */
function deepClone(obj) {
  if (obj === null || typeof obj !== 'object') return obj
  if (obj instanceof Date) return new Date(obj)
  if (obj instanceof Array) return obj.map(item => deepClone(item))

  const cloned = {}
  for (const key in obj) {
    if (obj.hasOwnProperty(key)) {
      cloned[key] = deepClone(obj[key])
    }
  }
  return cloned
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

/**
 * 解析Markdown为小程序可显示的文本
 * 小程序不支持完整的Markdown渲染，这里做简单的处理
 */
function parseMarkdown(text) {
  if (!text) return ''

  return text
    // 标题
    .replace(/^### (.*$)/gim, '\n$1\n')
    .replace(/^## (.*$)/gim, '\n$1\n')
    .replace(/^# (.*$)/gim, '\n$1\n')
    // 粗体
    .replace(/\*\*(.*?)\*\*/g, '$1')
    // 斜体
    .replace(/\*(.*?)\*/g, '$1')
    // 代码块
    .replace(/```([\s\S]*?)```/g, '\n代码:\n$1\n')
    // 行内代码
    .replace(/`([^`]+)`/g, '$1')
    // 链接
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')
    // 列表
    .replace(/^\s*-\s+/gm, '• ')
    // 清理多余空行
    .replace(/\n{3,}/g, '\n\n')
}

/**
 * 计算变化率
 */
function calculateChange(current, previous) {
  if (!current || !previous || previous === 0) return null
  const change = current - previous
  const percentChange = (change / previous) * 100
  return {
    absolute: change,
    percent: percentChange
  }
}

/**
 * 格式化变化率显示
 */
function formatChange(changeData, unit = '') {
  if (!changeData) return '-'

  const { absolute, percent } = changeData
  const sign = absolute > 0 ? '+' : ''
  return `${sign}${absolute}${unit} (${sign}${percent.toFixed(1)}%)`
}

/**
 * 获取变化率的样式类
 */
function getChangeClass(changeData) {
  if (!changeData) return 'text-neutral'
  if (changeData.absolute > 0) return 'text-danger'
  if (changeData.absolute < 0) return 'text-success'
  return 'text-neutral'
}

/**
 * 数据分组
 */
function groupBy(array, key) {
  return array.reduce((result, item) => {
    const group = item[key]
    if (!result[group]) {
      result[group] = []
    }
    result[group].push(item)
    return result
  }, {})
}

/**
 * 数组去重
 */
function unique(array, key) {
  if (!key) {
    return [...new Set(array)]
  }
  const seen = new Set()
  return array.filter(item => {
    const k = item[key]
    if (seen.has(k)) {
      return false
    }
    seen.add(k)
    return true
  })
}

/**
 * 安全的JSON解析
 */
function safeJsonParse(str, defaultValue = null) {
  try {
    return JSON.parse(str)
  } catch (e) {
    return defaultValue
  }
}

/**
 * 生成唯一ID
 */
function generateId() {
  return Date.now().toString(36) + Math.random().toString(36).substr(2)
}

/**
 * 验证手机号
 */
function validatePhone(phone) {
  return /^1[3-9]\d{9}$/.test(phone)
}

/**
 * 验证邮箱
 */
function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
}

module.exports = {
  formatDate,
  formatRelativeTime,
  showToast,
  showLoading,
  hideLoading,
  showConfirm,
  showActionSheet,
  getIndicatorTypeName,
  getIndicatorStatusInfo,
  debounce,
  throttle,
  getBaseURL,
  deepClone,
  formatFileSize,
  parseMarkdown,
  calculateChange,
  formatChange,
  getChangeClass,
  groupBy,
  unique,
  safeJsonParse,
  generateId,
  validatePhone,
  validateEmail
}
