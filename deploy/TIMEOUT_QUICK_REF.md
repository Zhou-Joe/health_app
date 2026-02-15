# 超时配置快速参考卡

## ⏱️ 超时时间层级关系

```
┌─────────────────────────────────────────────────────┐
│ 超时时间递增（每个环节都要大于上一个）         │
├─────────────────────────────────────────────────────┤
│ 1. Django心跳: 10秒                             │
│    └─> 作用：保持SSE连接活跃                   │
│                                                  │
│ 2. Django OCR超时: 300秒 (5分钟)               │
│    └─> 位置: SystemSettings.ocr_timeout          │
│                                                  │
│ 3. Nginx超时: 600秒 (10分钟)                   │
│    └─> 位置: nginx.conf proxy_read_timeout      │
│                                                  │
│ 4. Gunicorn超时: 900秒 (15分钟)                │
│    └─> 位置: gunicorn.conf.py timeout           │
└─────────────────────────────────────────────────────┘
```

## 🔧 必须配置的3个地方

### 1️⃣ Django系统设置（Web界面）
访问：http://your-domain.com/settings

```
OCR超时设置: 300 (秒)
OCR健康检查超时: 20 (秒)
```

### 2️⃣ Nginx配置
文件：/etc/nginx/sites-available/health_app

```nginx
location /api/stream-upload/ {
    proxy_read_timeout 600s;    # ← 关键！
    proxy_send_timeout 600s;

    proxy_buffering off;          # ← 关键！
    proxy_http_version 1.1;       # ← 关键！
}
```

### 3️⃣ Gunicorn配置
文件：/path/to/health_app/deploy/gunicorn.conf.py

```python
timeout = 900                  # ← 关键！
worker_class = 'sync'          # ← 关键！
```

## 🚀 快速部署命令

```bash
# 1. 复制配置文件
sudo cp deploy/nginx.conf /etc/nginx/sites-available/health_app
sudo ln -s /etc/nginx/sites-available/health_app /etc/nginx/sites-enabled/

# 2. 修改配置文件
sudo nano /etc/nginx/sites-available/health_app
# 修改: server_name, 静态文件路径

# 3. 测试Nginx
sudo nginx -t

# 4. 启动Gunicorn
cd /path/to/health_app
gunicorn -c deploy/gunicorn.conf.py health_report.wsgi:application &

# 5. 重载Nginx
sudo systemctl reload nginx

# 6. 测试
curl -N http://your-domain.com/api/stream-upload/
```

## 🧪 验证清单

```bash
# ✅ 1. 检查Gunicorn运行
ps aux | grep gunicorn

# ✅ 2. 检查端口监听
netstat -tlnp | grep 8000

# ✅ 3. 检查Nginx配置
sudo nginx -t

# ✅ 4. 检查心跳日志
tail -f /var/log/gunicorn/health_app_error.log | grep "发送心跳"

# ✅ 5. 测试SSE连接
curl -N http://localhost/api/stream-upload/
```

## 🚨 常见错误速查

| 错误信息 | 原因 | 解决方案 |
|---------|------|---------|
| `upstream timed out` | Nginx超时太小 | 增大 `proxy_read_timeout` |
| `WORKER TIMEOUT` | Gunicorn超时太小 | 增大 `timeout` |
| `Failed to fetch` | 客户端超时 | 检查浏览器控制台，增加服务器超时 |
| `502 Bad Gateway` | Gunicorn未运行 | `sudo supervisorctl start health_app` |
| `Connection lost` | SSE被缓冲 | 设置 `proxy_buffering off` |

## 📝 配置文件位置速查

```
项目根目录/
├── deploy/
│   ├── nginx.conf              → /etc/nginx/sites-available/health_app
│   ├── gunicorn.conf.py        → 项目中使用
│   ├── supervisor.conf         → /etc/supervisor/conf.d/health_app.conf
│   └── DEPLOYMENT_GUIDE.md     → 完整部署指南
```

## 🔄 服务重启顺序

```bash
# 遇到问题时按此顺序重启

# 1. Gunicorn (先停后启)
sudo supervisorctl restart health_app

# 2. Nginx (平滑重载)
sudo systemctl reload nginx

# 3. Supervisor (如果修改了配置)
sudo supervisorctl reread
sudo supervisorctl update
```

## 📊 日志文件位置

```bash
# Nginx日志
tail -f /var/log/nginx/health_app_error.log
tail -f /var/log/nginx/health_app_access.log

# Gunicorn日志
tail -f /var/log/gunicorn/health_app_error.log
tail -f /var/log/gunicorn/health_app_access.log

# Supervisor日志
tail -f /var/log/supervisor/health_app_stderr.log
tail -f /var/log/supervisor/health_app_stdout.log

# Django日志（如果在settings.py中配置）
tail -f /path/to/health_app/logs/django.log
```

---

**记住这个黄金法则**：
> Django心跳 < Django超时 < Nginx超时 < Gunicorn超时

**如果出现超时**：
1. 先检查心跳是否在发送（查看Django日志）
2. 再检查Nginx配置（`proxy_buffering off`）
3. 最后检查Gunicorn配置（`timeout`足够大）
