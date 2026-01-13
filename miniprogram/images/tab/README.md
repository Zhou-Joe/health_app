# TabBar 图标说明

本目录已包含完整的SVG图标设计，可直接使用或转换为PNG格式。

## 当前图标列表

| 功能 | SVG图标 | 用途 |
|------|---------|------|
| 🏠 首页 | home.svg / home-active.svg | 仪表盘首页 |
| 📄 报告 | report.svg / report-active.svg | 体检报告列表 |
| ⬆️ 上传 | upload.svg / upload-active.svg | 上传体检报告 |
| 🤖 AI咨询 | ai.svg / ai-active.svg | AI健康咨询 |
| 👤 我的 | user.svg / user-active.svg | 个人中心 |

## SVG 转 PNG 说明

**注意**：微信小程序 tabBar 不支持 SVG，需要转换为 PNG。

### 快速转换方法

#### 方法1：在线转换（推荐）
1. 访问 https://convertio.co/zh/svg-png/
2. 批量上传本目录的 SVG 文件
3. 设置尺寸：81x81 像素
4. 勾选"透明背景"
5. 下载并替换到本目录

#### 方法2：Figma/Sketch
1. 用 Figma 打开 SVG 文件
2. 导出为 PNG，81x81px，@3x
3. 保存到同一目录

#### 方法3：命令行 (ImageMagick)
```bash
cd miniprogram/images/tab
for file in *.svg; do
  convert -background none -resize 81x81 "$file" "${file%.svg}.png"
done
```

## 转换后的文件列表

转换完成后，应该有以下10个PNG文件：

```
home.png, home-active.png
report.png, report-active.png
upload.png, upload-active.png
ai.png, ai-active.png
user.png, user-active.png
```

## app.json 配置

转换完成后，在 `app.json` 中添加 iconPath：

```json
{
  "tabBar": {
    "color": "#666666",
    "selectedColor": "#4A90E2",
    "list": [
      {
        "pagePath": "pages/dashboard/dashboard",
        "text": "首页",
        "iconPath": "images/tab/home.png",
        "selectedIconPath": "images/tab/home-active.png"
      }
      // ... 其他项同理
    ]
  }
}
```

## 设计规范

- **尺寸**：81x81px (@3x) 或 54x54px (@2x)
- **颜色**：
  - 未选中：#666666
  - 选中：#4A90E2
- **格式**：PNG，透明背景
- **大小**：每个图标 ≤ 40kb

