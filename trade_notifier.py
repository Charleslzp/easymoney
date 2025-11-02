"""
trade_notifier_improved.py - 改进的交易通知服务
主要改进：
1. 修复开仓/平仓通知遗漏问题
2. 添加更精确的时间戳判断
3. 增强调试日志
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Set, Optional
from telegram import Bot
from freqtrade_api_client import FreqtradeAPIClient
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImprovedTradeNotifier:
    """改进的交易通知器"""

    def __init__(self, bot_token: str):
        """初始化通知器"""
        self.bot = Bot(token=bot_token)
        self.api_client = FreqtradeAPIClient()
        self.db = Database()

        # 记录已通知的开仓交易
        self.notified_open_trades: Dict[int, Set[int]] = {}
        # 记录已通知的平仓交易
        self.notified_close_trades: Dict[int, Set[int]] = {}

        # ⭐ 服务启动时间
        self.start_time = datetime.now()

        # 轮询间隔（秒）
        self.poll_interval = 30

        # ⭐ 初始化标志
        self.initialized_users: Set[int] = set()

        # ⭐ 记录每个交易的最后状态,用于检测状态变化
        self.trade_last_status: Dict[int, Dict[int, bool]] = {}  # {user_id: {trade_id: is_open}}

        logger.info("[INFO] 改进的交易通知器初始化完成")
        logger.info(f"[INFO] 启动时间: {self.start_time}")

    async def check_new_trades(self, user_id: int) -> None:
        """检查用户的新交易（改进版）"""
        try:
            logger.info(f"[DEBUG] 开始检查用户 {user_id} 的交易...")

            # 获取交易历史
            success, data = self.api_client.trades(user_id, limit=50)

            if not success:
                logger.warning(f"[WARN] 用户 {user_id} 获取交易失败: {data.get('error', '未知错误')}")
                return

            # 初始化该用户的已通知列表
            if user_id not in self.notified_open_trades:
                self.notified_open_trades[user_id] = set()
            if user_id not in self.notified_close_trades:
                self.notified_close_trades[user_id] = set()
            if user_id not in self.trade_last_status:
                self.trade_last_status[user_id] = {}

            # 解析交易数据
            trades = data.get('trades', []) if isinstance(data, dict) else data

            if not trades:
                logger.info(f"[DEBUG] 用户 {user_id} 暂无交易记录")
                return

            logger.info(f"[DEBUG] 用户 {user_id} 共有 {len(trades)} 条交易记录")

            # ⭐ 首次初始化：静默加载现有交易
            if user_id not in self.initialized_users:
                logger.info(f"[INFO] 首次初始化用户 {user_id}，加载现有交易但不发送通知")
                for trade in trades:
                    trade_id = trade.get('trade_id')
                    is_open = trade.get('is_open', True)

                    # 记录交易状态
                    self.trade_last_status[user_id][trade_id] = is_open

                    if is_open:
                        self.notified_open_trades[user_id].add(trade_id)
                        logger.info(f"[DEBUG] 加载现有开仓交易: {trade_id}")
                    else:
                        self.notified_close_trades[user_id].add(trade_id)
                        logger.info(f"[DEBUG] 加载现有平仓交易: {trade_id}")

                self.initialized_users.add(user_id)
                logger.info(f"[INFO] 用户 {user_id} 初始化完成")
                return

            # ⭐ 正常检查：通知新交易和状态变化
            for trade in trades:
                trade_id = trade.get('trade_id')
                is_open = trade.get('is_open', True)

                # 获取交易时间
                open_date_str = trade.get('open_date')
                close_date_str = trade.get('close_date')

                # 检查是否是状态变化（从开仓变为平仓）
                last_status = self.trade_last_status[user_id].get(trade_id)

                if is_open:
                    # ⭐ 开仓通知：必须是新的交易且未通知过
                    if trade_id not in self.notified_open_trades[user_id]:
                        # 额外检查：确保开仓时间在启动时间之后
                        if self._is_recent_trade(open_date_str):
                            logger.info(f"[INFO] 🆕 发现新开仓: 用户 {user_id}, 交易 {trade_id}")
                            await self.send_open_notification(user_id, trade)
                            self.notified_open_trades[user_id].add(trade_id)
                        else:
                            logger.info(f"[DEBUG] 跳过历史开仓: {trade_id}, 时间: {open_date_str}")
                            self.notified_open_trades[user_id].add(trade_id)

                    # 更新状态
                    self.trade_last_status[user_id][trade_id] = True

                else:
                    # ⭐ 平仓通知：检测状态变化或新的平仓交易
                    if trade_id not in self.notified_close_trades[user_id]:
                        # 检查是否是从开仓状态变为平仓状态
                        if last_status is True:
                            logger.info(f"[INFO] 🔄 检测到状态变化: 用户 {user_id}, 交易 {trade_id} 从开仓变为平仓")
                            await self.send_close_notification(user_id, trade)
                            self.notified_close_trades[user_id].add(trade_id)
                        # 或者是新的已关闭交易
                        elif self._is_recent_trade(close_date_str):
                            logger.info(f"[INFO] 🆕 发现新平仓: 用户 {user_id}, 交易 {trade_id}")
                            await self.send_close_notification(user_id, trade)
                            self.notified_close_trades[user_id].add(trade_id)
                        else:
                            logger.info(f"[DEBUG] 跳过历史平仓: {trade_id}, 时间: {close_date_str}")
                            self.notified_close_trades[user_id].add(trade_id)

                    # 更新状态
                    self.trade_last_status[user_id][trade_id] = False

        except Exception as e:
            logger.error(f"[ERROR] 检查交易异常 (用户 {user_id}): {e}")
            import traceback
            traceback.print_exc()

    def _is_recent_trade(self, date_str: Optional[str]) -> bool:
        """
        判断交易是否是最近的（启动后发生的）

        Args:
            date_str: 日期字符串

        Returns:
            是否是最近的交易
        """
        if not date_str:
            return False

        try:
            # 解析日期字符串
            trade_time = datetime.fromisoformat(date_str.replace('Z', '+00:00'))

            # 检查是否在启动时间之后（留5分钟缓冲）
            buffer_time = self.start_time - timedelta(minutes=5)
            is_recent = trade_time > buffer_time

            logger.debug(f"[DEBUG] 交易时间: {trade_time}, 启动时间: {self.start_time}, 是否最近: {is_recent}")

            return is_recent
        except Exception as e:
            logger.warning(f"[WARN] 解析交易时间失败: {date_str}, 错误: {e}")
            return False

    async def send_open_notification(self, user_id: int, trade: Dict) -> None:
        """发送开仓通知"""
        try:
            pair = trade.get('pair', 'N/A')
            trade_id = trade.get('trade_id', 'N/A')
            open_rate = trade.get('open_rate', 0)
            amount = trade.get('amount', 0)
            stake_amount = trade.get('stake_amount', 0)
            open_date = trade.get('open_date', 'N/A')
            is_short = trade.get('is_short', False)
            direction = "做空 🔻" if is_short else "做多 🔺"

            current_profit_abs = trade.get('profit_abs', 0)
            current_profit_pct = trade.get('profit_ratio', 0) * 100
            stop_loss = trade.get('stop_loss', 0)

            message = (
                f"🟢 <b>开仓通知</b>\n"
                f"{'=' * 30}\n\n"
                f"<b>币种:</b> {pair}\n"
                f"<b>方向:</b> {direction}\n"
                f"<b>交易ID:</b> {trade_id}\n\n"
                f"<b>开仓价:</b> {open_rate:.6f}\n"
                f"<b>数量:</b> {amount:.6f}\n"
                f"<b>投入:</b> {stake_amount:.2f} USDT\n"
            )

            if stop_loss > 0:
                message += f"<b>止损价:</b> {stop_loss:.6f}\n"

            if abs(current_profit_abs) > 0.01:
                message += f"\n<b>当前盈亏:</b> {current_profit_abs:+.4f} USDT ({current_profit_pct:+.2f}%)\n"

            message += f"\n<b>开仓时间:</b> {open_date}\n"

            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )

            logger.info(f"[INFO] ✅ 已发送开仓通知: 用户 {user_id}, 交易 {trade_id}, {pair}")

        except Exception as e:
            logger.error(f"[ERROR] 发送开仓通知失败 (用户 {user_id}): {e}")
            import traceback
            traceback.print_exc()

    async def send_close_notification(self, user_id: int, trade: Dict) -> None:
        """发送平仓通知"""
        try:
            pair = trade.get('pair', 'N/A')
            trade_id = trade.get('trade_id', 'N/A')
            profit_abs = trade.get('profit_abs', 0) or trade.get('close_profit_abs', 0)
            profit_ratio = trade.get('profit_ratio', 0) or trade.get('close_profit', 0)
            profit_pct = profit_ratio * 100

            open_rate = trade.get('open_rate', 0)
            close_rate = trade.get('close_rate', 0)
            amount = trade.get('amount', 0)
            stake_amount = trade.get('stake_amount', 0)

            open_date = trade.get('open_date', 'N/A')
            close_date = trade.get('close_date', 'N/A')

            is_short = trade.get('is_short', False)
            direction = "做空 🔻" if is_short else "做多 🔺"

            exit_reason = trade.get('exit_reason', 'N/A')

            if profit_abs > 0:
                result_emoji = "✅"
                result_text = "盈利"
            elif profit_abs < 0:
                result_emoji = "❌"
                result_text = "亏损"
            else:
                result_emoji = "⚪"
                result_text = "持平"

            message = (
                f"{result_emoji} <b>平仓通知</b>\n"
                f"{'=' * 30}\n\n"
                f"<b>币种:</b> {pair}\n"
                f"<b>方向:</b> {direction}\n"
                f"<b>交易ID:</b> {trade_id}\n\n"
                f"<b>开仓价:</b> {open_rate:.6f}\n"
                f"<b>平仓价:</b> {close_rate:.6f}\n"
                f"<b>数量:</b> {amount:.6f}\n"
                f"<b>投入:</b> {stake_amount:.2f} USDT\n\n"
                f"<b>{result_text}:</b> {profit_abs:+.4f} USDT ({profit_pct:+.2f}%)\n"
            )

            if exit_reason != 'N/A':
                reason_map = {
                    'roi': '🎯 达到目标收益',
                    'stop_loss': '🛑 触发止损',
                    'trailing_stop_loss': '📉 追踪止损',
                    'sell_signal': '📊 卖出信号',
                    'force_exit': '⚠️ 强制退出',
                    'emergency_exit': '🚨 紧急退出',
                    'exit_signal': '📉 退出信号',
                }
                reason_text = reason_map.get(exit_reason, exit_reason)
                message += f"<b>退出原因:</b> {reason_text}\n"

            message += f"\n<b>开仓时间:</b> {open_date}\n"
            message += f"<b>平仓时间:</b> {close_date}\n"

            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )

            logger.info(f"[INFO] ✅ 已发送平仓通知: 用户 {user_id}, 交易 {trade_id}, 盈亏 {profit_abs:+.4f}")

        except Exception as e:
            logger.error(f"[ERROR] 发送平仓通知失败 (用户 {user_id}): {e}")
            import traceback
            traceback.print_exc()

    async def monitor_all_active_users(self) -> None:
        """监控所有激活的用户"""
        logger.info("[INFO] 开始监控所有激活用户的交易...")

        while True:
            try:
                active_users = self.db.get_running_users()

                if not active_users:
                    logger.info("[INFO] 当前没有激活用户")
                else:
                    logger.info(f"[INFO] 正在监控 {len(active_users)} 个激活用户")

                for user in active_users:
                    user_id = user.get('user_id')
                    if user_id:
                        await self.check_new_trades(user_id)

                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"[ERROR] 监控循环异常: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)

    async def start(self) -> None:
        """启动通知服务"""
        logger.info("[INFO] 🚀 改进的交易通知服务启动中...")

        try:
            await self.monitor_all_active_users()
        except KeyboardInterrupt:
            logger.info("[INFO] 🛑 交易通知服务停止")
        except Exception as e:
            logger.error(f"[ERROR] 服务异常: {e}")
            import traceback
            traceback.print_exc()


def run_notifier(bot_token: str):
    """运行通知服务"""
    notifier = ImprovedTradeNotifier(bot_token)

    try:
        asyncio.run(notifier.start())
    except KeyboardInterrupt:
        logger.info("[INFO] 服务已停止")


if __name__ == "__main__":
    import os

    BOT_TOKEN = os.getenv("BOT_TOKEN")

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ 请设置 BOT_TOKEN")
    else:
        print("=" * 50)
        print("🔔 改进的 Freqtrade 交易通知服务")
        print("=" * 50)
        print("")
        run_notifier(BOT_TOKEN)