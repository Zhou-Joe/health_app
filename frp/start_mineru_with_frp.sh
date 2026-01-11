#!/bin/bash
# 本地Linux/Mac电脑启动MinerU和frp客户端

echo "=========================================="
echo "  本地GPU电脑 - MinerU + frp 客户端启动脚本"
echo "  连接到阿里云: 8.218.181.186"
echo "=========================================="
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3"
    exit 1
fi

# ============================================
# Step 1: 启动MinerU服务 (端口8001)
# ============================================
echo "[1/2] 启动MinerU服务 (端口8001)..."
nohup python3 -m mineru.server --port 8001 > mineru.log 2>&1 &
MINERU_PID=$!
echo "MinerU服务已启动 (PID: $MINERU_PID)"
sleep 3

# 检查MinerU是否启动成功
if curl -s http://localhost:8001/docs > /dev/null 2>&1; then
    echo "[OK] MinerU服务运行正常"
else
    echo "[警告] MinerU服务可能未正常启动，请检查mineru.log"
fi

# ============================================
# Step 2: 启动frp客户端
# ============================================
echo ""
echo "[2/2] 启动frp客户端..."

# 检查frpc是否存在
if [ ! -f "frpc" ]; then
    echo ""
    echo "错误: 未找到frpc"
    echo "请下载frp客户端:"
    echo "  wget https://github.com/fatedier/frp/releases/download/v0.52.3/frp_0.52.3_linux_amd64.tar.gz"
    echo "  tar -xzf frp_0.52.3_linux_amd64.tar.gz"
    echo "  cp frp_0.52.3_linux_amd64/frpc ."
    exit 1
fi

# 检查frpc.ini配置文件
if [ ! -f "frpc.ini" ]; then
    echo ""
    echo "错误: 未找到frpc.ini配置文件"
    echo "请确保frpc.ini在当前目录"
    exit 1
fi

nohup ./frpc -c frpc.ini > frpc.log 2>&1 &
FRPC_PID=$!
echo "frp客户端已启动 (PID: $FRPC_PID)"

sleep 2

# ============================================
# 显示信息
# ============================================
echo ""
echo "=========================================="
echo "  服务启动完成！"
echo "=========================================="
echo ""
echo "已启动的服务:"
echo "  1. MinerU服务 (端口8001) - PID: $MINERU_PID"
echo "  2. frp客户端 (连接到8.218.181.186:7000) - PID: $FRPC_PID"
echo ""
echo "阿里云可以通过以下地址访问MinerU:"
echo "  http://8.218.181.186:8001"
echo ""
echo "frp管理面板:"
echo "  http://8.218.181.186:7500"
echo "  用户名: admin"
echo "  密码: Health@2026MinerU"
echo ""
echo "日志文件:"
echo "  MinerU: mineru.log"
echo "  frp客户端: frpc.log"
echo ""
echo "停止服务:"
echo "  kill $MINERU_PID  # 停止MinerU"
echo "  kill $FRPC_PID    # 停止frp客户端"
echo ""
