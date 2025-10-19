#!/bin/bash

echo "========================================="
echo "  Freqtrade 完整系统启动脚本"
echo "========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Bot Token
if [ -f ".env" ]; then
    echo "📝 加载环境变量..."
    export $(cat .env | grep -v '^#' | xargs)
fi

if [ -z "$BOT_TOKEN" ]; then
    echo "❌ 错误: BOT_TOKEN 未设置"
    echo "请先创建 .env 文件并设置 BOT_TOKEN"
    exit 1
fi

# ==================== 环境变量检查 ====================
echo -e "${BLUE}检查环境变量...${NC}"

if [ -z "$MASTER_PRIVATE_KEY" ]; then
    echo -e "${YELLOW}⚠${NC} MASTER_PRIVATE_KEY 未设置"
    echo "   支付系统将自动生成新的主私钥"
    echo "   首次运行后请保存私钥到环境变量"
else
    echo -e "${GREEN}✓${NC} MASTER_PRIVATE_KEY 已设置"
fi

if [ -z "$TRONGRID_API_KEY" ]; then
    echo -e "${YELLOW}⚠${NC} TRONGRID_API_KEY 未设置（可选）"
    echo "   建议设置以提高 API 请求限额"
else
    echo -e "${GREEN}✓${NC} TRONGRID_API_KEY 已设置"
fi

echo ""

# ==================== 趋势服务检查和启动 ====================
echo -e "${BLUE}检查趋势服务...${NC}"

if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} 趋势服务已运行"
else
    echo -e "${YELLOW}⚠${NC} 趋势服务未运行，正在启动..."

    if [ -f "trend_service.py" ]; then
        mkdir -p logs
        nohup python3 trend_service.py > logs/trend_service.log 2>&1 &

        echo "等待趋势服务启动..."
        sleep 3

        if curl -s http://localhost:5000/health > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} 趋势服务启动成功"
            echo "   访问地址: http://localhost:5000"
        else
            echo -e "${YELLOW}⚠${NC} 趋势服务启动可能失败，请检查日志: tail -f logs/trend_service.log"
        fi
    else
        echo -e "${YELLOW}⚠${NC} 未找到 trend_service.py，跳过趋势服务启动"
    fi
fi

echo ""

# ==================== Python环境检查 ====================
echo -e "${BLUE}检查Python环境...${NC}"
if command -v python3 &> /dev/null; then
    python_version=$(python3 --version)
    echo -e "${GREEN}✓${NC} $python_version"
else
    echo -e "${RED}✗${NC} Python3未安装"
    exit 1
fi

# ==================== Docker检查 ====================
echo -e "${BLUE}检查Docker...${NC}"
if command -v docker &> /dev/null; then
    docker_version=$(docker --version)
    echo -e "${GREEN}✓${NC} $docker_version"
else
    echo -e "${RED}✗${NC} Docker未安装"
    echo "请先运行: ./swarm_setup.sh"
    exit 1
fi

# ==================== Docker Swarm检查 ====================
echo -e "${BLUE}检查Docker Swarm...${NC}"
if docker info 2>/dev/null | grep -q "Swarm: active"; then
    echo -e "${GREEN}✓${NC} Swarm已激活"
else
    echo -e "${RED}✗${NC} Swarm未初始化"
    echo "请先运行: ./swarm_setup.sh"
    exit 1
fi

# ==================== Portainer检查 ====================
echo -e "${BLUE}检查Portainer...${NC}"
if docker service ls 2>/dev/null | grep -q "portainer"; then
    echo -e "${GREEN}✓${NC} Portainer服务运行中"
    portainer_status=$(docker service ps portainer --filter "desired-state=running" --format "{{.CurrentState}}" | head -1)
    echo "   状态: $portainer_status"
else
    echo -e "${YELLOW}⚠${NC} Portainer未运行"
    echo "建议运行: ./swarm_setup.sh 安装Portainer"
fi

# ==================== 目录结构 ====================
echo ""
echo -e "${BLUE}创建目录结构...${NC}"
mkdir -p work_dir user_data logs
echo -e "${GREEN}✓${NC} 目录创建完成"

# ==================== 配置文件检查 ====================
echo ""
echo -e "${BLUE}检查配置文件...${NC}"

if [ -f "work_dir/config.json" ]; then
    echo -e "${GREEN}✓${NC} config.json 存在"
else
    echo -e "${YELLOW}⚠${NC} work_dir/config.json 不存在"
    echo "请确保已创建配置模板文件"
fi

if [ -f "MyStrategy.py" ]; then
    echo -e "${GREEN}✓${NC} MyStrategy.py 存在"
else
    echo -e "${YELLOW}⚠${NC} MyStrategy.py 不存在"
    echo "请确保已创建策略文件"
fi

if [ -f "trend_client.py" ]; then
    echo -e "${GREEN}✓${NC} trend_client.py 存在"
else
    echo -e "${YELLOW}⚠${NC} trend_client.py 不存在"
    echo "策略将无法连接趋势服务"
fi

# ==================== Python依赖检查 ====================
echo ""
echo -e "${BLUE}检查Python依赖...${NC}"
missing_deps=0

# 核心依赖
for package in "telegram" "docker" "ccxt" "requests"; do
    if python3 -c "import $package" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $package"
    else
        echo -e "${RED}✗${NC} $package 未安装"
        missing_deps=1
    fi
done

# 支付系统依赖
if python3 -c "import tronpy" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} tronpy (支付系统)"
else
    echo -e "${YELLOW}⚠${NC} tronpy 未安装 (支付系统需要)"
    missing_deps=1
fi

if [ $missing_deps -eq 1 ]; then
    echo ""
    echo "正在安装缺失的依赖..."
    pip3 install -r requirements.txt
fi

# ==================== 数据库初始化 ====================
echo ""
echo -e "${BLUE}检查数据库...${NC}"

if [ -f "user_data/users.db" ]; then
    echo -e "${GREEN}✓${NC} 数据库文件存在"
else
    echo -e "${YELLOW}⚠${NC} 数据库文件不存在，正在初始化..."
    python3 -c "from database import Database; db = Database(); db.create_tables()"

    if [ -f "user_data/users.db" ]; then
        echo -e "${GREEN}✓${NC} 数据库初始化成功"
    else
        echo -e "${RED}✗${NC} 数据库初始化失败"
    fi
fi

# ==================== Freqtrade镜像检查 ====================
echo ""
echo -e "${BLUE}检查Freqtrade Docker镜像...${NC}"
if docker images | grep -q "freqtrade"; then
    echo -e "${GREEN}✓${NC} Freqtrade镜像已存在"
else
    echo -e "${YELLOW}⚠${NC} Freqtrade镜像不存在"
    echo "请先构建镜像: docker build -t freqtrade:latest ."
fi

# ==================== 系统状态显示 ====================
echo ""
echo "========================================="
echo "  系统状态"
echo "========================================="
echo ""

echo "Swarm节点："
docker node ls 2>/dev/null
echo ""

echo "运行中的服务："
docker service ls 2>/dev/null
echo ""

echo "趋势服务状态："
if curl -s http://localhost:5000/api/status 2>/dev/null | python3 -m json.tool 2>/dev/null | head -10; then
    :
else
    echo -e "${YELLOW}趋势服务数据尚未初始化（首次启动需等待几秒）${NC}"
fi
echo ""

# ==================== 启动服务 ====================
echo "========================================="
echo "  启动服务"
echo "========================================="
echo ""

# 检查是否有服务在运行
if screen -ls | grep -q "payment_system\|trade_notifier\|freqtrade_bot"; then
    echo -e "${YELLOW}检测到已有服务在运行：${NC}"
    screen -ls | grep -E "payment_system|trade_notifier|freqtrade_bot"
    echo ""
    read -p "是否先停止现有服务？(y/n): " stop_choice

    if [ "$stop_choice" = "y" ]; then
        echo "正在停止服务..."
        screen -S payment_system -X quit 2>/dev/null
        screen -S trade_notifier -X quit 2>/dev/null
        screen -S freqtrade_bot -X quit 2>/dev/null
        sleep 2
        echo -e "${GREEN}✓${NC} 现有服务已停止"
    fi
fi

echo ""
echo -e "${GREEN}开始启动服务...${NC}"
echo ""

echo "1️⃣ 启动支付监控系统..."
screen -L -Logfile logs/payment_system.log -dmS payment_system bash -c "python3 payment_system.py"
echo -e "${GREEN}✓${NC} 支付监控系统已启动 (日志: logs/payment_system.log)"
sleep 2

# 2. 启动交易通知系统（带日志）
echo "2️⃣ 启动交易通知系统..."
screen -L -Logfile logs/trade_notifier.log -dmS trade_notifier bash -c "python3 trade_notifier.py"
echo -e "${GREEN}✓${NC} 交易通知系统已启动 (日志: logs/trade_notifier.log)"
sleep 2

# 3. 启动 Telegram Bot（带日志）
echo "3️⃣ 启动 Telegram Bot..."
screen -L -Logfile logs/freqtrade_bot.log -dmS freqtrade_bot bash -c "python3 bot.py"
echo -e "${GREEN}✓${NC} Telegram Bot 已启动 (日志: logs/freqtrade_bot.log)"
sleep 2

echo ""
echo "========================================="
echo "  ✅ 启动完成"
echo "========================================="
echo ""

echo "📋 服务列表："
echo "  1. 支付监控系统 (payment_system)"
echo "  2. 交易通知系统 (trade_notifier)"
echo "  3. Telegram Bot (freqtrade_bot)"
echo ""

echo "🔍 查看运行状态："
echo "  screen -ls"
echo ""

echo "📺 进入某个服务查看日志："
echo "  screen -r payment_system"
echo "  screen -r trade_notifier"
echo "  screen -r freqtrade_bot"
echo ""

echo "⌨️  退出 screen: Ctrl+A 然后按 D"
echo ""

echo "🌐 访问地址："
echo "  Portainer: http://localhost:9000"
echo "  趋势服务: http://localhost:5000"
echo ""

echo "🛑 停止所有服务："
echo "  ./stop_all.sh"
echo ""

echo "========================================="
echo "  系统已就绪"
echo "========================================="
echo ""

# 显示运行中的 screen 会话
echo "当前运行的服务："
screen -ls | grep -E "payment_system|trade_notifier|freqtrade_bot" || echo "  (无)"
echo ""