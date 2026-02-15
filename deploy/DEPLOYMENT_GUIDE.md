# 云端部署配置指南 - Gunicorn + Nginx

## ⚠️ 为什么必须配置Gunicorn和Nginx？

### 之前的超时问题
```
浏览器 --nginx--> gunicorn --> Django OCR
                    ↑
                    |---- 超时断开 ---|
```

**原因**：
- Nginx默认超时：60秒
- Gunicorn默认超时：30秒
- OCR处理：2-5分钟

**解决方案**：
1. ✅ Django中添加心跳机制（已完成）
2. ✅ Nginx配置SSE长连接支持
3. ✅ Gunicorn配置增加超时时间

---

## 📋 部署清单

### 1. Nginx配置

#### 配置文件位置
```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/health_app
sudo ln -s /etc/nginx/sites-available/health_app /etc/nginx/sites-enabled/health_app
```

#### 必须修改的参数
```nginx
server_name your-domain.com;  # 改为你的域名

# 静态文件路径
alias /path/to/health_app/health_report/static/;
alias /path/to/health_app/health_report/media/;
```

#### 关键配置说明

**SSE超时配置（最重要！）**：
```nginx
location /api/stream-upload/ {
    proxy_read_timeout 600s;  # ⚠️ 必须 >= OCR处理时间
    proxy_send_timeout 600s;

    proxy_buffering off;        # ⚠️ 禁用缓冲
    proxy_cache off;

    proxy_http_version 1.1;      # ⚠️ 启用HTTP/1.1
    proxy_set_header Connection "";
}
```

**参数说明**：
- `proxy_read_timeout`: 从后端读取响应的最大时间
  - 默认60秒 → 改为600秒（10分钟）
  - 必须 >= Django OCR超时 + 心跳间隔

- `proxy_buffering off`: 禁用缓冲
  - SSE需要实时推送，不能缓冲

- `proxy_http_version 1.1`: HTTP/1.1支持keep-alive

#### 测试配置
```bash
sudo nginx -t
```

#### 重启Nginx
```bash
sudo systemctl reload nginx
# 或
sudo service nginx reload
```

---

### 2. Gunicorn配置

#### 配置文件位置
```bash
cp deploy/gunicorn.conf.py /path/to/health_app/
```

#### 必须修改的参数
```python
chdir = '/path/to/health_app'  # 改为项目路径
raw_env = [
    'PYTHONPATH=/path/to/health_app',
]
```

#### 关键配置说明

**超时配置（最重要！）**：
```python
timeout = 900  # ⚠️ 必须 > nginx proxy_read_timeout
```

**参数说明**：
- `timeout`: Worker处理请求的最大时间
  - 默认30秒 → 改为900秒（15分钟）
  - 必须 > nginx的proxy_read_timeout（建议多50%）
  - 建议：nginx 600s，gunicorn 900s

- `worker_class = 'sync'`: 使用同步worker
  - SSE需要长连接，必须用sync
  - 不能用gevent/async

- `workers = 3`: Worker进程数
  - 建议公式：(2 × CPU核心数) + 1
  - 或更保守：CPU核心数

#### 安装Gunicorn
```bash
# 使用虚拟环境
source venv/bin/activate
pip install gunicorn

# 或系统级安装
sudo pip install gunicorn
```

#### 测试Gunicorn
```bash
# 前台运行测试
cd /path/to/health_app
gunicorn -c deploy/gunicorn.conf.py health_report.wsgi:application
```

---

### 3. Supervisor配置（可选但推荐）

#### 配置文件位置
```bash
sudo cp deploy/supervisor.conf /etc/supervisor/conf.d/health_app.conf
```

#### 必须修改的参数
```ini
[program:health_app]
directory=/path/to/health_app
command=/path/to/venv/bin/gunicorn -c /path/to/deploy/gunicorn.conf.py health_report.wsgi:application
environment=
    PYTHONPATH="/path/to/health_app"
```

#### 启动服务
```bash
# 重新加载配置
sudo supervisorctl reread
sudo supervisorctl update

# 启动服务
sudo supervisorctl start health_app

# 查看状态
sudo supervisorctl status health_app

# 查看日志
sudo supervisorctl tail -f health_app
```

---

## 🔍 超时时间关系图

```
客户端请求
    ↓
Nginx proxy_read_timeout: 600s ──┐
    ↓                          │
Gunicorn timeout: 900s ────────┼──→ 递增关系（每个环节都要更大）
    ↓                          │
Django OCR超时: 300s ─────────┘
    ↓
Django心跳: 每10秒
```

**配置原则**：
1. **Django心跳间隔**（10秒）< **Django OCR超时**（300秒）
2. **Django OCR超时**（300秒）< **Nginx超时**（600秒）
3. **Nginx超时**（600秒）< **Gunicorn超时**（900秒）

---

## 🧪 测试验证

### 1. 测试SSE连接
```bash
# 使用curl测试SSE
curl -N http://your-domain.com/api/stream-upload/

# 应该看到：
# data: {"status": "...", "message": "..."}
# (持续输出，不会断开)
```

### 2. 测试OCR上传
1. 访问智能上传页面
2. 上传一个较大的PDF（需要2-3分钟处理）
3. 观察日志：
   ```bash
   # Django日志
   tail -f /var/log/gunicorn/health_app_error.log

   # 应该看到：
   [流式上传] 发送心跳 #1, 已等待 10秒
   [流式上传] 发送心跳 #2, 已等待 20秒
   [流式上传] 发送心跳 #3, 已等待 30秒
   ```

### 3. 检查超时是否生效
```bash
# Nginx日志
tail -f /var/log/nginx/health_app_error.log

# 如果出现：
# upstream timed out (110: Connection timed out) while reading response
# 说明nginx超时设置太小

# Gunicorn日志
tail -f /var/log/gunicorn/health_app_error.log

# 如果出现：
# [CRITICAL] WORKER TIMEOUT
# 说明gunicorn超时设置太小
```

---

## 🚨 常见问题排查

### 问题1: 仍然出现 "Failed to load resource"

**检查清单**：
```bash
# 1. 确认nginx已重载
sudo nginx -t && sudo systemctl reload nginx

# 2. 确认gunicorn超时配置生效
ps aux | grep gunicorn
# 查看进程参数中是否有 -c gunicorn.conf.py

# 3. 检查心跳是否发送
grep "发送心跳" /var/log/gunicorn/health_app_error.log

# 4. 测试网络连接
curl -v http://localhost:8000/api/check-services/
```

### 问题2: Nginx 502 Bad Gateway

**原因**：Gunicorn未启动或配置错误

**解决**：
```bash
# 检查gunicorn是否运行
ps aux | grep gunicorn

# 检查端口是否监听
netstat -tlnp | grep 8000

# 手动启动测试
gunicorn -c deploy/gunicorn.conf.py health_report.wsgi:application
```

### 问题3: SSE连接断开但无错误日志

**原因**：可能是客户端超时

**解决**：检查浏览器控制台，可能需要在fetch中添加超时配置

---

## 📊 性能调优建议

### 1. Worker数量调整
```python
# CPU密集型（OCR计算）
workers = (2 * CPU核心数) + 1

# IO密集型（等待外部API）
workers = CPU核心数 * 4

# 保守型（避免内存溢出）
workers = CPU核心数
```

### 2. 监控命令
```bash
# Gunicorn统计
kill -USR1 $(cat /var/run/gunicorn/health_app.pid)

# Nginx状态
curl http://localhost/nginx_status

# Django调试
# 在settings.py中启用日志
LOG_LEVEL = 'DEBUG'
```

### 3. 日志轮转
```bash
# /etc/logrotate.d/health_app
/var/log/gunicorn/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload gunicorn > /dev/null 2>&1 || true
    endscript
}
```

---

## ✅ 部署后验证

### 完整测试流程
1. ✅ 访问首页：http://your-domain.com
2. ✅ 登录系统
3. ✅ 检查服务状态（系统设置页面）
4. ✅ 上传测试PDF（智能上传）
5. ✅ 观察心跳日志：`grep "发送心跳" /var/log/gunicorn/health_app_error.log`
6. ✅ 确认不会断开连接

---

## 📝 总结

**三个关键配置点**：
1. ✅ **Nginx**: `proxy_read_timeout 600s` + `proxy_buffering off`
2. ✅ **Gunicorn**: `timeout 900` + `worker_class = 'sync'`
3. ✅ **Django**: 心跳每10秒 + OCR超时300秒

**配置顺序**：
1. 先配置并测试Gunicorn（确保能启动）
2. 再配置Nginx（反向代理到Gunicorn）
3. 最后配置Supervisor（可选，自动管理）

**日志位置**：
- Nginx: `/var/log/nginx/health_app_*.log`
- Gunicorn: `/var/log/gunicorn/health_app_*.log`
- Supervisor: `/var/log/supervisor/health_app_*.log`

**重启顺序**：
```bash
# 1. Gunicorn
sudo supervisorctl restart health_app

# 2. Nginx
sudo systemctl reload nginx
```

如有问题，请查看日志文件排查！
