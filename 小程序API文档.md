# 健康管理系统 - 微信小程序API文档

## 基础信息

- **API基础路径**: `/api/miniprogram/`
- **认证方式**: Token认证 (通过登录获取)
- **数据格式**: JSON
- **字符编码**: UTF-8

## 目录

1. [用户认证](#用户认证)
2. [体检报告管理](#体检报告管理)
3. [健康指标管理](#健康指标管理)
4. [AI健康建议](#ai健康建议)
5. [AI对话功能](#ai对话功能)
6. [数据整合](#数据整合)
7. [系统信息](#系统信息)

---

## 用户认证

### 1.1 用户登录

**接口**: `POST /api/miniprogram/login/`

**说明**: 支持微信小程序登录和用户名密码登录（测试用）

**请求参数**:
```json
{
  "code": "微信登录code",  // 可选
  "openid": "微信openid",  // 可选
  "nickname": "微信昵称",  // 可选
  "username": "用户名",    // 可选
  "password": "密码"       // 可选
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "登录成功",
  "user": {
    "id": 1,
    "username": "wx_user",
    "first_name": "微信用户"
  },
  "token": "1"
}
```

### 1.2 获取用户信息

**接口**: `GET /api/miniprogram/user-info/`

**说明**: 获取当前登录用户的信息

**请求头**:
```
Authorization: Bearer {token}
```

**响应示例**:
```json
{
  "success": true,
  "user": {
    "id": 1,
    "username": "test_user",
    "email": "user@example.com",
    "first_name": "测试"
  }
}
```

---

## 体检报告管理

### 2.1 上传体检报告

**接口**: `POST /api/miniprogram/upload/`

**说明**: 上传体检报告PDF或图片文件，系统自动OCR识别和AI分析

**请求参数**: (multipart/form-data)
- `file`: 文件 (必填)
- `checkup_date`: 体检日期，格式YYYY-MM-DD (可选)
- `hospital`: 体检机构名称 (可选)
- `department`: 科室 (可选)
- `workflow_type`: 工作流类型 (可选，默认vl_model)
  - `vl_model`: 多模态大模型模式
  - `mineru_pipeline`: MinerU Pipeline模式
  - `mineru_vlm`: MinerU VLM模式

**响应示例**:
```json
{
  "success": true,
  "message": "上传成功，正在处理...",
  "processing_id": 123,
  "checkup_id": 456
}
```

### 2.2 获取处理状态

**接口**: `GET /api/miniprogram/processing-status/{processing_id}/`

**说明**: 查看报告处理进度

**响应示例**:
```json
{
  "success": true,
  "status": "completed",
  "progress": 100,
  "indicators_count": 45,
  "has_ai_result": true,
  "ai_indicators_count": 42,
  "error_message": null
}
```

**状态值**:
- `pending`: 等待处理
- `uploading`: 上传中
- `ocr_processing`: OCR识别中
- `ai_processing`: AI分析中
- `saving_data`: 保存数据中
- `completed`: 处理完成
- `failed`: 处理失败

### 2.3 获取体检记录列表

**接口**: `GET /api/miniprogram/checkups/`

**查询参数**:
- `page`: 页码 (默认1)
- `page_size`: 每页数量 (默认10)

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "checkup_date": "2024-01-15",
      "hospital": "北京协和医院",
      "department": "体检科",
      "status": "completed",
      "indicators_count": 45,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 25,
  "page": 1,
  "page_size": 10,
  "has_more": true
}
```

### 2.4 获取体检记录详情

**接口**: `GET /api/miniprogram/checkups/{checkup_id}/`

**响应示例**:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "checkup_date": "2024-01-15",
    "hospital": "北京协和医院",
    "department": "体检科",
    "status": "completed",
    "indicators_count": 45,
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T11:00:00Z"
  }
}
```

### 2.5 删除体检报告

**接口**: `DELETE /api/miniprogram/checkups/{checkup_id}/delete/`

**响应示例**:
```json
{
  "success": true,
  "message": "体检报告已删除"
}
```

---

## 健康指标管理

### 3.1 获取健康指标列表

**接口**: `GET /api/miniprogram/indicators/`

**查询参数**:
- `checkup_id`: 体检报告ID (可选，不传则返回所有指标)
- `page`: 页码 (默认1)
- `page_size`: 每页数量 (默认50)

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "indicator_name": "血红蛋白",
      "value": "135",
      "unit": "g/L",
      "reference_range": "110-150",
      "status": "normal",
      "indicator_type": "blood_routine"
    }
  ],
  "total": 120,
  "page": 1,
  "page_size": 50,
  "has_more": true
}
```

### 3.2 获取特定报告的指标

**接口**: `GET /api/miniprogram/checkups/{checkup_id}/indicators/`

**说明**: 同3.1，但路径参数指定体检报告

### 3.3 手动创建健康指标

**接口**: `POST /api/miniprogram/indicators/create/`

**请求参数**:
```json
{
  "checkup_id": 1,
  "indicator_type": "blood_routine",
  "indicator_name": "白细胞计数",
  "value": "6.5",
  "unit": "10^9/L",
  "reference_range": "3.5-9.5",
  "status": "normal"
}
```

**indicator_type 可选值**:
- `physical_exam`: 体格检查
- `blood_routine`: 血液常规
- `biochemistry`: 生化检验
- `liver_function`: 肝功能
- `kidney_function`: 肾功能
- `thyroid_function`: 甲状腺功能
- `tumor_markers`: 肿瘤标志物
- `urine_exam`: 尿液检查
- `other_exam`: 其他检查

**status 可选值**:
- `normal`: 正常
- `abnormal`: 异常
- `attention`: 关注

**响应示例**:
```json
{
  "success": true,
  "message": "指标添加成功",
  "data": {
    "id": 121,
    "indicator_name": "白细胞计数",
    "value": "6.5",
    "unit": "10^9/L"
  }
}
```

### 3.4 更新健康指标

**接口**: `PUT/PATCH /api/miniprogram/indicators/{indicator_id}/update/`

**请求参数**:
```json
{
  "indicator_name": "白细胞计数",
  "value": "7.0",
  "unit": "10^9/L",
  "reference_range": "3.5-9.5",
  "status": "normal"
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "指标更新成功",
  "data": {...}
}
```

### 3.5 删除健康指标

**接口**: `DELETE /api/miniprogram/indicators/{indicator_id}/delete/`

**响应示例**:
```json
{
  "success": true,
  "message": "指标已删除"
}
```

---

## AI健康建议

### 4.1 获取AI健康建议

**接口**: `POST /api/miniprogram/advice/`

**说明**: 基于体检报告获取AI健康分析和建议

**请求参数**:
```json
{
  "checkup_id": 1
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "AI建议生成成功",
  "data": {
    "id": 10,
    "question": "请分析我的体检报告",
    "answer": "根据您的体检报告，总体健康状况良好...",
    "created_at": "2024-01-15T12:00:00Z"
  }
}
```

---

## AI对话功能

### 5.1 获取对话列表

**接口**: `GET /api/miniprogram/conversations/`

**说明**: 获取用户的所有AI健康咨询对话

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "id": 5,
      "title": "关于血压的咨询",
      "created_at": "2024-01-15T14:00:00Z",
      "updated_at": "2024-01-15T15:30:00Z",
      "message_count": 5,
      "latest_question": "我的血压偏高怎么办？"
    }
  ],
  "total": 3
}
```

### 5.2 创建新对话

**接口**: `POST /api/miniprogram/conversations/create/`

**请求参数**:
```json
{
  "title": "关于血糖的咨询"
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "对话创建成功",
  "data": {
    "id": 6,
    "title": "关于血糖的咨询",
    "created_at": "2024-01-15T16:00:00Z"
  }
}
```

### 5.3 获取对话详情

**接口**: `GET /api/miniprogram/conversations/{conversation_id}/`

**说明**: 获取对话的所有消息历史

**响应示例**:
```json
{
  "success": true,
  "data": {
    "id": 5,
    "title": "关于血压的咨询",
    "created_at": "2024-01-15T14:00:00Z",
    "updated_at": "2024-01-15T15:30:00Z",
    "messages": [
      {
        "id": 101,
        "question": "我的血压偏高怎么办？",
        "answer": "血压偏高需要注意以下几点...",
        "created_at": "2024-01-15T14:05:00Z"
      }
    ],
    "message_count": 5
  }
}
```

### 5.4 删除对话

**接口**: `DELETE /api/miniprogram/conversations/{conversation_id}/delete/`

**响应示例**:
```json
{
  "success": true,
  "message": "对话已删除"
}
```

---

## 数据整合

### 6.1 AI智能数据整合

**接口**: `POST /api/miniprogram/integrate-data/`

**说明**: 选择多份体检报告，AI自动统一指标名称、单位等信息

**请求参数**:
```json
{
  "checkup_ids": [1, 2, 3]
}
```

**响应示例**:
```json
{
  "success": true,
  "total_indicators": 135,
  "unique_groups": 42,
  "changed_count": 15,
  "unchanged_count": 120,
  "changes": [
    {
      "indicator_id": 123,
      "original": {
        "indicator_name": "身长",
        "value": "175",
        "unit": "cm"
      },
      "changes": {
        "indicator_name": "身高"
      }
    }
  ],
  "all_indicators": [...]
}
```

---

## 系统信息

### 7.1 获取服务状态

**接口**: `GET /api/miniprogram/services-status/`

**说明**: 检查系统各个AI服务的可用性

**响应示例**:
```json
{
  "success": true,
  "services": [
    {
      "name": "ocr",
      "status": "healthy",
      "api_url": "http://localhost:8000"
    },
    {
      "name": "llm",
      "status": "healthy",
      "api_url": "https://api.siliconflow.cn/v1/chat/completions"
    }
  ],
  "default_workflow": "vl_model"
}
```

### 7.2 获取系统设置

**接口**: `GET /api/miniprogram/system-settings/`

**说明**: 获取系统配置信息（用于小程序显示配置状态）

**响应示例**:
```json
{
  "success": true,
  "settings": {
    "mineru_api_url": "http://localhost:8000",
    "llm_api_url": "https://api.siliconflow.cn/v1/chat/completions",
    "llm_model_name": "deepseek-ai/DeepSeek-V3.2",
    "vl_model_api_url": "https://api.siliconflow.cn/v1/chat/completions",
    "vl_model_name": "zai-org/GLM-4.6V",
    "default_workflow": "vl_model",
    "ai_model_timeout": "300"
  }
}
```

### 7.3 获取常用医院

**接口**: `GET /api/miniprogram/hospitals/common/`

**说明**: 获取用户历史使用过的体检机构列表，按使用频率排序

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "name": "北京协和医院",
      "usage_count": 5,
      "last_used": "2024-01-15"
    },
    {
      "name": "301医院",
      "usage_count": 3,
      "last_used": "2023-12-10"
    }
  ],
  "total": 10
}
```

---

## 通用响应格式

### 成功响应
```json
{
  "success": true,
  "data": {...},
  "message": "操作成功"
}
```

### 错误响应
```json
{
  "success": false,
  "message": "错误描述"
}
```

### HTTP状态码
- `200`: 成功
- `201`: 创建成功
- `400`: 请求参数错误
- `401`: 未授权
- `403`: 禁止访问
- `404`: 资源不存在
- `500`: 服务器内部错误

---

## 注意事项

1. **认证Token**: 大部分接口需要在请求头中携带 `Authorization: Bearer {token}`
2. **文件上传**: 上传接口使用 multipart/form-data 格式
3. **分页参数**: 所有列表接口都支持分页，建议合理设置page_size避免数据量过大
4. **后台处理**: 文件上传后是异步处理，需要通过 processing_status 接口轮询处理进度
5. **错误处理**: 所有接口都有统一的错误处理机制，请根据返回的success字段判断是否成功

---

## 更新日志

### v1.0.0 (2024-01-15)
- ✅ 用户认证功能
- ✅ 体检报告上传和处理
- ✅ 健康指标查询和管理
- ✅ AI健康建议
- ✅ AI多轮对话
- ✅ 数据整合功能
- ✅ 系统状态查询
