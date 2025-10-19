# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
# isort: skip_file

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


def extract_currency(input_string):
    """提取货币单位"""
    match = re.match(r'([A-Za-z]+)', input_string)
    ret = match.group(1) if match else None
    return ret


class MyStrategy(IStrategy):
    """
    基于PPO强化学习的交易策略
    支持多币种、多方向(做多/做空)交易
    使用趋势服务获取市场趋势
    ⭐ 启动时自动关闭所有现有交易
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
        "entry": "market",
        "exit": "market",
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
        """初始化策略，加载模型和配置"""
        super().__init__(**kwargs)
        print('[INFO] ==========================================')
        print('[INFO] 策略初始化开始 (CPU + 趋势服务)...')
        print('[INFO] ==========================================')

        # ⭐ 添加标志位，确保只关闭一次交易
        self._trades_closed_on_startup = False

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
                self.config.get('trend_service_url', 'http://host.docker.internal:5000')
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

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        """
        ⭐ 每次bot循环开始时调用
        在这里关闭所有交易（只执行一次）
        这个时机数据库会话已经建立
        """
        # 只在第一次循环时关闭交易
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

            # ⭐ 使用 Trade.get_open_trades() 获取开放交易
            # 此时数据库会话已经建立
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

                    # 强制关闭交易
                    trade.close(current_rate=current_rate)

                    # 记录到日志
                    try:
                        self.tradlog.close_record(
                            trade_id,
                            trade.amount,
                            current_rate,
                            profit,
                            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
        """添加技术指标到数据框"""
        pair = metadata['pair']
        tar = extract_currency(pair)

        if tar not in self.asset:
            return dataframe

        index = self.asset.index(tar)
        pc = self.pc[index]

        if dataframe.empty:
            print(f'[WARN] {pair} 数据框为空')
            return dataframe

        # 从趋势服务获取趋势方向
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

        # 初始化模型状态
        if not pc.init_state:
            temp_his = dataframe.iloc[-300:-2].copy()
            temp_his = temp_his.rename(columns={'date': 'timestamp'})
            print(f'[INFO] 初始化 {tar} 模型...')

            with torch.no_grad():
                pc.init(temp_his)

        # 模型工作
        if pc.init_state:
            cur_data = dataframe.iloc[-1].copy()
            cur_data = cur_data.rename({'date': 'timestamp'})

            with torch.no_grad():
                action, _, vol = pc.work(cur_data, trend_direction)

            pc.vol_factor = vol + 0.3

            # 调整做空动作的编号
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
        """生成入场信号"""
        pair = metadata['pair']
        tar = extract_currency(pair)

        if tar not in self.asset:
            return dataframe

        last_row = dataframe.iloc[-1]

        # 做多信号
        if last_row['action'] in [2, 3] and last_row['volume'] > 0:
            print(f'[SIGNAL] 做多 {tar} @ {time.time()}')
            dataframe.loc[dataframe.index[-1], 'enter_long'] = 1

        # 做空信号
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
        """动态计算每次交易的金额"""
        leverage = self.config.get("leverage", 1)
        available_funds = self.wallets.get_total("USDT")
        current_pair_invested = self.wallets.get_used(pair)

        total_allocation = available_funds
        base = total_allocation / max(self.asset_length, 1)

        tar = extract_currency(pair)

        if tar not in self.asset:
            return 0

        index = self.asset.index(tar)
        pc = self.pc[index]

        minstake = pc.vol_factor * base
        remaining_allocation = max(base - current_pair_invested, 0)
        stake = min(remaining_allocation, minstake)
        final = max(stake, min_stake)

        print(f'[STAKE] {tar} - 总资金: {total_allocation:.2f}, '
              f'基础: {base:.2f}, 最小: {minstake:.2f}, 最终: {final:.2f}')

        return final

    def order_filled(self, pair: str, trade: Trade, order: Order,
                     current_time: datetime, **kwargs) -> None:
        """订单成交后的回调"""
        if trade.is_open:
            dir = "short" if trade.is_short else "long"
            self.tradlog.open_record(
                trade.id,
                pair,
                dir,
                trade.amount,
                trade.open_rate,
                current_time.strftime('%Y-%m-%d %H:%M:%S')
            )

        return None

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs):
        """自定义退出逻辑"""
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

                # 平多仓
                if pc.action == 4:
                    print(f'[EXIT] 平多仓 {tar}')
                    self.tradlog.close_record(
                        trade.id,
                        trade.amount,
                        trade.close_rate,
                        profit,
                        current_time.strftime('%Y-%m-%d %H:%M:%S')
                    )
                    return "close"

                # 平空仓
                elif pc.action == 7:
                    print(f'[EXIT] 平空仓 {tar}')
                    self.tradlog.close_record(
                        trade.id,
                        trade.amount,
                        trade.close_rate,
                        profit,
                        current_time.strftime('%Y-%m-%d %H:%M:%S')
                    )
                    return "close"

        except Exception as e:
            print(f"[ERROR] custom_exit 错误: {str(e)}")

        return None