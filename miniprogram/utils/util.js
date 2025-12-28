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
  throttle
}
