# TabBar 图标说明

## 图标尺寸要求

- **大小**: 81px * 81px（推荐）或 40px * 40px
- **格式**: PNG
- **模式**: 必须是透明背景
- **颜色**: 普通状态用灰色，选中状态用蓝色

## 所需图标文件

在 `miniprogram/images/tab/` 目录下创建以下图标：

### 1. 首页图标
- `home.png` - 未选中状态（灰色）
- `home-active.png` - 选中状态（蓝色）

### 2. 报告图标
- `report.png` - 未选中状态（灰色）
- `report-active.png` - 选中状态（蓝色）

### 3. 上传图标
- `upload.png` - 未选中状态（灰色）
- `upload-active.png` - 选中状态（蓝色）

### 4. AI咨询图标
- `ai.png` - 未选中状态（灰色）
- `ai-active.png` - 选中状态（蓝色）

### 5. 我的图标
- `me.png` - 未选中状态（灰色）
- `me-active.png` - 选中状态（蓝色）

## 图标推荐

可以使用以下图标库：
- Iconfont (https://www.iconfont.cn/)
- 阿里巴巴图标库
- 自行设计简约图标

## 添加步骤

1. 创建目录：`miniprogram/images/tab/`
2. 准备10个图标文件（5个普通 + 5个选中）
3. 放入对应目录
4. 取消 `app.json` 中iconPath的注释

## 快速测试

当前配置可以正常使用，只显示文字标签。添加图标后，app.json会自动启用图标显示。
