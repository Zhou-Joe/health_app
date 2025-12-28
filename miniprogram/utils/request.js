// utils/request.js - 请求封装
const app = getApp()

/**
 * 发起HTTP请求
 * @param {string} url - 请求地址
 * @param {string} method - 请求方法
 * @param {object} data - 请求数据
 * @param {boolean} needAuth - 是否需要认证
 */
function request(url, method = 'GET', data = {}, needAuth = true, retryCount = 0) {
  return new Promise((resolve, reject) => {
    const header = {
      'content-type': 'application/json'
    }

    // 优先使用globalData中的token，如果不存在则从storage读取
    let token = app.globalData.token
    if (needAuth && !token) {
      token = wx.getStorageSync('token')
      if (token) {
        app.globalData.token = token
      }
    }

    if (needAuth && token) {
      header['Authorization'] = `Bearer ${token}`
    }

    wx.request({
      url: `${app.globalData.baseUrl}/api/miniprogram${url}`,
      method: method,
      data: data,
      header: header,
      timeout: 30000,
      success: (res) => {
        if (res.statusCode === 200) {
          if (res.data.success) {
            resolve(res.data)
          } else {
            reject(res.data)
          }
        } else if (res.statusCode === 401) {
          app.clearLoginInfo()
          wx.reLaunch({
            url: '/pages/login/login'
          })
          reject({ message: '请先登录' })
        } else if (res.statusCode >= 500 && retryCount < 2) {
          setTimeout(() => {
            request(url, method, data, needAuth, retryCount + 1)
              .then(resolve)
              .catch(reject)
          }, 1000 * (retryCount + 1))
        } else {
          reject({ message: res.data.message || '请求失败' })
        }
      },
      fail: (err) => {
        if (retryCount < 2) {
          setTimeout(() => {
            request(url, method, data, needAuth, retryCount + 1)
              .then(resolve)
              .catch(reject)
          }, 1000 * (retryCount + 1))
        } else {
          reject({ message: '网络请求失败，请检查网络连接' })
        }
      }
    })
  })
}

// 文件上传
function uploadFile(filePath, formData = {}, retryCount = 0) {
  return new Promise((resolve, reject) => {
    // 优先使用globalData中的token，如果不存在则从storage读取
    let token = app.globalData.token
    if (!token) {
      token = wx.getStorageSync('token')
      if (token) {
        app.globalData.token = token
      }
    }

    wx.uploadFile({
      url: `${app.globalData.baseUrl}/api/miniprogram/upload/`,
      filePath: filePath,
      name: 'file',
      formData: formData,
      header: token ? {
        'Authorization': `Bearer ${token}`
      } : {},
      timeout: 60000,
      success: (res) => {
        try {
          const data = JSON.parse(res.data)
          if (data.success) {
            resolve(data)
          } else {
            reject(data)
          }
        } catch (e) {
          reject({ message: '响应解析失败' })
        }
      },
      fail: (err) => {
        if (retryCount < 2) {
          setTimeout(() => {
            uploadFile(filePath, formData, retryCount + 1)
              .then(resolve)
              .catch(reject)
          }, 2000 * (retryCount + 1))
        } else {
          reject({ message: '上传失败，请检查网络连接' })
        }
      }
    })
  })
}

module.exports = {
  request,
  uploadFile,
  get: (url, data) => request(url, 'GET', data),
  post: (url, data) => request(url, 'POST', data),
  put: (url, data) => request(url, 'PUT', data),
  delete: (url, data) => request(url, 'DELETE', data)
}
