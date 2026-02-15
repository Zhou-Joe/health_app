# Gunicorn配置文件 - 健康管理系统
# 用途：WSGI服务器 + SSE长连接支持
# 启动命令：gunicorn -c gunicorn.conf.py health_report.wsgi:application

import multiprocessing
import os

# 服务器socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker进程配置
workers = 3  # 根据CPU核心数调整，建议 (2 x CPU核心数) + 1
worker_class = 'sync'  # SSE需要使用sync worker
worker_connections = 1000
max_requests = 1000  # 每个worker处理1000个请求后重启，防止内存泄漏
max_requests_jitter = 50  # 重启抖动，避免所有worker同时重启

# ======== 关键：超时配置 ========
# 超时时间（秒）：必须大于nginx的proxy_read_timeout
# OCR处理可能需要5-10分钟，这里设置15分钟作为安全值
timeout = 900
keepalive = 5  # HTTP keepalive秒数

# Graceful超时：重启worker时等待现有请求完成的时间
graceful_timeout = 30

# 预加载应用（减少内存占用）
preload_app = True

# 进程名称
proc_name = 'health_app_gunicorn'

# 日志配置
accesslog = '/tmp/gunicorn_health_app_access.log'
errorlog = '/tmp/gunicorn_health_app_error.log'
loglevel = 'info'  # 可选: debug, info, warning, error, critical

# 日志格式
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# PID文件
pidfile = '/tmp/gunicorn_health_app.pid'

# Daemon模式（如果使用systemd/supervisor，设为False）
daemon = False

# 用户和组
# user = 'www-data'
# group = 'www-data'

# 目录
chdir = '/home/projects/health_app'  # 修改为项目路径
raw_env = [
    'DJANGO_SETTINGS_MODULE=health_report.settings',
    'PYTHONPATH=/home/projects/health_app',  # 修改为项目路径
]

# 临时目录
tmp_upload_dir = None  # 使用系统默认，或设置为 /tmp

# ======== 为什么使用sync worker ========
# SSE (Server-Sent Events) 需要：
# 1. sync worker - 保持长连接，实时推送数据
# 2. gevent/async worker - 虽然并发高，但不适合SSE
#
# 如果需要高并发，可以考虑：
# - 增加worker数量
# - 使用nginx负载均衡到多个gunicorn实例
# ====================================

# ======== 性能优化建议 ========
# 1. Worker数量：
#    - CPU密集型（OCR处理）：workers = (2 * CPU) + 1
#    - IO密集型（主要是等待OCR API）：workers = CPU * 4
#
# 2. 监控：
#    - 使用 gunicorn --stats 来查看性能
#    - 监控日志中的处理时间
#
# 3. 如果遇到超时：
#    - 检查 nginx proxy_read_timeout (必须 < gunicorn timeout)
#    - 检查 Django的 OCR超时配置 (SystemSettings.ocr_timeout)
# ====================================
