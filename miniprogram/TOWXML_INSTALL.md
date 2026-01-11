# Towxml 安装说明

## 安装步骤

### 1. 下载 towxml

方式一：直接下载（推荐）
```bash
cd miniprogram
git clone https://github.com/sbfkcel/towxml.git
```

方式二：npm安装
```bash
cd miniprogram
npm install towxml
```

### 2. 复制到项目中

如果用git clone方式，将下载的 `towxml` 文件夹复制到 `miniprogram/` 目录下：
```
miniprogram/
  ├── towxml/           # Markdown渲染组件
  ├── pages/
  ├── utils/
  └── ...
```

如果用npm方式，需要构建：
```bash
cd miniprogram
npm install towxml
# 然后在微信开发者工具中：工具 -> 构建 npm
```

### 3. 配置 app.json

在 `miniprogram/app.json` 中添加towxml的引用（如果使用npm方式）：
```json
{
  "usingComponents": {
    "towxml": "/towxml/towxml"
  }
}
```

### 4. 功能特性

towxml支持：
- ✅ Markdown完整语法
- ✅ 代码高亮（支持多种编程语言）
- ✅ 表格渲染
- ✅ 数学公式
- ✅ 任务列表
- ✅ 引用块
- ✅ 图片和链接
- ✅ 自定义主题

### 5. 使用示例

在页面中：
```xml
<towxml nodes="{{markdownData}}" />
```

在JS中：
```javascript
const Towxml = require('../../towxml')

Page({
  data: {
    markdownData: {}
  },
  loadMarkdown() {
    const result = Towxml('# Hello Markdown\n\n```js\nconsole.log("code")\n```', 'markdown')
    this.setData({ markdownData: result })
  }
})
```

## 主题配置

支持浅色和深色主题，默认根据系统自动切换。

## 注意事项

1. towxml会自动处理代码高亮、表格等复杂格式
2. 图片需要配置域名白名单
3. 支持自定义主题颜色
