#!/bin/bash
# 阿里云服务器上快速部署frp服务端

set -e

echo "=========================================="
echo "  阿里云 frp 服务端部署脚本"
echo "  公网IP: 8.218.181.186"
echo "=========================================="
echo ""

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo "请使用 root 权限运行此脚本"
    exit 1
fi

# 1. 创建必要的目录
echo "[1/5] 创建frp目录..."
mkdir -p /etc/frp
mkdir -p /var/log/frp

# 2. 下载frp
echo "[2/5] 下载frp..."
cd /tmp
if [ ! -f "frp_0.52.3_linux_amd64.tar.gz" ]; then
    wget https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_linux_amd64.tar.gz
fi

# 3. 解压并安装
echo "[3/5] 安装frp..."
tar -xzf frp_0.52.3_linux_amd64.tar.gz
cp frp_0.52.3_linux_amd64/frps /usr/local/bin/
chmod +x /usr/local/bin/frps

# 4. 提示用户上传配置文件
echo "[4/5] 配置文件..."
echo "请确保已上传 frps.ini 到 /etc/frp/frps.ini"
echo ""
echo "如果还没有上传，请运行以下命令："
echo "  scp frp/frps.ini root@8.218.181.186:/etc/frp/frps.ini"
echo ""

# 检查配置文件是否存在
if [ ! -f "/etc/frp/frps.ini" ]; then
    echo "⚠️  警告: /etc/frp/frps.ini 不存在"
    echo "请先上传配置文件，然后重新运行此脚本"
    exit 1
fi

# 5. 创建systemd服务
echo "[5/5] 创建系统服务..."
cat > /etc/systemd/system/frps.service << 'EOF'
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

# 重载systemd并启动服务
systemctl daemon-reload
systemctl enable frps
systemctl restart frps

# 检查服务状态
sleep 2
if systemctl is-active --quiet frps; then
    echo ""
    echo "✅ frp 服务端部署成功！"
    echo ""
    echo "服务状态: 运行中"
    echo "管理面板: http://8.218.181.186:7500"
    echo "  - 用户名: admin"
    echo "  - 密码: Health@2026MinerU"
    echo ""
    echo "常用命令:"
    echo "  查看状态: systemctl status frps"
    echo "  查看日志: journalctl -u frps -f"
    echo "  重启服务: systemctl restart frps"
    echo "  停止服务: systemctl stop frps"
    echo ""
    echo "⚠️  请确保阿里云安全组已开放以下端口:"
    echo "  - 7000 (frp服务端口)"
    echo "  - 8001 (MinerU API)"
    echo "  - 7500 (管理面板)"
else
    echo ""
    echo "❌ frp 服务启动失败"
    echo "请查看日志: journalctl -u frps -n 50"
    exit 1
fi
