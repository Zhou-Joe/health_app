# 阿里云 + 本地GPU MinerU配置指南

## 架构说明
```
阿里云服务器 (Web服务)
    ↓
frp隧道 (7000端口)
    ↓
本地GPU主机 (MinerU服务: 8001端口)
```

## 部署步骤

### 1. 配置阿里云服务器

```bash
# 上传frps配置到阿里云
scp frp/frps.ini root@your_aliyun_ip:/etc/frp/

# SSH登录阿里云
ssh root@your_aliyun_ip

# 运行部署脚本
bash deploy.sh

# 或手动启动frp服务
frps -c /etc/frp/frps.ini
```

### 2. 配置本地GPU主机

**如果是Linux:**
```bash
# 1. 下载frp客户端
wget https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_linux_amd64.tar.gz
tar -xzf frp_0.52.3_linux_amd64.tar.gz

# 2. 配置frpc.ini
cat > ~/frp/frpc.ini << 'EOF'
[common]
server_addr = your_aliyun_ip
server_port = 7000
token = your_secure_token_here

[mineru_api]
type = tcp
local_ip = 127.0.0.1
local_port = 8001
remote_port = 8001
EOF

# 3. 启动MinerU服务（在本地8001端口）
cd /path/to/mineru
python -m mineru.server --port 8001

# 4. 启动frp客户端
cd ~/frp
./frpc -c frpc.ini
```

**如果是Windows:**
```powershell
# 1. 下载frp客户端
# 访问: https://github.com/fatedier/frp/releases
# 下载: frp_0.52.3_windows_amd64.zip
# 解压到: C:\frp

# 2. 编辑 C:\frp\frpc.ini
[common]
server_addr = your_aliyun_ip
server_port = 7000
token = your_secure_token_here

[mineru_api]
type = tcp
local_ip = 127.0.0.1
local_port = 8001
remote_port = 8001

# 3. 启动MinerU服务
cd C:\path\to\mineru
python -m mineru.server --port 8001

# 4. 启动frp客户端（新开一个终端）
cd C:\frp
.\frpc.exe -c frpc.ini
```

### 3. 修改Django项目配置

编辑 `health_report/settings.py`:

```python
# MinerU API配置
# 原来：MINERU_API_URL = os.getenv('MINERU_API_URL', 'http://localhost:8000')
# 改为：指向阿里云服务器上的frp端口（会转发到你的本地GPU主机）

MINERU_API_URL = os.getenv('MINERU_API_URL', 'http://localhost:8001')  # 在阿里云上
# 或者使用公网IP: MINERU_API_URL = 'http://your_aliyun_ip:8001'

# 也可以在环境变量中设置：
# export MINERU_API_URL='http://localhost:8001'
```

### 4. 测试连接

```bash
# 在阿里云服务器上测试
curl http://localhost:8001/health

# 应该返回本地GPU主机MinerU服务的响应
```

## 高级配置

### 自动启动MinerU和frp

**Linux (systemd):**

```ini
# /etc/systemd/system/mineru.service
[Unit]
Description=MinerU API Service
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/mineru
ExecStart=/path/to/python -m mineru.server --port 8001
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable mineru
sudo systemctl start mineru
```

**Windows (任务计划程序):**

1. 打开"任务计划程序"
2. 创建基本任务
3. 触发器：启动时
4. 操作：启动程序
   - 程序：`python.exe`
   - 参数：`-m mineru.server --port 8001`
   - 起始于：`C:\path\to\mineru`

### 安全加固

1. **修改默认token**：
   ```ini
   # 生成随机token
   openssl rand -hex 32
   ```

2. **启用TLS加密**（可选）：
   ```ini
   # frps.ini
   [common]
   bind_port = 7000
   bind_udp_port = 7001
   # vhost_http_port = 8080
   token = your_token
   ```

3. **限制访问IP**（阿里云安全组）：
   - 只允许你的IP访问frp端口
   - 只允许阿里云内网访问MinerU端口

## 故障排查

### 检查frp连接状态
```bash
# 查看frp服务端日志
tail -f /var/log/frp/frps.log

# 查看frp客户端日志
tail -f ~/frp/frpc.log
```

### 检查端口占用
```bash
# 阿里云
netstat -tlnp | grep 8001

# 本地
netstat -an | grep 8001  # Windows/Linux
```

### 测试MinerU服务
```bash
# 本地测试
curl http://localhost:8001/health

# 阿里云测试（通过frp隧道）
curl http://localhost:8001/health
```

### 常见问题

1. **frp连接失败**：
   - 检查防火墙是否开放7000端口
   - 检查token是否一致
   - 查看frp日志

2. **MinerU无法访问**：
   - 确认MinerU服务正在运行
   - 检查8001端口是否被占用
   - 查看frp隧道是否建立成功

3. **Django请求超时**：
   - 增加超时时间：`AI_MODEL_TIMEOUT = 600`
   - 检查网络延迟
   - 查看MinerU日志

## 监控和维护

### frp Dashboard
访问: `http://your_aliyun_ip:7500`
用户名: `admin`
密码: `your_password_here`

可以看到：
- 隧道连接状态
- 流量统计
- 客户端状态

### 日志位置
```bash
# 阿里云
/var/log/frp/frps.log
journalctl -u frps -f

# 本地Linux
~/frp/frpc.log
journalctl -u frpc -f

# 本地Windows
C:\frp\frpc.log
```

## 性能优化

1. **启用压缩**：
   ```ini
   # frps.ini 和 frpc.ini 都添加
   [common]
   tcp_mux = true
   pool_count = 5
   ```

2. **调整连接池**：
   ```ini
   # frpc.ini
   [common]
   pool_count = 10  # 增加连接池
   ```

3. **本地MinerU优化**：
   - 使用GPU加速
   - 增加worker数量
   - 优化内存配置
