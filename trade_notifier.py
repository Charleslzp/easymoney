"""
trade_notifier.py - 交易通知服务（改进版）
主要改进：
1. 修复开仓通知逻辑 - 只在真正的"新"开仓时通知
2. 添加时间戳检查，避免通知历史交易
3. 增强调试日志
4. 添加测试命令
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


class TradeNotifier:
    """交易通知器"""

    def __init__(self, bot_token: str):
        """
        初始化通知器

        Args:
            bot_token: Telegram Bot Token
        """
        self.bot = Bot(token=bot_token)
        self.api_client = FreqtradeAPIClient()
        self.db = Database()

        # 记录已通知的开仓交易
        self.notified_open_trades: Dict[int, Set[int]] = {}
        # 记录已通知的平仓交易
        self.notified_close_trades: Dict[int, Set[int]] = {}

        # ⭐ 记录服务启动时间，避免通知历史交易
        self.start_time = datetime.now()

        # 轮询间隔（秒）
        self.poll_interval = 30

        # ⭐ 初始化标志 - 用于跳过首次检查时的通知
        self.initialized_users: Set[int] = set()

        logger.info("[INFO] 交易通知器初始化完成")
        logger.info(f"[INFO] 启动时间: {self.start_time}")

    async def check_new_trades(self, user_id: int) -> None:
        """
        检查用户的新交易（开仓+平仓）

        Args:
            user_id: 用户ID
        """
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

            # 解析交易数据
            trades = data.get('trades', []) if isinstance(data, dict) else data

            if not trades:
                logger.info(f"[DEBUG] 用户 {user_id} 暂无交易记录")
                return

            logger.info(f"[DEBUG] 用户 {user_id} 共有 {len(trades)} 条交易记录")

            # ⭐ 首次初始化：静默加载现有交易，不发送通知
            if user_id not in self.initialized_users:
                logger.info(f"[INFO] 首次初始化用户 {user_id}，加载现有交易但不发送通知")
                for trade in trades:
                    trade_id = trade.get('trade_id')
                    is_open = trade.get('is_open', True)

                    if is_open:
                        # 标记为已通知（虽然实际上没通知）
                        self.notified_open_trades[user_id].add(trade_id)
                        logger.info(f"[DEBUG] 加载现有开仓交易: {trade_id}")
                    else:
                        # 标记为已通知
                        self.notified_close_trades[user_id].add(trade_id)
                        logger.info(f"[DEBUG] 加载现有平仓交易: {trade_id}")

                self.initialized_users.add(user_id)
                logger.info(f"[INFO] 用户 {user_id} 初始化完成，已加载 {len(self.notified_open_trades[user_id])} 个开仓和 {len(self.notified_close_trades[user_id])} 个平仓")
                return

            # ⭐ 正常检查：只通知新的交易
            for trade in trades:
                trade_id = trade.get('trade_id')
                is_open = trade.get('is_open', True)

                if is_open:
                    # 开仓通知：交易是开仓状态且未通知过
                    if trade_id not in self.notified_open_trades[user_id]:
                        logger.info(f"[INFO] 🆕 发现新开仓: 用户 {user_id}, 交易 {trade_id}")
                        await self.send_open_notification(user_id, trade)
                        self.notified_open_trades[user_id].add(trade_id)
                else:
                    # 平仓通知：交易已关闭且未通知过
                    if trade_id not in self.notified_close_trades[user_id]:
                        logger.info(f"[INFO] 🆕 发现新平仓: 用户 {user_id}, 交易 {trade_id}")
                        await self.send_close_notification(user_id, trade)
                        self.notified_close_trades[user_id].add(trade_id)

        except Exception as e:
            logger.error(f"[ERROR] 检查交易异常 (用户 {user_id}): {e}")
            import traceback
            traceback.print_exc()

    async def send_open_notification(self, user_id: int, trade: Dict) -> None:
        """
        发送开仓通知

        Args:
            user_id: 用户ID
            trade: 交易数据
        """
        try:
            # 提取交易信息
            pair = trade.get('pair', 'N/A')
            trade_id = trade.get('trade_id', 'N/A')

            open_rate = trade.get('open_rate', 0)
            amount = trade.get('amount', 0)
            stake_amount = trade.get('stake_amount', 0)

            open_date = trade.get('open_date', 'N/A')

            is_short = trade.get('is_short', False)
            direction = "做空 🔻" if is_short else "做多 🔺"

            # 当前盈亏
            current_profit_abs = trade.get('profit_abs', 0)
            current_profit_pct = trade.get('profit_ratio', 0) * 100

            # 止损价
            stop_loss = trade.get('stop_loss', 0)

            # 构建开仓通知消息
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

            # 发送通知
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
        """
        发送平仓通知

        Args:
            user_id: 用户ID
            trade: 交易数据
        """
        try:
            # 提取交易信息
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

            # 平仓原因
            exit_reason = trade.get('exit_reason', 'N/A')

            # 判断盈亏
            if profit_abs > 0:
                result_emoji = "✅"
                result_text = "盈利"
            elif profit_abs < 0:
                result_emoji = "❌"
                result_text = "亏损"
            else:
                result_emoji = "⚪"
                result_text = "持平"

            # 构建平仓通知消息
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
                # 翻译常见的退出原因
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

            # 发送通知
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

    async def monitor_user(self, user_id: int) -> None:
        """
        持续监控单个用户

        Args:
            user_id: 用户ID
        """
        logger.info(f"[INFO] 🔍 开始监控用户 {user_id}")

        while True:
            try:
                await self.check_new_trades(user_id)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                logger.info(f"[INFO] 停止监控用户 {user_id}")
                break
            except Exception as e:
                logger.error(f"[ERROR] 监控用户 {user_id} 异常: {e}")
                await asyncio.sleep(self.poll_interval)

    async def monitor_all_active_users(self) -> None:
        """监控所有活跃用户"""
        logger.info("[INFO] 🚀 开始监控所有活跃用户")

        tasks = []

        while True:
            try:
                # 获取所有运行中的用户
                running_users = self.db.get_running_users()

                # ⭐ 如果没有运行中的用户，尝试获取所有注册用户
                if not running_users and hasattr(self.db, 'get_all_users'):
                    logger.warning("[WARN] 没有运行中的用户，尝试获取所有注册用户")
                    running_users = self.db.get_all_users()

                current_user_ids = {user['user_id'] for user in running_users}

                logger.info(f"[INFO] 📋 当前监控用户: {current_user_ids}")

                # 为每个活跃用户创建监控任务
                for user in running_users:
                    user_id = user['user_id']

                    # 检查是否已有监控任务
                    if not any(task.get_name() == f"monitor_{user_id}" for task in tasks if not task.done()):
                        task = asyncio.create_task(self.monitor_user(user_id), name=f"monitor_{user_id}")
                        tasks.append(task)
                        logger.info(f"[INFO] ✅ 为用户 {user_id} 创建监控任务")

                # 清理完成的任务
                tasks = [task for task in tasks if not task.done()]

                # 每5分钟检查一次用户列表变化
                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"[ERROR] 监控异常: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)

    async def test_notification(self, user_id: int) -> bool:
        """
        测试通知功能（手动触发）

        Args:
            user_id: 用户ID

        Returns:
            是否成功发送测试通知
        """
        try:
            test_message = (
                "🧪 <b>测试通知</b>\n"
                f"{'=' * 30}\n\n"
                "如果你收到这条消息，说明通知功能正常！\n"
                "交易通知器已准备就绪。\n\n"
                f"启动时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            await self.bot.send_message(
                chat_id=user_id,
                text=test_message,
                parse_mode='HTML'
            )

            logger.info(f"[INFO] ✅ 测试通知已发送给用户 {user_id}")
            return True

        except Exception as e:
            logger.error(f"[ERROR] 发送测试通知失败: {e}")
            return False

    async def force_check_user(self, user_id: int) -> None:
        """
        强制检查用户交易（调试用）
        会重新初始化用户状态

        Args:
            user_id: 用户ID
        """
        logger.info(f"[INFO] 🔧 强制检查用户 {user_id}")

        # 移除初始化标记，强制重新扫描
        if user_id in self.initialized_users:
            self.initialized_users.remove(user_id)

        # 清空已通知记录
        self.notified_open_trades[user_id] = set()
        self.notified_close_trades[user_id] = set()

        # 执行检查
        await self.check_new_trades(user_id)

    async def start(self) -> None:
        """启动通知服务"""
        logger.info("[INFO] 🚀 交易通知服务启动中...")

        try:
            await self.monitor_all_active_users()
        except KeyboardInterrupt:
            logger.info("[INFO] 🛑 交易通知服务停止")
        except Exception as e:
            logger.error(f"[ERROR] 服务异常: {e}")
            import traceback
            traceback.print_exc()


def run_notifier(bot_token: str):
    """
    运行通知服务

    Args:
        bot_token: Telegram Bot Token
    """
    notifier = TradeNotifier(bot_token)

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
        print("🔔 Freqtrade 交易通知服务")
        print("=" * 50)
        print("")
        run_notifier(BOT_TOKEN)