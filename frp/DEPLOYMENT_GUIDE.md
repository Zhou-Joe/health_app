# 阿里云 + 本地GPU MinerU 完整部署指南

## 📋 架构说明

```
┌─────────────────────────────────┐
│  阿里云服务器 (8.218.181.186)    │
│  - Django Web                   │
│  - frp 服务端 (端口7000)         │
│  - MinerU隧道入口 (端口8001)     │
└───────────┬─────────────────────┘
            │ frp加密隧道
            ↓
┌─────────────────────────────────┐
│  本地GPU电脑                     │
│  - frp 客户端                   │
│  - MinerU服务 (端口8001)         │
│  - GPU加速                      │
└─────────────────────────────────┘
```

## 🚀 完整部署步骤

### 第一步：部署阿里云frp服务端

#### 1. 上传配置文件到阿里云
```bash
# 在本地Windows电脑上执行
scp frp/frps.ini root@8.218.181.186:/etc/frp/frps.ini
```

#### 2. 登录阿里云并部署
```bash
# SSH登录阿里云
ssh root@8.218.181.186

# 上传并运行部署脚本
scp frp/deploy_aliyun.sh root@8.218.181.186:/tmp/
ssh root@8.218.181.186 "bash /tmp/deploy_aliyun.sh"
```

或者**手动部署**（推荐用于了解详细步骤）：
```bash
# SSH登录阿里云
ssh root@8.218.181.186

# 1. 创建目录
mkdir -p /etc/frp
mkdir -p /var/log/frp

# 2. 下载frp
cd /tmp
wget https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_linux_amd64.tar.gz
tar -xzf frp_0.52.3_linux_amd64.tar.gz

# 3. 安装frps
sudo cp frp_0.52.3_linux_amd64/frps /usr/local/bin/
sudo chmod +x /usr/local/bin/frps

# 4. 上传配置文件（在本地电脑执行）
scp frp/frps.ini root@8.218.181.186:/etc/frp/frps.ini

# 5. 创建systemd服务（在阿里云执行）
sudo tee /etc/systemd/system/frps.service << 'EOF'
[Unit]
Description=frp server
After=network.target

[Service]
Type=simple
User=root
Restart=on-failure
RestartSec=5s
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.ini
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

# 6. 启动服务
sudo systemctl daemon-reload
sudo systemctl enable frps
sudo systemctl start frps

# 7. 检查状态
sudo systemctl status frps
```

#### 3. 配置阿里云安全组

在阿里云控制台开放以下端口：
- **7000** - frp服务端口（TCP）
- **8001** - MinerU API（TCP）
- **7500** - frp管理面板（TCP）

#### 4. 验证frp服务端
```bash
# 在阿里云上查看frp日志
sudo journalctl -u frps -f

# 访问管理面板
# 浏览器打开: http://8.218.181.186:7500
# 用户名: admin
# 密码: Health@2026MinerU
```

---

### 第二步：配置本地GPU电脑

#### 1. 下载frp客户端

**Windows:**
```powershell
# 下载
# https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_windows_amd64.zip

# 解压后，将 frpc.exe 复制到 frp 目录
```

**Linux/Mac:**
```bash
wget https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_linux_amd64.tar.gz
tar -xzf frp_0.52.3_linux_amd64.tar.gz
cp frp_0.52.3_linux_amd64/frpc frp/
chmod +x frp/frpc
```

#### 2. 确认配置文件

检查 `frp/frpc.ini` 已配置正确：
```ini
[common]
server_addr = 8.218.181.186
server_port = 7000
token = 77033a49ef3065f89c411f95cb48c0d93ca9f83bb13d8dc254daac83ac2d6191

[mineru_api]
type = tcp
local_ip = 127.0.0.1
local_port = 8001
remote_port = 8001
```

#### 3. 启动MinerU和frp客户端

**Windows - 使用启动脚本:**
```powershell
# 双击运行或在PowerShell中执行
cd frp
.\start_mineru_with_frp.bat
```

**Linux/Mac - 使用启动脚本:**
```bash
cd frp
chmod +x start_mineru_with_frp.sh
./start_mineru_with_frp.sh
```

**手动启动（Windows）:**
```powershell
# 终端1: 启动MinerU
python -m mineru.server --port 8001

# 终端2: 启动frp客户端
cd frp
.\frpc.exe -c frpc.ini
```

**手动启动（Linux/Mac）:**
```bash
# 终端1: 启动MinerU
python3 -m mineru.server --port 8001

# 终端2: 启动frp客户端
cd frp
./frpc -c frpc.ini
```

---

### 第三步：修改Django配置

#### 方法1：通过环境变量（推荐）

在阿里云服务器上设置环境变量：
```bash
# 编辑环境变量
export MINERU_API_URL='http://localhost:8001'

# 添加到 ~/.bashrc 永久生效
echo "export MINERU_API_URL='http://localhost:8001'" >> ~/.bashrc
source ~/.bashrc

# 重启Django服务
```

#### 方法2：通过系统设置界面

1. 访问Django管理后台
2. 进入系统设置
3. 修改 `mineru_api_url` 为 `http://localhost:8001`

#### 方法3：直接修改数据库
```python
# 在Django shell中执行
from medical_records.models import SystemSettings
SystemSettings.set_setting('mineru_api_url', 'http://localhost:8001')
```

---

### 第四步：测试连接

#### 1. 在阿里云上测试MinerU连接
```bash
# 测试MinerU API文档是否可访问
curl http://localhost:8001/docs

# 应该返回HTML内容（MinerU的API文档页面）
```

#### 2. 在frp管理面板查看状态
```
访问: http://8.218.181.186:7500
用户名: admin
密码: Health@2026MinerU

应该看到:
- Proxy: mineru_api
- Status: online
```

#### 3. 在Django中测试完整流程
```bash
# 在阿里云服务器上，访问Django上传测试页面
# 上传一个体检报告PDF/图片
# 检查是否成功调用MinerU进行OCR识别
```

---

## 🔧 常见问题排查

### 问题1：frp客户端连接失败

**症状：** 本地frp客户端显示 "connect to server failed"

**解决方案：**
```bash
# 1. 检查阿里云frp服务端是否运行
ssh root@8.218.181.186 "systemctl status frps"

# 2. 检查阿里云安全组是否开放7000端口
# 在阿里云控制台确认

# 3. 检查本地网络是否可以访问阿里云7000端口
telnet 8.218.181.186 7000

# 4. 检查token是否一致
# frps.ini 和 frpc.ini 的token必须相同
```

### 问题2：MinerU服务无法访问

**症状：** 阿里云访问 `http://localhost:8001` 返回连接拒绝

**解决方案：**
```bash
# 1. 在本地检查MinerU是否运行
curl http://localhost:8001/docs

# 2. 检查frp隧道是否建立
# 访问 http://8.218.181.186:7500 查看连接状态

# 3. 检查frp客户端日志
tail -f frp/frpc.log
```

### 问题3：Django调用MinerU超时

**症状：** Django上传文档时显示 "OCR识别失败"

**解决方案：**
```python
# 1. 增加OCR超时时间
# 在Django系统设置中设置: ocr_timeout = 600

# 2. 检查MinerU日志
# 确认MinerU是否正常处理请求

# 3. 手动测试MinerU API
# 在阿里云服务器上执行:
curl -X POST http://localhost:8001/file_parse \
  -F "files=@test.pdf" \
  -F "parse_method=auto" \
  -F "lang_list=ch"
```

---

## 📊 性能优化建议

### 1. 启用frp压缩（减少带宽占用）

在 `frpc.ini` 中添加：
```ini
[mineru_api]
type = tcp
local_ip = 127.0.0.1
local_port = 8001
remote_port = 8001
use_compression = true  # 启用压缩
```

### 2. 调整超时设置

在Django系统设置中：
- `ocr_timeout`: 600 (秒) - OCR超时时间
- `llm_timeout`: 600 (秒) - LLM超时时间

### 3. 监控frp连接

使用frp dashboard监控隧道状态：
```
http://8.218.181.186:7500
```

---

## 🔒 安全加固建议

### 1. 修改默认密码

已生成的随机token：
```
77033a49ef3065f89c411f95cb48c0d93ca9f83bb13d8dc254daac83ac2d6191
```

如需重新生成：
```bash
openssl rand -hex 32
```

### 2. 限制frp dashboard访问

在阿里云防火墙中，只允许特定IP访问7500端口：
```bash
# 只允许你的本地IP访问管理面板
iptables -A INPUT -p tcp --dport 7500 -s YOUR_LOCAL_IP -j ACCEPT
iptables -A INPUT -p tcp --dport 7500 -j DROP
```

### 3. 定期更新frp版本

```bash
# 检查最新版本
https://github.com/fatedier/frp/releases
```

---

## 📝 配置文件清单

| 文件 | 用途 | 位置 |
|------|------|------|
| `frps.ini` | frp服务端配置 | 阿里云 `/etc/frp/frps.ini` |
| `frpc.ini` | frp客户端配置 | 本地 `frp/frpc.ini` |
| `deploy_aliyun.sh` | 阿里云部署脚本 | `frp/deploy_aliyun.sh` |
| `start_mineru_with_frp.bat` | Windows启动脚本 | `frp/start_mineru_with_frp.bat` |
| `start_mineru_with_frp.sh` | Linux/Mac启动脚本 | `frp/start_mineru_with_frp.sh` |

---

## ✅ 验证清单

部署完成后，确认以下项目：

- [ ] 阿里云frp服务端运行正常 (`systemctl status frps`)
- [ ] 本地frp客户端显示连接成功
- [ ] frp管理面板可访问 (http://8.218.181.186:7500)
- [ ] 阿里云可访问MinerU (curl http://localhost:8001/docs)
- [ ] Django配置已更新 (MINERU_API_URL=http://localhost:8001)
- [ ] 上传测试文档成功处理

---

## 🎯 快速命令参考

### 阿里云服务器
```bash
# 查看frp状态
systemctl status frps

# 查看frp日志
journalctl -u frps -f

# 重启frp
systemctl restart frps

# 测试MinerU连接
curl http://localhost:8001/docs
```

### 本地电脑
```bash
# 查看frp客户端日志
tail -f frp/frpc.log

# 测试本地MinerU
curl http://localhost:8001/docs

# 测试阿里云访问MinerU
curl http://8.218.181.186:8001/docs
```

---

## 📞 技术支持

- frp官方文档: https://github.com/fatedier/frp
- MinerU文档: (查看项目文档)
- 问题反馈: (提交项目Issue)

---

**配置信息汇总：**
- 阿里云公网IP: `8.218.181.186`
- frp服务端口: `7000`
- MinerU端口: `8001`
- frp管理面板: `7500`
- frp token: `77033a49ef3065f89c411f95cb48c0d93ca9f83bb13d8dc254daac83ac2d6191`
- dashboard用户名: `admin`
- dashboard密码: `Health@2026MinerU`
