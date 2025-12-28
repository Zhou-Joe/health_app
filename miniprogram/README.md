# 健康档案微信小程序

## 项目说明

这是一个完整的健康档案管理微信小程序，支持体检报告上传、AI分析、健康数据管理等功能。

## 目录结构

```
miniprogram/
├── pages/                    # 页面目录
│   ├── login/               # 登录页 ✓
│   ├── dashboard/           # 首页 ✓
│   ├── upload/              # 上传报告 ✓
│   ├── checkups/            # 报告列表 (需创建)
│   ├── checkup-detail/      # 报告详情 (需创建)
│   ├── indicators/          # 健康指标 (需创建)
│   ├── indicator-edit/      # 编辑指标 (需创建)
│   ├── ai-advice/           # AI咨询 (需创建)
│   ├── conversation/        # AI对话 (需创建)
│   ├── integration/         # 数据整合 (需创建)
│   └── settings/            # 设置 (需创建)
├── components/              # 组件目录
├── utils/                   # 工具函数 ✓
│   ├── request.js          # 请求封装
│   ├── api.js              # API接口
│   └── util.js             # 工具函数
├── images/                  # 图片资源
├── app.js                   # 小程序入口 ✓
├── app.json                 # 小程序配置 ✓
├── app.wxss                 # 全局样式 ✓
├── sitemap.json            # 站点地图 ✓
└── project.config.json     # 项目配置 ✓
```

## 已创建文件

✅ 核心配置文件（app.js, app.json, app.wxss等）
✅ 工具类（utils/request.js, utils/api.js, utils/util.js）
✅ 登录页面（pages/login/）
✅ 首页（pages/dashboard/）
✅ 上传页面（pages/upload/）

## 待创建页面

### 1. 体检报告列表 (pages/checkups/)

**checkups.wxml**
```xml
<view class="checkups-container">
  <view class="checkup-list">
    <block wx:if="{{checkups.length > 0}}">
      <view class="checkup-item card" wx:for="{{checkups}}" wx:key="id"
            bindtap="goToDetail" data-id="{{item.id}}">
        <view class="checkup-header">
          <text class="hospital">{{item.hospital}}</text>
          <text class="date">{{item.checkup_date}}</text>
        </view>
        <view class="checkup-body">
          <text class="department">{{item.department || '未知科室'}}</text>
          <view class="status-badge status-{{item.status}}">
            {{item.status === 'completed' ? '已完成' : '处理中'}}
          </view>
        </view>
        <view class="checkup-footer">
          <text class="indicator-count">{{item.indicators_count}}项指标</text>
          <text class="delete-btn" catchtap="deleteCheckup" data-id="{{item.id}}">删除</text>
        </view>
      </view>
    </block>
    <view class="empty-container" wx:else>
      <text>暂无体检报告</text>
    </view>
  </view>
</view>
```

**checkups.js**
```javascript
const api = require('../../utils/api.js')
const util = require('../../utils/util.js')

Page({
  data: {
    checkups: [],
    page: 1,
    hasMore: true
  },

  onLoad() {
    this.loadCheckups()
  },

  async loadCheckups() {
    if (!this.data.hasMore) return

    try {
      const res = await api.getCheckups({
        page: this.data.page,
        page_size: 20
      })

      this.setData({
        checkups: [...this.data.checkups, ...(res.data || [])],
        hasMore: res.has_more,
        page: this.data.page + 1
      })
    } catch (err) {
      util.showToast(err.message || '加载失败')
    }
  },

  goToDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/checkup-detail/checkup-detail?id=${id}` })
  },

  async deleteCheckup(e) {
    const id = e.currentTarget.dataset.id
    const confirm = await util.showConfirm('确定删除这份报告吗？')
    if (!confirm) return

    try {
      await api.deleteCheckup(id)
      util.showToast('删除成功', 'success')
      this.setData({ checkups: [], page: 1 })
      this.loadCheckups()
    } catch (err) {
      util.showToast(err.message || '删除失败')
    }
  },

  onReachBottom() {
    this.loadCheckups()
  }
})
```

### 2. 报告详情页 (pages/checkup-detail/)

**checkup-detail.wxml**
```xml
<view class="detail-container">
  <!-- 报告信息 -->
  <view class="info-card card">
    <view class="info-row">
      <text class="label">体检机构</text>
      <text class="value">{{checkup.hospital}}</text>
    </view>
    <view class="info-row">
      <text class="label">体检日期</text>
      <text class="value">{{checkup.checkup_date}}</text>
    </view>
    <view class="info-row">
      <text class="label">科室</text>
      <text class="value">{{checkup.department || '未知'}}</text>
    </view>
  </view>

  <!-- 指标统计 -->
  <view class="stats-card card">
    <view class="stat-item">
      <text class="stat-value">{{stats.total}}</text>
      <text class="stat-label">总指标</text>
    </view>
    <view class="stat-item">
      <text class="stat-value text-success">{{stats.normal}}</text>
      <text class="stat-label">正常</text>
    </view>
    <view class="stat-item">
      <text class="stat-value text-danger">{{stats.abnormal}}</text>
      <text class="stat-label">异常</text>
    </view>
  </view>

  <!-- 指标列表 -->
  <view class="indicators-card card">
    <view class="card-title">健康指标</view>
    <view class="indicator-list">
      <view class="indicator-item" wx:for="{{indicators}}" wx:key="id"
            bindtap="goToIndicatorEdit" data-id="{{item.id}}">
        <view class="indicator-header">
          <text class="indicator-name">{{item.indicator_name}}</text>
          <view class="status-badge status-{{item.status}}">
            {{item.status === 'normal' ? '正常' : '异常'}}
          </view>
        </view>
        <view class="indicator-value">
          <text class="value">{{item.value}}</text>
          <text class="unit">{{item.unit}}</text>
        </view>
      </view>
    </view>
  </view>
</view>
```

### 3. 编辑指标页 (pages/indicator-edit/)

**indicator-edit.js 核心逻辑**
```javascript
const api = require('../../utils/api.js')

Page({
  data: {
    checkupId: null,
    indicatorId: null,
    formData: {
      indicator_type: 'other_exam',
      indicator_name: '',
      value: '',
      unit: '',
      reference_range: '',
      status: 'normal'
    },
    typeOptions: ['体格检查', '血液常规', '生化检验', '肝功能', '肾功能', '甲状腺功能', '肿瘤标志物', '尿液检查', '其他']
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ indicatorId: options.id })
      this.loadIndicator(options.id)
    }
    if (options.checkupId) {
      this.setData({ checkupId: options.checkupId })
    }
  },

  async loadIndicator(id) {
    try {
      const indicators = await api.getIndicators({ checkup_id: options.checkupId })
      const indicator = indicators.data.find(i => i.id == id)
      if (indicator) {
        this.setData({ formData: indicator })
      }
    } catch (err) {
      console.error(err)
    }
  },

  async handleSubmit() {
    const { formData, checkupId, indicatorId } = this.data

    if (!formData.indicator_name || !formData.value) {
      util.showToast('请填写必填项')
      return
    }

    try {
      if (indicatorId) {
        await api.updateIndicator(indicatorId, formData)
      } else {
        await api.createIndicator({ ...formData, checkup_id: checkupId })
      }
      util.showToast('保存成功', 'success')
      setTimeout(() => wx.navigateBack(), 1000)
    } catch (err) {
      util.showToast(err.message || '保存失败')
    }
  }
})
```

### 4. AI咨询页 (pages/ai-advice/)

**ai-advice.wxml**
```xml
<view class="advice-container">
  <!-- 快捷操作 -->
  <view class="quick-actions card">
    <view class="action-item" bindtap="startNewConversation">
      <image class="action-icon" src="/images/new-chat.png"></image>
      <text>新建对话</text>
    </view>
    <view class="action-item" bindtap="viewHistory">
      <image class="action-icon" src="/images/history.png"></image>
      <text>历史记录</text>
    </view>
  </view>

  <!-- 对话列表 -->
  <view class="conversation-list card">
    <view class="card-title">对话记录</view>
    <block wx:if="{{conversations.length > 0}}">
      <view class="conversation-item" wx:for="{{conversations}}" wx:key="id"
            bindtap="openConversation" data-id="{{item.id}}">
        <view class="conversation-header">
          <text class="title">{{item.title}}</text>
          <text class="time">{{item.updated_at}}</text>
        </view>
        <view class="conversation-preview">
          {{item.latest_question}}
        </view>
        <view class="conversation-footer">
          <text class="message-count">{{item.message_count}}条消息</text>
          <text class="delete-btn" catchtap="deleteConversation" data-id="{{item.id}}">删除</text>
        </view>
      </view>
    </block>
    <view class="empty-container" wx:else>
      <text>暂无对话记录</text>
    </view>
  </view>
</view>
```

### 5. 数据整合页 (pages/integration/)

**integration.js 核心逻辑**
```javascript
const api = require('../../utils/api.js')

Page({
  data: {
    checkups: [],
    selectedIds: [],
    integrating: false
  },

  onLoad() {
    this.loadCheckups()
  },

  async loadCheckups() {
    try {
      const res = await api.getCheckups({ page_size: 100 })
      this.setData({ checkups: res.data || [] })
    } catch (err) {
      console.error(err)
    }
  },

  toggleSelection(e) {
    const id = e.currentTarget.dataset.id
    const selectedIds = [...this.data.selectedIds]
    const index = selectedIds.indexOf(id)

    if (index > -1) {
      selectedIds.splice(index, 1)
    } else {
      selectedIds.push(id)
    }

    this.setData({ selectedIds })
  },

  async handleIntegrate() {
    if (this.data.selectedIds.length < 2) {
      util.showToast('请至少选择2份报告')
      return
    }

    this.setData({ integrating: true })

    try {
      const res = await api.integrateData({ checkup_ids: this.data.selectedIds })

      wx.navigateTo({
        url: `/pages/integration-result/integration-result?data=${encodeURIComponent(JSON.stringify(res))}`
      })
    } catch (err) {
      util.showToast(err.message || '整合失败')
    } finally {
      this.setData({ integrating: false })
    }
  }
})
```

## 配置说明

### 1. 修改服务器地址

在 `app.js` 中修改：
```javascript
globalData: {
  baseUrl: 'http://your-server-ip:8000',  // 改为你的服务器地址
  // ...
}
```

### 2. 配置AppID

在 `project.config.json` 中：
```json
{
  "appid": "your-weixin-appid"
}
```

### 3. 配置服务器域名

在微信公众平台配置合法域名：
- request域名: https://your-domain.com
- uploadFile域名: https://your-domain.com

## 功能特性

✅ 用户认证登录
✅ 体检报告上传（PDF/图片）
✅ 实时处理进度显示
✅ 健康指标查看和管理
✅ 手动添加/编辑指标
✅ AI健康咨询
✅ AI多轮对话
✅ 数据智能整合
✅ 常用医院管理
✅ 分页加载
✅ 下拉刷新

## 使用说明

1. 克隆项目到微信开发者工具
2. 修改 `app.js` 中的服务器地址
3. 配置 `project.config.json` 中的AppID
4. 点击编译运行

## 注意事项

- 确保Django服务已启动
- 确保服务器地址可访问
- 小程序需要配置合法域名
- 上传文件大小限制为10MB

## API接口说明

所有API接口已在 `utils/api.js` 中定义，参考文档：`小程序API文档.md`
