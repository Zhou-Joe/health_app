#!/bin/bash

# ============================================================
# 本地GPU主机端部署脚本 (frpc)
# ============================================================

echo "=========================================="
echo "部署 frp 客户端到本地GPU主机"
echo "=========================================="

# 下载frp
FRP_VERSION="0.52.3"
cd /tmp
wget https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz
tar -xzf frp_${FRP_VERSION}_linux_amd64.tar.gz
cd frp_${FRP_VERSION}_linux_amd64

# 复制到本地目录
mkdir -p ~/frp
cp frpc ~/frp/
chmod +x ~/frp/frpc

# 提示配置
echo "=========================================="
echo "frp客户端已下载到: ~/frp/"
echo "=========================================="
echo ""
echo "接下来请："
echo "1. 编辑配置文件: ~/frp/frpc.ini"
echo "2. 设置阿里云服务器IP"
echo "3. 设置token（与服务端一致）"
echo "4. 运行: cd ~/frp && ./frpc -c frpc.ini"
echo ""
echo "或者创建自启动服务（Linux）:"
cat << 'EOF'
sudo tee /etc/systemd/system/frpc.service > /dev/null << 'SERVICE'
[Unit]
Description=frp client
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
Restart=on-failure
RestartSec=5s
ExecStart=/home/YOUR_USERNAME/frp/frpc -c /home/YOUR_USERNAME/frp/frpc.ini

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable frpc
sudo systemctl start frpc
EOF
echo ""
echo "=========================================="
