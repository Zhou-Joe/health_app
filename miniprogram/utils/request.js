/**
 * 网络请求封装
 * 支持拦截器、错误处理、重试等
 */

const config = require('../config.js')

class Request {
  constructor() {
    this.baseUrl = config.server.baseUrl
    this.timeout = config.server.timeout
    this.interceptors = {
      request: [],
      response: []
    }
  }

  /**
   * 添加请求拦截器
   */
  addRequestInterceptor(fn) {
    this.interceptors.request.push(fn)
  }

  /**
   * 添加响应拦截器
   */
  addResponseInterceptor(fn) {
    this.interceptors.response.push(fn)
  }

  /**
   * 获取完整的URL
   */
  getFullUrl(url) {
    // 如果是完整URL，直接返回
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return url
    }
    // 拼接base URL
    return this.baseUrl + url
  }

  /**
   * 获取Token
   */
  getToken() {
    return wx.getStorageSync(config.storageKeys.TOKEN) || ''
  }

  /**
   * 通用请求方法
   */
  request(options) {
    return new Promise((resolve, reject) => {
      // 请求拦截器
      let requestConfig = {
        url: this.getFullUrl(options.url),
        method: options.method || 'GET',
        data: options.data || {},
        header: {
          'Content-Type': 'application/json',
          ...options.header
        },
        timeout: options.timeout || this.timeout
      }

      // 添加Token
      const token = this.getToken()
      if (token) {
        requestConfig.header['Authorization'] = `Token ${token}`
      }

      // 执行请求拦截器
      this.interceptors.request.forEach(interceptor => {
        requestConfig = interceptor(requestConfig) || requestConfig
      })

      // 发起请求
      wx.request({
        ...requestConfig,
        success: (res) => {
          // 响应拦截器
          let response = res
          this.interceptors.response.forEach(interceptor => {
            response = interceptor(response) || response
          })

          // 处理响应
          if (response.statusCode >= 200 && response.statusCode < 300) {
            resolve(response.data)
          } else if (response.statusCode === 401) {
            // Token过期，清除登录信息
            const app = getApp()
            app.clearLoginInfo()
            wx.reLaunch({ url: config.pages.login })
            reject(new Error('登录已过期，请重新登录'))
          } else {
            const errorMsg = response.data?.message || response.data?.error || '请求失败'
            reject(new Error(errorMsg))
          }
        },
        fail: (err) => {
          console.error('请求失败:', err)
          let errorMsg = '网络请求失败'

          if (err.errMsg.includes('timeout')) {
            errorMsg = '请求超时，请稍后重试'
          } else if (err.errMsg.includes('fail to connect')) {
            errorMsg = '网络连接失败，请检查网络'
          }

          reject(new Error(errorMsg))
        }
      })
    })
  }

  /**
   * GET请求
   */
  get(url, data = {}, options = {}) {
    return this.request({
      url,
      method: 'GET',
      data,
      ...options
    })
  }

  /**
   * POST请求
   */
  post(url, data = {}, options = {}) {
    return this.request({
      url,
      method: 'POST',
      data,
      ...options
    })
  }

  /**
   * PUT请求
   */
  put(url, data = {}, options = {}) {
    return this.request({
      url,
      method: 'PUT',
      data,
      ...options
    })
  }

  /**
   * DELETE请求
   */
  delete(url, data = {}, options = {}) {
    return this.request({
      url,
      method: 'DELETE',
      data,
      ...options
    })
  }

  /**
   * 上传文件
   */
  uploadFile(filePath, formData = {}, options = {}) {
    return new Promise((resolve, reject) => {
      const token = this.getToken()
      const header = {}
      if (token) {
        header['Authorization'] = `Token ${token}`
      }

      wx.uploadFile({
        url: this.getFullUrl(options.url || config.api.uploadReport),
        filePath,
        name: 'file',
        formData,
        header,
        timeout: options.timeout || 60000, // 上传超时时间更长
        success: (res) => {

          if (res.statusCode === 200 || res.statusCode === 201) {
            try {
              const data = JSON.parse(res.data)
              resolve(data)
            } catch (e) {
              resolve(res.data)
            }
          } else if (res.statusCode === 401) {
            const app = getApp()
            app.clearLoginInfo()
            wx.reLaunch({ url: config.pages.login })
            reject(new Error('登录已过期'))
          } else {
            // 尝试解析错误信息
            let errorMsg = '上传失败'
            try {
              const errorData = JSON.parse(res.data)
              errorMsg = errorData.message || errorData.error || errorMsg
            } catch (e) {
              // 无法解析，使用原始数据
              errorMsg = `上传失败 (状态码: ${res.statusCode})`
            }
            console.error('上传错误详情:', errorMsg)
            reject(new Error(errorMsg))
          }
        },
        fail: (err) => {
          console.error('上传失败:', err)
          let errorMsg = '上传失败'
          if (err.errMsg.includes('timeout')) {
            errorMsg = '上传超时，请稍后重试'
          }
          reject(new Error(errorMsg))
        }
      })
    })
  }

  /**
   * 下载文件
   */
  downloadFile(url, options = {}) {
    return new Promise((resolve, reject) => {
      const token = this.getToken()
      const header = {}
      if (token) {
        header['Authorization'] = `Token ${token}`
      }

      const fullUrl = this.getFullUrl(url)
      console.log('[下载文件] URL:', fullUrl)

      wx.downloadFile({
        url: fullUrl,
        header,
        timeout: options.timeout || 60000,
        success: (res) => {
          console.log('[下载文件] 响应:', res)
          if (res.statusCode === 200) {
            console.log('[下载文件] 成功:', res.tempFilePath)
            resolve(res.tempFilePath)
          } else if (res.statusCode === 401) {
            console.error('[下载文件] 未授权')
            const app = getApp()
            app.clearLoginInfo()
            wx.reLaunch({ url: config.pages.login })
            reject(new Error('登录已过期，请重新登录'))
          } else if (res.statusCode === 403) {
            console.error('[下载文件] 无权限')
            reject(new Error('没有权限访问此文件'))
          } else if (res.statusCode === 404) {
            console.error('[下载文件] 文件不存在')
            reject(new Error('文件不存在'))
          } else {
            console.error('[下载文件] 状态码异常:', res.statusCode, res)
            // 尝试读取错误信息
            if (res.tempFilePath) {
              wx.getFileSystemManager().readFile({
                filePath: res.tempFilePath,
                encoding: 'utf-8',
                success: (fileRes) => {
                  console.error('[下载文件] 错误响应内容:', fileRes.data)
                  try {
                    const errorData = JSON.parse(fileRes.data)
                    reject(new Error(errorData.message || errorData.error || '下载失败'))
                  } catch {
                    reject(new Error(`下载失败 (状态码: ${res.statusCode})`))
                  }
                },
                fail: () => {
                  reject(new Error(`下载失败 (状态码: ${res.statusCode})`))
                }
              })
            } else {
              reject(new Error(`下载失败 (状态码: ${res.statusCode})`))
            }
          }
        },
        fail: (err) => {
          console.error('[下载文件] 请求失败:', err)
          let errorMsg = '下载失败'
          if (err.errMsg) {
            if (err.errMsg.includes('fail to connect')) {
              errorMsg = '网络连接失败，请检查网络'
            } else if (err.errMsg.includes('timeout')) {
              errorMsg = '下载超时，请稍后重试'
            } else if (err.errMsg.includes('url not in domain list')) {
              errorMsg = '域名不在白名单中，请在开发设置中关闭域名校验'
            } else {
              errorMsg = `下载失败: ${err.errMsg}`
            }
          }
          reject(new Error(errorMsg))
        }
      })
    })
  }
}

// 创建单例
const request = new Request()

// 添加默认的响应拦截器
request.addResponseInterceptor((response) => {
  // 可以在这里统一处理响应数据
  return response
})

module.exports = request
