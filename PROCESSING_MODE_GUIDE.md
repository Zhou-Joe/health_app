# AI处理模式使用说明

## 📊 两种处理模式

### 1. 实时模式 (Stream)
- **特点**：流式响应，实时看到AI生成过程
- **优点**：
  - ✅ 可以看到AI逐步输出的过程
  - ✅ 体验流畅，即时反馈
- **缺点**：
  - ❌ 必须保持页面打开
  - ❌ 手机熄屏会中断
  - ❌ 不适合长时间处理
- **适合**：PC用户，想看实时输出过程的用户

### 2. 后台模式 (Background)
- **特点**：异步任务，在服务器后台处理
- **优点**：
  - ✅ 可以离开页面或关闭手机
  - ✅ 任务持续运行不受影响
  - ✅ 完成后回来查看结果
  - ✅ 适合长时间处理
- **缺点**：
  - ❌ 看不到实时生成过程
  - ❌ 需要轮询任务状态
- **适合**：手机用户，长时间处理，想离开页面的用户

---

## 🔧 API使用方法

### 1. 获取当前模式

```javascript
// 获取当前用户的AI处理模式
const response = await fetch('/health/api/processing-mode/');
const data = await response.json();

console.log(data.mode);           // 'stream' 或 'background'
console.log(data.mode_display);   // '实时模式' 或 '后台模式'
console.log(data.description);    // 模式说明
```

**返回示例：**
```json
{
  "mode": "background",
  "mode_display": "后台模式",
  "description": "可以在后台处理，完成后查看结果，适合手机用户"
}
```

### 2. 设置处理模式

```javascript
// 切换到实时模式
await fetch('/health/api/processing-mode/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCookie('csrftoken')
  },
  body: JSON.stringify({
    mode: 'stream'  // 或 'background'
  })
});
```

---

## 💡 前端集成示例

### 在上传页面添加模式选择器

```html
<!-- 在表单中添加模式选择 -->
<div class="mb-3">
  <label class="form-label">
    <i class="bi bi-gear"></i> AI处理模式
  </label>
  <select class="form-select" id="processingMode">
    <option value="background">后台模式（推荐）- 可离开页面</option>
    <option value="stream">实时模式 - 需保持页面打开</option>
  </select>
  <small class="form-text text-muted">
    后台模式：上传后可以关闭页面，完成后查看结果。适合手机用户。
  </small>
</div>
```

```javascript
// 页面加载时获取当前模式
async function initProcessingMode() {
  const response = await fetch('/health/api/processing-mode/');
  const data = await response.json();
  document.getElementById('processingMode').value = data.mode;
}

// 上传时根据模式选择API
async function uploadFile() {
  const mode = document.getElementById('processingMode').value;

  if (mode === 'stream') {
    // 使用流式API
    const response = await fetch('/health/api/stream-upload/', {...});
    // 处理流式响应...
  } else {
    // 使用后台任务API
    const response = await fetch('/health/api/task/create/', {...});
    const {task_id} = await response.json();

    // 开始轮询任务状态
    pollTaskStatus(task_id);
  }
}

// 轮询任务状态
async function pollTaskStatus(taskId) {
  const interval = setInterval(async () => {
    const response = await fetch(`/health/api/task/${taskId}/status/`);
    const task = await response.json();

    // 更新进度
    updateProgress(task.progress, task.message);

    if (task.status === 'completed') {
      clearInterval(interval);
      showResult(task.result);
      alert('处理完成！');
    } else if (task.status === 'failed') {
      clearInterval(interval);
      showError(task.error);
    }
  }, 3000);
}
```

---

## 📱 移动端建议

### 检测设备类型自动选择模式

```javascript
// 检测是否为移动设备
function isMobile() {
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

// 根据设备类型设置默认模式
async function setDefaultMode() {
  const response = await fetch('/health/api/processing-mode/');
  const data = await response.json();

  // 如果是移动设备且当前是实时模式，自动切换到后台模式
  if (isMobile() && data.mode === 'stream') {
    await fetch('/health/api/processing-mode/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
      },
      body: JSON.stringify({ mode: 'background' })
    });
    console.log('已自动切换到后台模式');
  }
}

// 页面加载时执行
setDefaultMode();
```

---

## 🎯 系统设置页面集成

在系统设置页面添加模式选择UI：

```html
<div class="card">
  <div class="card-header">
    <h5>AI处理设置</h5>
  </div>
  <div class="card-body">
    <div class="mb-3">
      <label class="form-label">处理模式</label>
      <select class="form-select" id="processingModeSelect">
        <option value="stream">实时模式</option>
        <option value="background">后台模式（推荐）</option>
      </select>
      <div class="form-text">
        <strong>实时模式</strong>：可以看到AI生成的实时过程，但需要保持页面打开<br>
        <strong>后台模式</strong>：可以在后台处理，完成后查看结果，适合手机用户
      </div>
    </div>
    <button class="btn btn-primary" onclick="saveProcessingMode()">保存设置</button>
  </div>
</div>

<script>
async function loadProcessingMode() {
  const response = await fetch('/health/api/processing-mode/');
  const data = await response.json();
  document.getElementById('processingModeSelect').value = data.mode;
}

async function saveProcessingMode() {
  const mode = document.getElementById('processingModeSelect').value;

  const response = await fetch('/health/api/processing-mode/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({ mode })
  });

  const data = await response.json();
  alert(data.message);
}

// 页面加载时获取当前设置
loadProcessingMode();
</script>
```

---

## 🚀 部署步骤

### 1. 阿里云执行迁移

```bash
cd /home/ubuntu/health
source venv/bin/activate
python manage.py migrate
```

### 2. 重启服务

```bash
sudo systemctl restart health-project
```

### 3. 验证功能

```bash
# 测试API
curl https://www.zctestbench.asia/api/processing-mode/
```

---

## 📊 数据库说明

**迁移文件：** `medical_records/migrations/0002_add_processing_mode.py`

**字段定义：**
```python
processing_mode = models.CharField(
    max_length=20,
    choices=[
        ('stream', '实时模式'),
        ('background', '后台模式')
    ],
    default='background'  # 默认后台模式
)
```

**位置：** `UserProfile` 模型

**默认值：** 所有用户默认使用后台模式

---

## 💡 使用建议

### 手机用户
- ✅ 使用**后台模式**
- ✅ 上传后可以锁屏或切换应用
- ✅ 完成后查看结果

### PC用户
- ✅ 使用**实时模式**
- ✅ 观看AI分析和生成过程
- ✅ 更好的交互体验

### 长时间处理任务
- ✅ 使用**后台模式**
- ✅ 避免浏览器超时
- ✅ 不占用用户时间

---

## 🔄 切换模式

用户可以随时在系统设置中切换模式：

1. 进入系统设置页面
2. 找到"AI处理设置"
3. 选择"实时模式"或"后台模式"
4. 保存设置

下次上传或使用AI功能时会自动使用新模式。

---

**现在用户可以根据自己的使用场景选择最合适的处理方式了！** ✅
