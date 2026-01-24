# 生产环境部署配置

## 🌐 访问地址

- **生产环境**: https://www.zctestbench.asia/

## 📋 已更新的配置

### 1. Django配置 (health_report/settings.py)

#### 允许的主机
```python
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0', 'testserver',
                 'www.zctestbench.asia', 'zctestbench.asia']
```

#### CORS配置
```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://192.168.1.1:8000",
    "https://www.zctestbench.asia",
    "https://zctestbench.asia",
]
```

#### 静态文件和媒体文件
```python
STATIC_URL = '/static/'
MEDIA_URL = '/media/'
```

#### AI服务配置
```python
MINERU_API_URL = 'http://localhost:8001'  # 通过frp隧道访问本地GPU
```

### 2. 小程序配置 (miniprogram/config.js)

```javascript
server: {
  baseUrl: 'https://www.zctestbench.asia', // 生产环境
  timeout: 60000
}
```

## 🚀 部署步骤

### 第一步：上传项目到阿里云

**方案1：通过Git（推荐）**
```bash
# 本地推送到Git
cd /mnt/c/Users/ZC/VSProject
git init
git add health/
git commit -m "Deploy to production"
git remote add origin <你的git仓库地址>
git push -u origin main

# 在阿里云拉取
cd /root
git clone <你的git仓库地址>
```

**方案2：通过Web终端上传**
```powershell
# 本地打包
cd /mnt/c/Users/ZC/VSProject
Compress-Archive -Path health -DestinationPath health.zip
```
然后在阿里云控制台上传并解压。

### 第二步：在阿里云安装依赖

```bash
cd /root/health

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 收集静态文件
python manage.py collectstatic --noinput

# 数据库迁移
python manage.py migrate
```

### 第三步：创建Systemd服务

```bash
sudo nano /etc/systemd/system/health-project.service
```

内容：
```ini
[Unit]
Description=Health Project Django Application
After=network.target

[Service]
Type=notify
User=root
WorkingDirectory=/root/health
Environment="PATH=/root/health/venv/bin"
Environment="MINERU_API_URL=http://localhost:8001"
ExecStart=/root/health/venv/bin/gunicorn \
          --workers 3 \
          --bind 127.0.0.1:8001 \
          --access-logfile /var/log/health/gunicorn-access.log \
          --error-logfile /var/log/health/gunicorn-error.log \
          health_report.wsgi:application
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
# 创建日志目录
sudo mkdir -p /var/log/health

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable health-project
sudo systemctl start health-project
sudo systemctl status health-project
```

### 第四步：配置Nginx

```bash
# 备份原配置
sudo cp /etc/nginx/conf.d/student_learning_platform.conf /etc/nginx/conf.d/student_learning_platform.conf.backup

# 编辑配置
sudo nano /etc/nginx/conf.d/student_learning_platform.conf
```

添加以下内容到HTTPS配置段：

```nginx
# HTTPS 配置
server {
    listen 443 ssl;
    server_name zctestbench.asia www.zctestbench.asia;

    ssl_certificate /etc/letsencrypt/live/zctestbench.asia/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/zctestbench.asia/privkey.pem;

    client_max_body_size 20M;

    # ========== 健康管理项目 ==========
    # 静态文件
    location /static/ {
        alias /root/health/staticfiles/;
        expires 30d;
        add_header Cache-Control "public";
    }

    # 媒体文件
    location /media/ {
        alias /root/health/media/;
    }

    # 应用
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
```

测试并重启Nginx：
```bash
sudo nginx -t
sudo systemctl reload nginx
```

## ✅ 验证部署

### 1. 检查服务状态
```bash
sudo systemctl status health-project
sudo systemctl status nginx
```

### 2. 测试访问
```bash
# 测试本地
curl http://localhost:8001/

# 测试域名
curl https://www.zctestbench.asia/api/check-services/
```

### 3. 检查日志
```bash
# Gunicorn日志
sudo tail -f /var/log/health/gunicorn-error.log

# Nginx日志
sudo tail -f /var/log/nginx/error.log
```

## 🔧 常见问题

### 问题1：静态文件404
```bash
# 重新收集静态文件
cd /root/health
source venv/bin/activate
python manage.py collectstatic --noinput
```

### 问题2：数据库迁移失败
```bash
# 检查数据库权限
ls -la db.sqlite3

# 如果需要，创建新数据库
python manage.py migrate
```

### 问题3：MinerU连接失败
确保frp客户端在本地运行：
```powershell
cd C:\Users\ZC\VSProject\health\frp
.\frpc.exe -c frpc.ini
```

## 📊 架构图

```
Internet
    ↓
阿里云 Nginx (443)
    └─→ /          → Gunicorn :8001 (健康管理项目)
                      ↓
                  MinerU (localhost:8001)
                      ↓ frp隧道
                  本地WSL MinerU GPU
```

## 🎯 访问地址

- **项目主页**: https://www.zctestbench.asia/
- **API文档**: https://www.zctestbench.asia/api/schema/
- **管理后台**: https://www.zctestbench.asia/admin/

## 🔄 更新部署

后续更新代码：
```bash
# 在阿里云
cd /root/health
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart health-project
```

---

**部署完成后，记得修改小程序配置！**
