#!/bin/bash

echo "========================================="
echo "  停止 Freqtrade 所有服务"
echo "========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "正在停止服务..."
echo ""

# 停止 screen 会话
if screen -ls | grep -q "payment_system"; then
    screen -S payment_system -X quit
    echo -e "${GREEN}✓${NC} 支付监控系统已停止"
else
    echo -e "${YELLOW}⚠${NC} 支付监控系统未运行"
fi

if screen -ls | grep -q "trade_notifier"; then
    screen -S trade_notifier -X quit
    echo -e "${GREEN}✓${NC} 交易通知系统已停止"
else
    echo -e "${YELLOW}⚠${NC} 交易通知系统未运行"
fi

if screen -ls | grep -q "freqtrade_bot"; then
    screen -S freqtrade_bot -X quit
    echo -e "${GREEN}✓${NC} Telegram Bot 已停止"
else
    echo -e "${YELLOW}⚠${NC} Telegram Bot 未运行"
fi

# 停止趋势服务
if pgrep -f "trend_service.py" > /dev/null; then
    pkill -f "trend_service.py"
    echo -e "${GREEN}✓${NC} 趋势服务已停止"
else
    echo -e "${YELLOW}⚠${NC} 趋势服务未运行"
fi

echo ""
echo "========================================="
echo "  ✅ 所有服务已停止"
echo "========================================="
echo ""

# 显示剩余的 screen 会话
remaining=$(screen -ls | grep -c "Socket")
if [ $remaining -gt 0 ]; then
    echo "剩余的 screen 会话："
    screen -ls
else
    echo "没有运行中的 screen 会话"
fi
echo ""