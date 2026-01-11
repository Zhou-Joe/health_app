# 小程序 Markdown 渲染功能使用指南

## 功能说明

AI对话页面现在支持完整的Markdown渲染和代码高亮显示，包括：

- ✅ **标题** - H1, H2, H3 等各级标题
- ✅ **代码高亮** - 支持多种编程语言的语法高亮
- ✅ **粗体斜体** - **粗体** 和 *斜体*
- ✅ **列表** - 有序列表和无序列表
- ✅ **引用块** - 带左边距的引用样式
- ✅ **表格** - Markdown表格渲染
- ✅ **链接** - 自动识别和显示链接

## 安装步骤

### 1. 安装 towxml 库

在项目根目录执行：

```bash
cd miniprogram
git clone https://github.com/sbfkcel/towxml.git
```

或使用npm（推荐）：

```bash
cd miniprogram
npm install towxml
```

### 2. 如果使用npm安装

在微信开发者工具中：
1. 点击菜单 **工具** → **构建 npm**
2. 等待构建完成

### 3. 验证安装

确保以下目录存在：
- `miniprogram/towxml/` （git clone方式）
- `miniprogram/miniprogram_npm/towxml/` （npm方式）

## 已配置的文件

以下文件已自动配置好Markdown渲染功能：

1. **miniprogram/pages/conversation/conversation.json**
   - 已引入towxml组件

2. **miniprogram/pages/conversation/conversation.js**
   - 添加了Markdown转换函数
   - 自动转换AI回复为渲染格式

3. **miniprogram/pages/conversation/conversation.wxml**
   - 使用towxml组件渲染Markdown
   - 保留纯文本作为降级方案

4. **miniprogram/pages/conversation/conversation.wxss**
   - 添加了完整的Markdown样式
   - 代码高亮使用One Dark主题

## 代码高亮示例

AI回复中的代码块会被自动高亮，例如：

```javascript
function hello() {
  console.log("Hello, World!");
}
```

会显示为带语法高亮的深色背景代码块。

## 主题配色

代码高亮采用 **One Dark** 主题：
- 关键字: 紫色 (#C678DD)
- 字符串: 绿色 (#98C379)
- 数字: 橙色 (#D19A66)
- 注释: 灰色斜体 (#5C6370)
- 函数: 蓝色 (#61AFEF)
- 代码块背景: 深灰 (#282C34)

## 降级方案

如果towxml未安装或加载失败，会自动降级为纯文本显示，不影响基本功能。

## 测试建议

1. 启动小程序后，进入AI对话页面
2. 发送包含代码的问题，如："如何用Python计算BMI？"
3. AI回复中的代码会自动高亮显示
4. 尝试发送其他Markdown格式的内容

## 常见问题

**Q: 为什么没有看到代码高亮？**
A: 确保已正确安装towxml库。检查控制台是否有错误信息。

**Q: 代码块显示不正常？**
A: 清除小程序缓存，重新编译。在微信开发者工具中：清缓存 → 全部清除。

**Q: 支持深色模式吗？**
A: 当前使用浅色主题，可以通过修改 `convertMarkdown` 函数的 `theme` 参数为 `'dark'` 来切换。

## 自定义配置

如需调整样式，编辑 `conversation.wxss` 中的 `.ai-bubble >>> .towxml*` 相关样式。

如需切换主题，编辑 `conversation.js` 中的 `convertMarkdown` 函数：

```javascript
const result = Towxml(content, 'markdown', {
  base: '',
  theme: 'dark'  // 改为 'dark' 启用深色主题
})
```
