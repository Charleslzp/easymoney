# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file

"""
终极增强版策略 - 整合资金管理
版本: 5.0
新增特性:
  ✅ 从环境变量注入最大可操作金额
  ✅ 三层资金控制：max_capital -> 总资金 -> 剩余余额
  ✅ 智能限价单买卖
  ✅ 盘口深度仓位管理
  ✅ 默认杠杆3倍
"""

# ⭐ 关键: 在导入任何模块之前强制使用 CPU
import os

os.environ['CUDA_VISIBLE_DEVICES'] = ''
os.environ['CUDA_LAUNCH_BLOCKING'] = '1'
os.environ['NPY_PROMOTION_STATE'] = 'weak'
os.environ['NUMPY_EXPERIMENTAL_ARRAY_FUNCTION'] = '1'

# 抑制 NumPy 警告
import warnings

warnings.filterwarnings('ignore', category=UserWarning, message='.*NumPy 1.x.*')
warnings.filterwarnings('ignore', category=DeprecationWarning)

import numpy as np

print(f"[INFO] NumPy 版本: {np.__version__}")

if hasattr(np, '_set_promotion_state'):
    try:
        np._set_promotion_state('weak')
        print("[INFO] ✅ NumPy 2.x 兼容模式已启用")
    except:
        pass

import torch

torch.set_default_device('cpu')
if torch.cuda.is_available():
    print("[WARN] CUDA 可用但将强制使用 CPU")
    torch.cuda.is_available = lambda: False

print(f"[INFO] PyTorch 版本: {torch.__version__}, 设备: CPU (强制)")

import sys
import time
import logging

STRATEGY_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.dirname(STRATEGY_DIR)
PROJECT_ROOT = os.path.dirname(USER_DATA_DIR)

ppostratege_path = os.path.join(USER_DATA_DIR, 'ppostratege')
models_path = os.path.join(USER_DATA_DIR, 'models')

if os.path.exists(ppostratege_path):
    sys.path.append(ppostratege_path)
if os.path.exists(models_path):
    sys.path.append(models_path)

from datetime import datetime, timedelta, timezone
from pandas import DataFrame
from typing import Optional, Dict, Tuple

from freqtrade.strategy import (
    IStrategy,
    Trade,
    Order,
    PairLocks,
    informative,
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
    RealParameter,
    timeframe_to_minutes,
    timeframe_to_next_date,
    timeframe_to_prev_date,
    merge_informative_pair,
    stoploss_from_absolute,
    stoploss_from_open,
)

from easymoney.driver import PPPO_Connector
from easymoney.agent.ppo_agent import PPOAgent
import re
from record import TradeRecorder

try:
    from trend_client import TrendServiceClient

    TREND_CLIENT_AVAILABLE = True
    print("[INFO] ✅ 趋势服务客户端已导入")
except ImportError:
    TREND_CLIENT_AVAILABLE = False
    print("[WARN] ⚠️  趋势服务客户端未找到，将使用默认趋势值")

logger = logging.getLogger(__name__)

from datetime import datetime, timezone


# 辅助函数：统一获取 UTC 时间字符串
def get_utc_time_str(dt: datetime = None) -> str:
    """获取 UTC 时间字符串"""
    if dt is None:
        return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    if dt.tzinfo is None:
        # 假设是 UTC
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    else:
        # 转换为 UTC
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def extract_currency(input_string):
    """提取货币单位"""
    match = re.match(r'([A-Za-z]+)', input_string)
    ret = match.group(1) if match else None
    return ret


# ========== 订单簿深度分析器 ==========
class OrderBookAnalyzer:
    """订单簿深度分析器"""

    def __init__(self):
        self.depth_levels = 10
        self.safe_liquidity_ratio = 0.3
        self.emergency_liquidity_ratio = 0.5

    def analyze_orderbook(self, orderbook: Dict, side: str = 'sell') -> Dict:
        """分析订单簿深度"""
        try:
            if side == 'buy':
                orders = orderbook.get('asks', [])
            else:
                orders = orderbook.get('bids', [])

            if not orders:
                return self._empty_analysis()

            levels = []
            cumulative_volume = 0
            cumulative_value = 0

            for i, order in enumerate(orders[:self.depth_levels]):
                price = float(order[0])
                volume = float(order[1])
                value = price * volume

                cumulative_volume += volume
                cumulative_value += value

                levels.append({
                    'level': i + 1,
                    'price': price,
                    'volume': volume,
                    'value': value,
                    'cumulative_volume': cumulative_volume,
                    'cumulative_value': cumulative_value
                })

            top_price = levels[0]['price']
            total_volume = cumulative_volume
            total_value = cumulative_value
            avg_price = total_value / total_volume if total_volume > 0 else top_price

            liquidity_1pct = self._calculate_liquidity(levels, top_price, 0.01)
            liquidity_2pct = self._calculate_liquidity(levels, top_price, 0.02)
            liquidity_5pct = self._calculate_liquidity(levels, top_price, 0.05)

            return {
                'valid': True,
                'side': side,
                'top_price': top_price,
                'top_volume': levels[0]['volume'],
                'top_value': levels[0]['value'],
                'total_volume': total_volume,
                'total_value': total_value,
                'avg_price': avg_price,
                'levels_count': len(levels),
                'liquidity_1pct': liquidity_1pct,
                'liquidity_2pct': liquidity_2pct,
                'liquidity_5pct': liquidity_5pct,
                'levels': levels
            }

        except Exception as e:
            logger.error(f"订单簿分析失败: {e}")
            return self._empty_analysis()

    def _calculate_liquidity(self, levels: list, base_price: float,
                             deviation: float) -> float:
        """计算特定价格偏离范围内的流动性"""
        threshold_price = base_price * (1 + deviation)
        liquidity = 0

        for level in levels:
            if level['price'] <= threshold_price:
                liquidity += level['value']
            else:
                break

        return liquidity

    def _empty_analysis(self) -> Dict:
        """返回空分析结果"""
        return {
            'valid': False,
            'side': None,
            'top_price': 0,
            'top_volume': 0,
            'top_value': 0,
            'total_volume': 0,
            'total_value': 0,
            'avg_price': 0,
            'levels_count': 0,
            'liquidity_1pct': 0,
            'liquidity_2pct': 0,
            'liquidity_5pct': 0,
            'levels': []
        }


# ========== 深度仓位管理器 ==========
class DepthBasedPositionManager:
    """基于深度的仓位管理器"""

    def __init__(self):
        self.analyzer = OrderBookAnalyzer()

        self.max_position_ratio = 0.3
        self.safe_position_ratio = 0.2
        self.min_position_value = 100

        self.stop_loss_slippage = 0.03
        self.emergency_exit_depth = 5

    def calculate_safe_position_size(
            self,
            pair: str,
            orderbook: Dict,
            proposed_amount: float,
            current_price: float,
            is_short: bool = False
    ) -> Tuple[float, Dict]:
        """计算安全的开仓金额"""
        side = 'sell' if not is_short else 'buy'
        depth_analysis = self.analyzer.analyze_orderbook(orderbook, side)

        if not depth_analysis['valid']:
            logger.warning(f"{pair} 订单簿数据无效，使用保守仓位")
            return self._conservative_position(proposed_amount), depth_analysis

        required_liquidity = depth_analysis['liquidity_5pct']
        safe_position = required_liquidity * self.safe_position_ratio
        max_position = required_liquidity * self.max_position_ratio

        if proposed_amount <= safe_position:
            final_amount = proposed_amount
            decision = "SAFE"
            reason = f"仓位在安全范围内 ({proposed_amount:.0f} <= {safe_position:.0f})"

        elif proposed_amount <= max_position:
            final_amount = proposed_amount
            decision = "ACCEPTABLE"
            reason = f"仓位可接受但需谨慎 ({proposed_amount:.0f} <= {max_position:.0f})"

        else:
            final_amount = max_position
            decision = "REDUCED"
            reason = f"仓位过大，削减 {proposed_amount:.0f} -> {final_amount:.0f}"

        if final_amount < self.min_position_value:
            if proposed_amount >= self.min_position_value:
                final_amount = 0
                decision = "REJECTED"
                reason = f"流动性不足，放弃开仓（需要{self.min_position_value}，可用{safe_position:.0f}）"
            else:
                final_amount = proposed_amount
                decision = "SMALL"
                reason = "小额仓位，忽略流动性检查"

        details = {
            'pair': pair,
            'decision': decision,
            'reason': reason,
            'proposed_amount': proposed_amount,
            'final_amount': final_amount,
            'adjustment': final_amount - proposed_amount,
            'adjustment_pct': (final_amount / proposed_amount - 1) * 100 if proposed_amount > 0 else 0,
            'depth_analysis': depth_analysis,
            'liquidity': {
                'available_1pct': depth_analysis['liquidity_1pct'],
                'available_2pct': depth_analysis['liquidity_2pct'],
                'available_5pct': depth_analysis['liquidity_5pct'],
                'safe_limit': safe_position,
                'max_limit': max_position,
                'usage_ratio': (final_amount / required_liquidity * 100) if required_liquidity > 0 else 0
            }
        }

        self._log_decision(details)
        return final_amount, details

    def _conservative_position(self, proposed_amount: float) -> float:
        """保守的仓位策略（当无法获取订单簿时）"""
        return proposed_amount * 0.5

    def _log_decision(self, details: Dict):
        """记录决策日志"""
        pair = details['pair']
        decision = details['decision']
        reason = details['reason']

        if decision == "SAFE":
            print(f"[DEPTH] {pair} ✅ {reason}")
        elif decision == "ACCEPTABLE":
            print(f"[DEPTH] {pair} ⚠️  {reason}")
        elif decision == "REDUCED":
            print(f"[DEPTH] {pair} ⬇️  {reason}")
        elif decision == "REJECTED":
            print(f"[DEPTH] {pair} ❌ {reason}")
        else:
            print(f"[DEPTH] {pair} ℹ️  {reason}")

        liq = details['liquidity']
        print(f"[DEPTH] {pair} 流动性: 1%={liq['available_1pct']:.0f}, "
              f"2%={liq['available_2pct']:.0f}, 5%={liq['available_5pct']:.0f} USDT")


# ========== 智能订单策略管理器 ==========
class ImprovedOrderStrategy:
    """改进的订单策略管理器 - 从配置文件读取参数"""

    def __init__(self, config: Dict):
        """从配置文件初始化参数"""
        unfilled_config = config.get('unfilledtimeout', {})
        self.entry_retry_interval = unfilled_config.get('entry', 1) * 60
        self.exit_retry_interval = unfilled_config.get('exit', 3) * 60

        self.entry_max_premium = 0.0015
        self.entry_max_retries = 3

        self.exit_initial_premium = 0.002
        self.exit_min_premium = 0.0005
        self.exit_max_retries = 6

        entry_pricing = config.get('entry_pricing', {})
        self.use_order_book_entry = entry_pricing.get('use_order_book', True)
        self.order_book_top_entry = entry_pricing.get('order_book_top', 1)

        exit_pricing = config.get('exit_pricing', {})
        self.use_order_book_exit = exit_pricing.get('use_order_book', True)
        self.order_book_top_exit = exit_pricing.get('order_book_top', 1)

        print(f"[ORDER] ✅ 订单策略配置:")
        print(f"  - 买入超时: {self.entry_retry_interval}秒")
        print(f"  - 卖出超时: {self.exit_retry_interval}秒")
        print(f"  - 使用订单簿(买入): {self.use_order_book_entry}")
        print(f"  - 使用订单簿(卖出): {self.use_order_book_exit}")

    def get_entry_price(self, trade: Trade, current_time: datetime,
                        market_price: float, order_book: dict) -> float:
        """计算买入价格"""
        if not self.use_order_book_entry or not order_book:
            return market_price

        retry_count = getattr(trade, 'entry_retry_count', 0)

        if retry_count >= self.entry_max_retries:
            print(f'[ENTRY] 重试{retry_count}次，使用市价买入')
            return market_price

        try:
            ask_price = order_book['asks'][0][0] if order_book.get('asks') else market_price
            ask_volume = order_book['asks'][0][1] if order_book.get('asks') else 0

            my_volume = getattr(trade, 'amount', 0)
            volume_ratio = my_volume / ask_volume if ask_volume > 0 else 1

            premium = min(self.entry_max_premium, 0.0005 * (retry_count + 1))

            if volume_ratio > 0.5:
                premium *= 1.5

            entry_price = ask_price * (1 + premium)

            print(f'[ENTRY] 重试{retry_count}次，卖一价: {ask_price:.8f}, '
                  f'溢价: {premium * 100:.3f}%, 买入价: {entry_price:.8f}')

            return entry_price

        except Exception as e:
            print(f'[ERROR] 计算买入价格失败: {e}，使用市价')
            return market_price

    def get_exit_price(self, trade: Trade, current_time: datetime,
                       market_price: float, order_book: dict,
                       current_profit: float) -> float:
        """计算卖出价格"""
        if not self.use_order_book_exit or not order_book:
            return market_price

        retry_count = getattr(trade, 'exit_retry_count', 0)
        position_value = trade.amount * market_price

        if retry_count >= self.exit_max_retries:
            print(f'[EXIT] 重试{retry_count}次，市价清仓')
            return market_price

        if current_profit < -0.03:
            print(f'[EXIT] 亏损{current_profit * 100:.2f}%，快速止损')
            return market_price * (1 + self.exit_min_premium)

        try:
            bid_price = order_book['bids'][0][0] if order_book.get('bids') else market_price
            bid_volume = order_book['bids'][0][1] if order_book.get('bids') else 0

            my_volume = trade.amount
            volume_ratio = my_volume / bid_volume if bid_volume > 0 else 1

            if position_value < 1000:
                if retry_count >= 1:
                    return market_price
                base_premium = self.exit_min_premium
            elif volume_ratio < 0.2:
                base_premium = self.exit_min_premium
            elif volume_ratio < 0.5:
                base_premium = self.exit_initial_premium * 0.7
            else:
                base_premium = self.exit_initial_premium

            current_premium = max(
                self.exit_min_premium,
                base_premium - (retry_count * 0.0003)
            )

            exit_price = bid_price * (1 + current_premium)

            print(f'[EXIT] 重试{retry_count}次，金额: ${position_value:.2f}, '
                  f'买一价: {bid_price:.8f}, 溢价: {current_premium * 100:.3f}%, '
                  f'卖出价: {exit_price:.8f}')

            return exit_price

        except Exception as e:
            print(f'[ERROR] 计算卖出价格失败: {e}，使用保守策略')
            return market_price * (1 + self.exit_initial_premium)


# ========== 主策略类 ==========
class MyStrategy(IStrategy):
    """
    终极增强版策略
    整合：PPO模型 + 趋势服务 + 智能订单 + 深度管理 + 资金控制
    """

    INTERFACE_VERSION = 3
    can_short: bool = True

    minimal_roi = {
        "60": 0.048,
        "30": 0.049,
        "10": 0.05
    }

    stoploss = -0.04
    trailing_stop = False

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = True

    startup_candle_count: int = 300

    buy_rsi = IntParameter(10, 40, default=30, space="buy")
    sell_rsi = IntParameter(60, 90, default=70, space="sell")

    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": False
    }

    order_time_in_force = {
        "entry": "GTC",
        "exit": "GTC"
    }

    @property
    def plot_config(self):
        return {
            "main_plot": {
                "tema": {},
                "sar": {"color": "white"},
            },
            "subplots": {
                "MACD": {
                    "macd": {"color": "blue"},
                    "macdsignal": {"color": "orange"},
                },
                "RSI": {
                    "rsi": {"color": "red"},
                }
            }
        }

    def __init__(self, **kwargs):
        """初始化策略"""
        super().__init__(**kwargs)
        print('[INFO] ==========================================')
        print('[INFO] 策略初始化开始 (完整增强版 + 资金管理)...')
        print('[INFO] ==========================================')

        self._trades_closed_on_startup = False

        # ⭐ 新增：从环境变量读取最大可操作金额
        self.max_capital = self._get_max_capital_from_env()

        # ⭐ 默认杠杆倍数
        self.default_leverage = 3

        print(f"[CAPITAL] 💰 最大可操作金额: {self.max_capital:.2f} USDT")
        print(f"[CAPITAL] ⚡ 默认杠杆倍数: {self.default_leverage}x")

        # 初始化订单策略管理器（从配置读取）
        self.order_strategy = ImprovedOrderStrategy(self.config)

        # 初始化深度仓位管理器
        self.depth_manager = DepthBasedPositionManager()
        print('[INFO] ✅ 深度仓位管理器已初始化')

        supported_assets = [
            "AAVE", "ADA", "AVAX", "BNB", "BTC", "DOGE", "ETH",
            "ICP", "LINK", "LTC", "SOL", "SUI", "TRB", "TRX", "UMA", "XRP"
        ]

        work_dir = STRATEGY_DIR

        print(f"[DEBUG] 策略目录: {STRATEGY_DIR}")
        print(f"[DEBUG] USER_DATA_DIR: {USER_DATA_DIR}")
        print(f"[DEBUG] work_dir: {work_dir}")

        long_path = os.path.join(work_dir, 'best_long.pth')
        short_path = os.path.join(work_dir, 'best_short.pth')

        print(f"[DEBUG] 长模型: {long_path} ({'存在' if os.path.exists(long_path) else '不存在'})")
        print(f"[DEBUG] 短模型: {short_path} ({'存在' if os.path.exists(short_path) else '不存在'})")

        if not os.path.exists(long_path):
            raise FileNotFoundError(f"做多模型文件不存在: {long_path}")
        if not os.path.exists(short_path):
            raise FileNotFoundError(f"做空模型文件不存在: {short_path}")

        print(f"[INFO] 加载模型 (强制 CPU):")
        print(f"  - 做多模型: {long_path}")
        print(f"  - 做空模型: {short_path}")

        longagent = PPOAgent(4, 1, 'cpu')
        shortagent = PPOAgent(4, 1, 'cpu')
        longagent.load_model(long_path)
        shortagent.load_model(short_path)

        print("[INFO] ✅ 模型加载成功 (CPU)")

        # 初始化趋势服务客户端
        self.trend_client = None
        if TREND_CLIENT_AVAILABLE:
            trend_service_url = os.getenv(
                'TREND_SERVICE_URL',
                self.config.get('trend_service_url', 'http://43.154.201.247:5000')
            )
            self.trend_client = TrendServiceClient(trend_service_url)

            if self.trend_client.health_check():
                print(f"[INFO] ✅ 趋势服务连接成功: {trend_service_url}")
            else:
                print(f"[WARN] ⚠️  趋势服务连接失败: {trend_service_url}")
                print(f"[WARN] 策略将使用默认趋势值 1")
                self.trend_client = None
        else:
            print("[WARN] 趋势服务客户端不可用，使用默认趋势值 1")

        logpath = self.config.get("logpath", os.path.join(USER_DATA_DIR, "logs", "tradlog_default.csv"))
        log_dir = os.path.dirname(logpath)
        os.makedirs(log_dir, exist_ok=True)
        print(f"[INFO] 交易日志路径: {logpath}")

        self.tradlog = TradeRecorder(logpath)
        self.count = 0

        pair_whitelist = self.config.get("exchange", {}).get("pair_whitelist", [])
        config_assets = [pair.split("/")[0] for pair in pair_whitelist]
        eth_id = supported_assets.index("ETH")
        self.asset = config_assets

        print(f"[INFO] 配置的交易对: {pair_whitelist}")
        print(f"[INFO] 提取的资产: {config_assets}")

        self.pc = []
        agent = None

        for asset_name in config_assets:
            if asset_name in supported_assets:
                asset_id = supported_assets.index(asset_name)
                print(f"[INFO] 加载 {asset_name} 模型 (ID: {asset_id})")
            else:
                asset_id = eth_id
                print(f"[WARN] 资产 {asset_name} 不在支持列表中，使用 ETH 模型 (ID: {eth_id})")

            pc = PPPO_Connector(
                name=asset_name,
                long_model=longagent,
                short_model=shortagent,
                trend_csv=None,
                agent=agent,
                id=asset_id,
            )

            self.pc.append(pc)

        self.asset_length = len(self.pc)
        print('[INFO] ==========================================')
        print(f'[INFO] ✅ 策略初始化完成，共加载 {self.asset_length} 个资产')
        print('[INFO] ==========================================')

    def _get_max_capital_from_env(self) -> float:
        """
        ⭐ 从环境变量获取最大可操作金额
        优先级: FT_MAX_CAPITAL > config.max_capital > 无限制
        """
        # 1. 尝试从环境变量读取
        env_max_capital = os.getenv('FT_MAX_CAPITAL')
        if env_max_capital:
            try:
                max_capital = float(env_max_capital)
                print(f"[CAPITAL] ✅ 从环境变量读取: FT_MAX_CAPITAL={max_capital}")
                return max_capital
            except ValueError:
                print(f"[CAPITAL] ⚠️  环境变量 FT_MAX_CAPITAL={env_max_capital} 格式错误")

        # 2. 尝试从配置文件读取
        config_max_capital = self.config.get('max_capital')
        if config_max_capital:
            try:
                max_capital = float(config_max_capital)
                print(f"[CAPITAL] ✅ 从配置文件读取: max_capital={max_capital}")
                return max_capital
            except ValueError:
                print(f"[CAPITAL] ⚠️  配置文件 max_capital={config_max_capital} 格式错误")

        # 3. 默认无限制（使用一个很大的数）
        print(f"[CAPITAL] ℹ️  未设置最大可操作金额，无限制")
        return float('inf')

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        """Bot循环开始时的处理"""
        if not self._trades_closed_on_startup:
            print('\n' + '=' * 60)
            print('🤖 Bot循环启动 - 执行启动检查')
            print('=' * 60)

            self._close_all_existing_trades()
            self._trades_closed_on_startup = True

            print('=' * 60)
            print('✅ 启动检查完成，开始正常交易')
            print('=' * 60 + '\n')

    def _close_all_existing_trades(self):
        """关闭所有现有的开放交易"""
        try:
            print('\n📋 检查现有交易...')

            try:
                open_trades = Trade.get_open_trades()
            except AttributeError as e:
                print(f'[ERROR] 无法获取交易列表: {e}')
                print('[INFO] 数据库会话可能尚未建立，跳过关闭交易')
                return

            if not open_trades:
                print('✅ 没有需要关闭的交易\n')
                return

            print(f'⚠️  发现 {len(open_trades)} 个开放的交易，准备关闭...\n')

            closed_count = 0
            failed_count = 0

            for trade in open_trades:
                try:
                    pair = trade.pair
                    trade_id = trade.id
                    direction = "做空" if trade.is_short else "做多"
                    current_rate = trade.close_rate or trade.open_rate
                    profit = trade.close_profit or 0

                    print(f'🔄 关闭交易 #{trade_id}:')
                    print(f'   交易对: {pair}')
                    print(f'   方向: {direction}')
                    print(f'   价格: {current_rate:.8f}')
                    print(f'   盈亏: {profit:.2%}')

                    trade.close(current_rate)

                    try:
                        self.tradlog.close_record(
                            trade_id,
                            trade.amount,
                            current_rate,
                            profit,
                            get_utc_time_str()
                        )
                    except Exception as log_error:
                        print(f'   ⚠️  日志记录失败: {log_error}')

                    closed_count += 1
                    print(f'   ✅ 交易已关闭\n')

                except Exception as e:
                    failed_count += 1
                    print(f'   ❌ 关闭失败: {str(e)}\n')
                    continue

            print(f'📊 关闭统计: 成功 {closed_count} 个, 失败 {failed_count} 个\n')

        except Exception as e:
            print(f'❌ 关闭所有交易时出错: {str(e)}')
            import traceback
            traceback.print_exc()

    def informative_pairs(self):
        """定义额外的信息对"""
        return []

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """添加技术指标 - 保持原始逻辑"""
        pair = metadata['pair']
        tar = extract_currency(pair)

        if tar not in self.asset:
            return dataframe

        index = self.asset.index(tar)
        pc = self.pc[index]

        if dataframe.empty:
            print(f'[WARN] {pair} 数据框为空')
            return dataframe

        trend_direction = 1
        if self.trend_client:
            try:
                trend_direction = self.trend_client.get_trend(use_cache=True)
                if trend_direction is None:
                    print(f'[WARN] {tar} 趋势服务返回 None，使用默认值 1')
                    trend_direction = 1
            except Exception as e:
                print(f'[ERROR] {tar} 获取趋势失败: {e}，使用默认值 1')
                trend_direction = 1

        if not pc.init_state:
            temp_his = dataframe.iloc[-300:-2].copy()
            temp_his = temp_his.rename(columns={'date': 'timestamp'})
            print(f'[INFO] 初始化 {tar} 模型...')

            with torch.no_grad():
                pc.init(temp_his)

        if pc.init_state:
            cur_data = dataframe.iloc[-1].copy()
            cur_data = cur_data.rename({'date': 'timestamp'})

            with torch.no_grad():
                action, _, vol = pc.work(cur_data, trend_direction)

            pc.vol_factor = vol + 0.3

            if trend_direction == -1 and action in [2, 3, 4]:
                action += 3

            if 'action' not in dataframe.columns:
                dataframe['action'] = 0

            dataframe.iloc[-1, dataframe.columns.get_loc('action')] = action

            print(f'[INFO] {tar} 趋势: {trend_direction}, 动作: {action}, 仓位: {vol:.2f}')
        else:
            print(f'[WARN] {tar} 模型未就绪')

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """生成入场信号 - 保持原始逻辑"""
        pair = metadata['pair']
        tar = extract_currency(pair)

        if tar not in self.asset:
            return dataframe

        last_row = dataframe.iloc[-1]

        if last_row['action'] in [2, 3] and last_row['volume'] > 0:
            print(f'[SIGNAL] 做多 {tar} @ {time.time()}')
            dataframe.loc[dataframe.index[-1], 'enter_long'] = 1

        elif last_row['action'] in [5, 6] and last_row['volume'] > 0:
            print(f'[SIGNAL] 做空 {tar} @ {time.time()}')
            dataframe.loc[dataframe.index[-1], 'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """生成出场信号"""
        dataframe['exit'] = False
        return dataframe

    def custom_stake_amount(self, pair: str, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, **kwargs):
        """
        ⭐ 动态计算每次交易的金额 - 三层资金控制
        第1层: max_capital 最大可操作金额限制
        第2层: 账户总资金规模
        第3层: 剩余余额满足未开单币种分配
        """
        # 获取杠杆（默认3倍）
        leverage = self.config.get("leverage", self.default_leverage)

        # 获取账户信息
        available_funds = self.wallets.get_total("USDT")  # 账户总资金
        current_pair_invested = self.wallets.get_used(pair)  # 当前交易对已用资金

        print(f"\n[STAKE] ==================== {extract_currency(pair)} ====================")
        print(f"[STAKE] 账户总资金: {available_funds:.2f} USDT")
        print(f"[STAKE] 杠杆倍数: {leverage}x")
        print(f"[STAKE] 最大可操作金额: {self.max_capital:.2f} USDT")

        # ⭐ 第1层：最大可操作金额限制
        # 计算实际可用资金（取最小值）
        if self.max_capital < float('inf'):
            effective_capital = min(available_funds, self.max_capital)
            print(f"[STAKE] 实际可用资金: {effective_capital:.2f} USDT (受max_capital限制)")
        else:
            effective_capital = available_funds
            print(f"[STAKE] 实际可用资金: {effective_capital:.2f} USDT (无限制)")

        # ⭐ 第2层：根据总资金和币种数量计算基础仓位
        tar = extract_currency(pair)
        if tar not in self.asset:
            print(f"[STAKE] ❌ {tar} 不在支持列表中")
            return 0

        index = self.asset.index(tar)
        pc = self.pc[index]

        # 计算基础分配（平均分配给所有币种）
        base_per_asset = effective_capital / max(self.asset_length, 1)

        # 根据模型vol_factor调整
        vol_factor = getattr(pc, 'vol_factor', 1.0)
        suggested_stake = vol_factor * base_per_asset *2

        print(f"[STAKE] 基础分配: {base_per_asset:.2f} USDT")
        print(f"[STAKE] Vol因子: {vol_factor:.2f}")
        print(f"[STAKE] 建议仓位: {suggested_stake:.2f} USDT")

        # ⭐ 第3层：检查剩余余额是否足够
        # 计算剩余可用金额（考虑为其他币种预留）
        try:
            open_trades = Trade.get_open_trades()
            total_invested = sum(trade.stake_amount for trade in open_trades)
        except:
            total_invested = 0  # 所有交易对已用资金总和
        remaining_balance = effective_capital - total_invested

        # 计算还未开仓的币种数量
        unopened_pairs = self.asset_length - len(Trade.get_open_trades())
        unopened_pairs = max(unopened_pairs, 1)  # 至少为1

        # 为未开单的币种预留资金
        reserved_per_pair = remaining_balance / unopened_pairs

        print(f"[STAKE] 已投入资金: {total_invested:.2f} USDT")
        print(f"[STAKE] 剩余余额: {remaining_balance:.2f} USDT")
        print(f"[STAKE] 未开仓币种: {unopened_pairs} 个")
        print(f"[STAKE] 每个币种预留: {reserved_per_pair:.2f} USDT")

        # 取建议仓位和剩余可用的最小值
        if current_pair_invested > 0:
            # 已有仓位，计算可加仓空间
            remaining_for_pair = max(base_per_asset - current_pair_invested, 0)
            final_stake = min(suggested_stake, remaining_for_pair, remaining_balance)
        else:
            # 新开仓
            final_stake = min(suggested_stake, reserved_per_pair)

        # 确保不低于最小仓位
        final_stake = max(final_stake, min_stake)

        # 确保不超过最大仓位
        final_stake = min(final_stake, max_stake)

        print(f"[STAKE] 最终仓位: {final_stake:.2f} USDT")

        # ⭐ 新增：深度检查和调整
        try:
            orderbook = self.dp.orderbook(pair, 10)

            # 判断是做多还是做空（简化处理）
            is_short = False

            # 使用深度管理器检查并调整仓位
            adjusted_stake, depth_details = self.depth_manager.calculate_safe_position_size(
                pair=pair,
                orderbook=orderbook,
                proposed_amount=final_stake,
                current_price=current_rate,
                is_short=is_short
            )

            if adjusted_stake != final_stake:
                print(f'[STAKE] 深度调整: {final_stake:.2f} -> {adjusted_stake:.2f} '
                      f'({depth_details["decision"]})')
                final_stake = adjusted_stake

        except Exception as e:
            print(f'[WARN] {tar} 深度检查失败: {e}，使用原始仓位')

        print(f"[STAKE] ==================== 返回: {final_stake:.2f} USDT ====================\n")
        return final_stake

    def custom_entry_price(self, pair: str, trade: Optional[Trade], current_time: datetime,
                           proposed_rate: float, entry_tag: Optional[str],
                           side: str, **kwargs) -> float:
        """⭐ 自定义买入价格"""
        try:
            orderbook = self.dp.orderbook(pair, 1)

            if trade is None:
                class TempTrade:
                    def __init__(self):
                        self.entry_retry_count = 0
                        self.amount = 0

                trade = TempTrade()

            if not hasattr(trade, 'entry_retry_count'):
                trade.entry_retry_count = 0

            entry_price = self.order_strategy.get_entry_price(
                trade, current_time, proposed_rate, orderbook
            )

            return entry_price

        except Exception as e:
            print(f'[ERROR] custom_entry_price 错误: {e}，使用建议价格')
            return proposed_rate

    def custom_exit_price(self, pair: str, trade: Trade, current_time: datetime,
                          proposed_rate: float, current_profit: float,
                          exit_check: str, **kwargs) -> float:
        """⭐ 自定义卖出价格"""
        try:
            orderbook = self.dp.orderbook(pair, 1)

            if not hasattr(trade, 'exit_retry_count'):
                trade.exit_retry_count = 0

            exit_price = self.order_strategy.get_exit_price(
                trade, current_time, proposed_rate, orderbook, current_profit
            )

            return exit_price

        except Exception as e:
            print(f'[ERROR] custom_exit_price 错误: {e}，使用建议价格')
            return proposed_rate

    def check_entry_timeout(self, pair: str, trade: Trade, order: Order,
                            current_time: datetime, **kwargs) -> bool:
        """⭐ 检查买入订单超时"""
        if order.side == 'buy' and order.status == 'open':
            # 🔧 统一转换为时区无关的 datetime（移除时区信息）
            current_time_naive = current_time.replace(tzinfo=None) if current_time.tzinfo else current_time
            order_date_naive = order.order_date.replace(tzinfo=None) if order.order_date.tzinfo else order.order_date

            order_age = (current_time_naive - order_date_naive).total_seconds()

            if not hasattr(trade, 'entry_retry_count'):
                trade.entry_retry_count = 0

            if order_age > self.order_strategy.entry_retry_interval:
                trade.entry_retry_count += 1
                print(f'[ENTRY] {pair} 订单超时({order_age:.0f}秒)，'
                      f'第{trade.entry_retry_count}次重试')
                return True

        return False

    def check_exit_timeout(self, pair: str, trade: Trade, order: Order,
                           current_time: datetime, **kwargs) -> bool:
        """⭐ 检查卖出订单超时"""
        if order.side == 'sell' and order.status == 'open':
            order_age = (current_time - order.order_date).total_seconds()

            if not hasattr(trade, 'exit_retry_count'):
                trade.exit_retry_count = 0

            position_value = trade.amount * trade.close_rate

            if position_value < 1000 and order_age > 30:
                trade.exit_retry_count += 1
                print(f'[EXIT] {pair} 小单超时，直接市价')
                return True

            if order_age > self.order_strategy.exit_retry_interval:
                trade.exit_retry_count += 1
                print(f'[EXIT] {pair} 订单超时({order_age:.0f}秒)，'
                      f'第{trade.exit_retry_count}次重试')
                return True

        return False

    def order_filled(self, pair: str, trade: Trade, order: Order,
                     current_time: datetime, **kwargs) -> None:
        """订单成交回调"""
        if trade.is_open:
            dir = "short" if trade.is_short else "long"

            if hasattr(trade, 'entry_retry_count'):
                print(f'[INFO] {pair} 买入成功，重试了{trade.entry_retry_count}次')
                trade.entry_retry_count = 0

            self.tradlog.open_record(
                trade.id,
                pair,
                dir,
                trade.amount,
                trade.open_rate,
                get_utc_time_str(current_time)
            )
        else:
            if hasattr(trade, 'exit_retry_count'):
                print(f'[INFO] {pair} 卖出成功，重试了{trade.exit_retry_count}次')

        return None

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        """自定义退出逻辑 - 保持原始逻辑"""
        try:
            tar = extract_currency(pair)

            if tar not in self.asset:
                return None

            index = self.asset.index(tar)
            pc = self.pc[index]

            if not hasattr(pc, 'last_act'):
                pc.last_act = 0

            if pc.last_act != pc.action:
                pc.last_act = pc.action

                position_times = max(1, pc.env.position_times)
                amount = 1 / position_times
                profit = pc.reward

                if pc.action == 4:
                    print(f'[EXIT] 平多仓 {tar}')
                    self.tradlog.close_record(
                        trade.id,
                        trade.amount,
                        trade.close_rate,
                        profit,
                        get_utc_time_str()
                    )
                    return "close"

                elif pc.action == 7:
                    print(f'[EXIT] 平空仓 {tar}')
                    self.tradlog.close_record(
                        trade.id,
                        trade.amount,
                        trade.close_rate,
                        profit,
                        get_utc_time_str()
                    )
                    return "close"

        except Exception as e:
            print(f"[ERROR] custom_exit 错误: {str(e)}")

        return None