/**
 * 对话历史列表页面
 * 显示所有AI咨询历史记录
 */

const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    conversations: [],
    loading: false,
    showSearch: false,
    searchKeyword: '',
    searchFocused: false
  },

  onLoad() {
    this.loadConversations()
  },

  onShow() {
    // 每次显示页面时刷新列表
    this.loadConversations()
  },

  /**
   * 切换搜索框显示
   */
  toggleSearch() {
    this.setData({
      showSearch: !this.data.showSearch
    })
  },

  /**
   * 搜索输入
   */
  onSearchInput(e) {
    const keyword = e.detail.value
    this.setData({ searchKeyword: keyword })

    // 防抖搜索
    if (this.searchTimer) {
      clearTimeout(this.searchTimer)
    }

    this.searchTimer = setTimeout(() => {
      this.filterConversations(keyword)
    }, 300)
  },

  /**
   * 过滤对话列表
   */
  filterConversations(keyword) {
    if (!keyword || !keyword.trim()) {
      this.loadConversations()
      return
    }

    const filtered = this.data.conversations.filter(conv => {
      const title = (conv.title || '').toLowerCase()
      const preview = (conv.preview || '').toLowerCase()
      const searchLower = keyword.toLowerCase()
      return title.includes(searchLower) || preview.includes(searchLower)
    })

    this.setData({ conversations: filtered })
  },

  /**
   * 清除搜索
   */
  clearSearch() {
    this.setData({
      searchKeyword: '',
      showSearch: false
    })
    this.loadConversations()
  },

  /**
   * 加载对话列表
   */
  async loadConversations() {
    if (this.data.loading) return

    this.setData({ loading: true })
    util.showLoading('加载中...')

    try {
      const res = await api.getConversations()
      const conversations = (res.data || []).map(conv => ({
        ...conv,
        created_at: this.formatDate(conv.created_at),
        preview: this.generatePreview(conv)
      }))

      this.setData({ conversations })
    } catch (err) {
      console.error('加载对话列表失败:', err)
      util.showToast(err.message || '加载失败')
    } finally {
      this.setData({ loading: false })
      util.hideLoading()
    }
  },

  /**
   * 生成预览文本
   */
  generatePreview(conversation) {
    // 如果有预览字段直接使用
    if (conversation.preview) {
      return conversation.preview
    }

    // 否则使用标题
    if (conversation.title) {
      return conversation.title.length > 50
        ? conversation.title.substring(0, 50) + '...'
        : conversation.title
    }

    return '暂无预览'
  },

  /**
   * 格式化日期
   */
  formatDate(dateStr) {
    if (!dateStr) return ''

    const date = new Date(dateStr)
    const now = new Date()
    const diff = now - date

    // 小于1分钟
    if (diff < 60000) {
      return '刚刚'
    }

    // 小于1小时
    if (diff < 3600000) {
      return `${Math.floor(diff / 60000)}分钟前`
    }

    // 小于24小时
    if (diff < 86400000) {
      return `${Math.floor(diff / 3600000)}小时前`
    }

    // 小于7天
    if (diff < 604800000) {
      return `${Math.floor(diff / 86400000)}天前`
    }

    // 超过7天，显示具体日期
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')

    return `${year}-${month}-${day}`
  },

  /**
   * 跳转到对话详情
   */
  goToConversation(e) {
    const id = e.currentTarget.dataset.id
    const title = e.currentTarget.dataset.title || '对话'
    console.log('[小程序] 继续对话 - conversation_id:', id, 'title:', title)
    wx.navigateTo({
      url: `/pages/conversation/conversation?id=${id}`
    })
  },

  /**
   * 删除对话
   */
  async deleteConversation(e) {
    const id = e.currentTarget.dataset.id

    const confirm = await util.showConfirm('确定要删除这个对话吗？删除后无法恢复。')
    if (!confirm) return

    util.showLoading('删除中...')
    try {
      await api.deleteConversation(id)
      util.showToast('删除成功')

      // 从列表中移除
      const conversations = this.data.conversations.filter(c => c.id !== id)
      this.setData({ conversations })
    } catch (err) {
      console.error('删除失败:', err)
      util.showToast(err.message || '删除失败')
    } finally {
      util.hideLoading()
    }
  },

  /**
   * 导出对话
   */
  async exportConversation(e) {
    const conversationId = e.currentTarget.dataset.id

    util.showLoading('生成中...')
    try {
      const token = wx.getStorageSync('token')
      const baseUrl = 'https://www.zctestbench.asia'
      const exportUrl = `${baseUrl}/api/miniprogram/conversations/${conversationId}/export/word/`


      // 下载文件
      const downloadRes = await new Promise((resolve, reject) => {
        wx.downloadFile({
          url: exportUrl,
          header: {
            'Authorization': `Token ${token}`
          },
          success: (res) => {
            if (res.statusCode === 200) {
              resolve(res.tempFilePath)
            } else if (res.statusCode === 400) {
              // 业务错误，尝试读取错误信息
              wx.request({
                url: exportUrl,
                header: { 'Authorization': `Token ${token}` },
                method: 'GET',
                success: (errRes) => {
                  if (errRes.data && errRes.data.message) {
                    reject(new Error(errRes.data.message))
                  } else {
                    reject(new Error('对话无消息内容或其他业务错误'))
                  }
                },
                fail: () => {
                  reject(new Error('对话无消息内容或其他业务错误'))
                }
              })
            } else {
              reject(new Error(`服务器错误(${res.statusCode})，请联系管理员查看后台日志`))
            }
          },
          fail: (err) => {
            console.error('[导出] 下载失败:', err)
            reject(new Error('网络下载失败，请检查网络连接或配置下载域名白名单'))
          }
        })
      })

      util.hideLoading()

      // 打开文档
      wx.openDocument({
        filePath: downloadRes,
        fileType: 'docx',
        showMenu: true,
        success: () => {
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
   * 跳转到AI咨询页面
   */
  goToAIAdvice() {
    wx.navigateTo({
      url: '/pages/ai-advice/ai-advice'
    })
  },

  /**
   * 返回上一页
   */
  goBack() {
    wx.navigateBack()
  },

  /**
   * 阻止事件冒泡
   */
  stopPropagation() {
    // 空方法，用于阻止点击事件冒泡
  },

  /**
   * 加载更多
   */
  loadMore() {
    // 目前已加载所有数据，暂不需要分页
    // 如果需要分页加载，可以在这里实现
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    this.loadConversations().then(() => {
      wx.stopPullDownRefresh()
    })
  }
})
