# 阿里云 + 本地GPU MinerU 解决方案

## 📋 方案概述

将Django项目部署在阿里云，使用本地GPU主机运行MinerU，通过frp内网穿透建立安全隧道。

## 🎯 优势

- ✅ **成本节约**：不需要购买阿里云GPU实例
- ✅ **高性能**：利用本地GPU性能
- ✅ **安全可靠**：frp提供加密隧道
- ✅ **易于部署**：配置简单，维护方便
- ✅ **灵活扩展**：可以添加多个本地GPU主机

## 📁 文件说明

```
frp/
├── README.md              # 本文件
├── UPDATE_SETTINGS.md     # 详细配置指南
├── frps.ini              # frp服务端配置（阿里云）
├── frpc.ini              # frp客户端配置（本地主机）
├── deploy.sh             # 阿里云部署脚本
├── deploy_client.sh      # Linux客户端部署脚本
└── deploy_client.ps1     # Windows客户端部署脚本
```

## 🚀 快速开始

### 1️⃣ 阿里云服务器

```bash
# 上传配置文件
scp frp/frps.ini root@your_server_ip:/etc/frp/frps.ini

# SSH登录并部署
ssh root@your_server_ip
bash <(curl -s https://raw.githubusercontent.com/your-repo/frp/main/deploy.sh)

# 或手动
wget https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_linux_amd64.tar.gz
tar -xzf frp_0.52.3_linux_amd64.tar.gz
sudo cp frp_0.52.3_linux_amd64/frps /usr/local/bin/
frps -c /etc/frp/frps.ini
```

### 2️⃣ 本地GPU主机 (Windows)

```powershell
# 1. 下载frp
# https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_windows_amd64.zip

# 2. 编辑 frpc.ini，设置你的阿里云IP和token

# 3. 启动MinerU (端口8001)
python -m mineru.server --port 8001

# 4. 启动frp客户端
.\frpc.exe -c frpc.ini
```

### 3️⃣ 本地GPU主机 (Linux)

```bash
# 1. 下载frp
wget https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_linux_amd64.tar.gz
tar -xzf frp_0.52.3_linux_amd64.tar.gz

# 2. 编辑 frpc.ini
sed -i 's/your_aliyun_server_ip/你的阿里云IP/g' frpc.ini
sed -i 's/your_secure_token_here/你的token/g' frpc.ini

# 3. 启动MinerU
cd /path/to/mineru
python -m mineru.server --port 8001 &

# 4. 启动frp客户端
cd ~/frp
./frpc -c frpc.ini
```

### 4️⃣ 修改Django配置

```python
# health_report/settings.py
MINERU_API_URL = 'http://localhost:8001'  # 通过frp隧道访问本地GPU
```

## 🔧 详细配置

查看 [UPDATE_SETTINGS.md](./UPDATE_SETTINGS.md) 获取：
- 详细部署步骤
- 安全加固建议
- 故障排查方法
- 性能优化技巧

## 📊 架构图

```
┌─────────────────┐
│  阿里云服务器    │
│  (Django Web)   │
│  Port: 8000     │
└────────┬────────┘
         │ HTTP请求
         ↓
┌─────────────────┐
│  frp 服务端     │
│  Port: 7000     │
│  Port: 8001     │ (隧道入口)
└────────┬────────┘
         │ frp隧道 (加密)
         ↓
┌─────────────────┐
│  本地GPU主机     │
│  ┌───────────┐  │
│  │ frp客户端 │  │
│  │ Port: 8001│  │ (隧道出口)
│  └─────┬─────┘  │
│        │        │
│  ┌─────↓─────┐  │
│  │  MinerU   │  │
│  │  GPU加速  │  │
│  └───────────┘  │
└─────────────────┘
```

## 🔒 安全建议

1. **修改默认token**
   ```bash
   # 生成随机token
   openssl rand -hex 32
   ```

2. **配置阿里云安全组**
   - 只允许你的IP访问7000端口（frp）
   - 只允许内网访问8001端口（MinerU）

3. **启用frp TLS**（可选）
   ```ini
   # frps.ini
   [common]
   bind_port = 7000
   token = your_token
   ```

## 📈 监控

### frp Dashboard
访问: `http://your_aliyun_ip:7500`

查看：
- 隧道连接状态
- 流量统计
- 客户端状态

## 🆘 故障排查

### 连接失败
```bash
# 检查frp服务端
sudo systemctl status frps
tail -f /var/log/frp/frps.log

# 检查frp客户端
tail -f ~/frp/frpc.log

# 测试隧道
curl http://localhost:8001/health
```

### 端口占用
```bash
# 阿里云
netstat -tlnp | grep 8001

# 本地
netstat -an | grep 8001
```

## 💡 高级用法

### 多GPU负载均衡
```ini
# frpc.ini - 本地GPU主机1
[mineru_api_1]
type = tcp
local_ip = 127.0.0.1
local_port = 8001
remote_port = 8001

# frpc.ini - 本地GPU主机2
[mineru_api_2]
type = tcp
local_ip = 127.0.0.1
local_port = 8002
remote_port = 8002
```

### 健康检查
```python
# 在Django中添加健康检查
import requests

def check_mineru_connection():
    try:
        response = requests.get(
            f"{settings.MINERU_API_URL}/health",
            timeout=5
        )
        return response.status_code == 200
    except:
        return False
```

## 📞 支持

- frp官方文档: https://github.com/fatedier/frp
- MinerU文档: (查看项目文档)
- Issue: (提交项目Issue)

## 📝 License

MIT
