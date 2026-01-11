#!/bin/bash

# ============================================================
# 阿里云服务器端部署脚本 (frps)
# ============================================================

echo "=========================================="
echo "部署 frp 服务端到阿里云服务器"
echo "=========================================="

# 下载frp
FRP_VERSION="0.52.3"
cd /tmp
wget https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz
tar -xzf frp_${FRP_VERSION}_linux_amd64.tar.gz
cd frp_${FRP_VERSION}_linux_amd64

# 复制配置文件
cp frps /usr/local/bin/
cp frpc /usr/local/bin/
chmod +x /usr/local/bin/frps
chmod +x /usr/local/bin/frpc

# 创建日志目录
mkdir -p /var/log/frp
chmod 755 /var/log/frp

# 复制配置文件（需要提前上传frps.ini到服务器）
# cp frps.ini /etc/frp/

# 创建systemd服务
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

# 启动服务
systemctl daemon-reload
systemctl enable frps
systemctl start frps

# 开放防火墙端口
if command -v firewall-cmd &> /dev/null; then
    firewall-cmd --permanent --add-port=7000/tcp  # frp端口
    firewall-cmd --permanent --add-port=7500/tcp  # dashboard端口
    firewall-cmd --permanent --add-port=8001/tcp  # MinerU端口
    firewall-cmd --reload
elif command -v ufw &> /dev/null; then
    ufw allow 7000/tcp
    ufw allow 7500/tcp
    ufw allow 8001/tcp
fi

echo "=========================================="
echo "frp服务端部署完成！"
echo "=========================================="
echo "Dashboard访问地址: http://your_server_ip:7500"
echo "请修改配置文件: /etc/frp/frps.ini"
echo "=========================================="
