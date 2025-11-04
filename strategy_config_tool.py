"""
策略参数配置工具 - 最终修正版
仅修改订单相关配置，不影响其他策略参数
"""

from dataclasses import dataclass
from typing import Dict
import json
import os
import sys
from pathlib import Path


@dataclass
class OrderStrategyConfig:
    """订单策略配置类"""

    # 买入参数
    entry_max_premium: float = 0.0015
    entry_retry_interval: int = 20
    entry_max_retries: int = 3

    # 卖出参数
    exit_initial_premium: float = 0.002
    exit_min_premium: float = 0.0005
    exit_retry_interval: int = 30
    exit_max_retries: int = 6

    # 紧急止损
    emergency_stop_loss: float = -0.03

    # 拆单阈值
    split_threshold_small: float = 1000
    split_threshold_medium: float = 5000
    split_threshold_large: float = 20000

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'entry': {
                'max_premium': self.entry_max_premium,
                'retry_interval': self.entry_retry_interval,
                'max_retries': self.entry_max_retries
            },
            'exit': {
                'initial_premium': self.exit_initial_premium,
                'min_premium': self.exit_min_premium,
                'retry_interval': self.exit_retry_interval,
                'max_retries': self.exit_max_retries
            },
            'risk': {
                'emergency_stop_loss': self.emergency_stop_loss
            },
            'split': {
                'small': self.split_threshold_small,
                'medium': self.split_threshold_medium,
                'large': self.split_threshold_large
            }
        }


# 预设配置方案
class PresetConfigs:
    """预设配置方案"""

    @staticmethod
    def conservative() -> OrderStrategyConfig:
        return OrderStrategyConfig(
            entry_max_premium=0.0025, entry_retry_interval=30, entry_max_retries=5,
            exit_initial_premium=0.003, exit_min_premium=0.001,
            exit_retry_interval=40, exit_max_retries=8, emergency_stop_loss=-0.04,
        )

    @staticmethod
    def balanced() -> OrderStrategyConfig:
        return OrderStrategyConfig(
            entry_max_premium=0.0015, entry_retry_interval=20, entry_max_retries=3,
            exit_initial_premium=0.002, exit_min_premium=0.0005,
            exit_retry_interval=30, exit_max_retries=6, emergency_stop_loss=-0.03,
        )

    @staticmethod
    def aggressive() -> OrderStrategyConfig:
        return OrderStrategyConfig(
            entry_max_premium=0.001, entry_retry_interval=15, entry_max_retries=2,
            exit_initial_premium=0.0015, exit_min_premium=0.0003,
            exit_retry_interval=20, exit_max_retries=4, emergency_stop_loss=-0.025,
        )

    @staticmethod
    def high_volatility() -> OrderStrategyConfig:
        return OrderStrategyConfig(
            entry_max_premium=0.0008, entry_retry_interval=10, entry_max_retries=1,
            exit_initial_premium=0.001, exit_min_premium=0.0002,
            exit_retry_interval=15, exit_max_retries=2, emergency_stop_loss=-0.02,
        )

    @staticmethod
    def btc_eth_optimized() -> OrderStrategyConfig:
        return OrderStrategyConfig(
            entry_max_premium=0.0012, entry_retry_interval=18, entry_max_retries=3,
            exit_initial_premium=0.0018, exit_min_premium=0.0004,
            exit_retry_interval=25, exit_max_retries=5, emergency_stop_loss=-0.03,
        )

    @staticmethod
    def altcoin_optimized() -> OrderStrategyConfig:
        return OrderStrategyConfig(
            entry_max_premium=0.003, entry_retry_interval=25, entry_max_retries=4,
            exit_initial_premium=0.004, exit_min_premium=0.0012,
            exit_retry_interval=35, exit_max_retries=7, emergency_stop_loss=-0.04,
        )


def find_work_dir() -> str:
    """查找 work_dir 目录"""
    candidates = ['work_dir', '../work_dir', '../../work_dir', './user_data/strategies']
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return os.getcwd()


def print_config_comparison():
    """打印所有预设配置的对比"""
    configs = {
        '保守策略': PresetConfigs.conservative(),
        '平衡策略': PresetConfigs.balanced(),
        '激进策略': PresetConfigs.aggressive(),
        '高波动策略': PresetConfigs.high_volatility(),
        'BTC/ETH策略': PresetConfigs.btc_eth_optimized(),
        '山寨币策略': PresetConfigs.altcoin_optimized(),
    }

    print("\n" + "="*80)
    print("策略配置对比表".center(80))
    print("="*80)

    headers = ['参数', '保守', '平衡', '激进', '高波动', 'BTC/ETH', '山寨币']
    print(f"\n{headers[0]:<20} {headers[1]:<10} {headers[2]:<10} {headers[3]:<10} {headers[4]:<10} {headers[5]:<10} {headers[6]:<10}")
    print("-"*80)

    params = [
        ('买入最大溢价(%)', 'entry_max_premium', 100),
        ('买入重试间隔(秒)', 'entry_retry_interval', 1),
        ('买入最大重试', 'entry_max_retries', 1),
        ('', '', 1),
        ('卖出初始溢价(%)', 'exit_initial_premium', 100),
        ('卖出最小溢价(%)', 'exit_min_premium', 100),
        ('卖出重试间隔(秒)', 'exit_retry_interval', 1),
        ('卖出最大重试', 'exit_max_retries', 1),
        ('', '', 1),
        ('紧急止损(%)', 'emergency_stop_loss', 100),
    ]

    for param_name, attr, multiplier in params:
        if param_name == '':
            print()
            continue
        row = [param_name]
        for config_name, config in configs.items():
            value = getattr(config, attr)
            if multiplier == 100:
                row.append(f'{value*multiplier:.2f}')
            else:
                row.append(f'{int(value*multiplier)}')
        print(f"{row[0]:<20} {row[1]:<10} {row[2]:<10} {row[3]:<10} {row[4]:<10} {row[5]:<10} {row[6]:<10}")

    print("\n" + "="*80)
    print("\n适用场景说明:")
    print("-"*80)
    scenarios = [
        ('保守策略', '震荡行情、低流动性币种、网络延迟较高'),
        ('平衡策略', '大部分市场环境（推荐默认使用）'),
        ('激进策略', '趋势行情、高流动性币种、追求速度'),
        ('高波动策略', '剧烈波动、快速行情、极短线交易'),
        ('BTC/ETH策略', '主流币种、大资金、稳定环境'),
        ('山寨币策略', '小币种、流动性差、需要耐心成交'),
    ]
    for name, scenario in scenarios:
        print(f"  • {name:<15} → {scenario}")
    print("\n" + "="*80 + "\n")


def patch_config_json(config_path: str, preset_name: str = 'balanced'):
    """
    ⭐ 核心功能：修改现有 config.json，添加/更新订单配置
    保留所有原有配置，只修改订单相关部分

    Args:
        config_path: config.json 路径
        preset_name: 预设配置名称
    """
    configs = {
        'conservative': PresetConfigs.conservative(),
        'balanced': PresetConfigs.balanced(),
        'aggressive': PresetConfigs.aggressive(),
        'high_volatility': PresetConfigs.high_volatility(),
        'btc_eth': PresetConfigs.btc_eth_optimized(),
        'altcoin': PresetConfigs.altcoin_optimized(),
    }

    if preset_name not in configs:
        print(f"❌ 未知预设: {preset_name}")
        return False

    # 备份原文件
    backup_path = config_path.replace('.json', '_backup.json')

    try:
        # 读取现有配置
        if not os.path.exists(config_path):
            print(f"❌ 配置文件不存在: {config_path}")
            return False

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 备份
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print(f"✅ 已备份到: {backup_path}")

        # ⭐ 只修改订单相关配置

        # 1. 添加/更新 order_types
        config['order_types'] = {
            "entry": "limit",
            "exit": "limit",
            "stoploss": "market",
            "stoploss_on_exchange": False
        }

        # 2. 添加/更新 order_time_in_force
        config['order_time_in_force'] = {
            "entry": "GTC",
            "exit": "GTC"
        }

        # 3. 修改 unfilledtimeout
        if 'unfilledtimeout' not in config:
            config['unfilledtimeout'] = {}
        config['unfilledtimeout']['entry'] = 1
        config['unfilledtimeout']['exit'] = 3
        config['unfilledtimeout']['unit'] = 'minutes'
        if 'exit_timeout_count' not in config['unfilledtimeout']:
            config['unfilledtimeout']['exit_timeout_count'] = 0

        # 4. 保存策略参数到单独文件（供策略读取）
        strategy_config = configs[preset_name]
        strategy_config_path = os.path.join(
            os.path.dirname(config_path),
            f'strategy_config_{preset_name}.json'
        )
        with open(strategy_config_path, 'w', encoding='utf-8') as f:
            json.dump(strategy_config.to_dict(), f, indent=2)
        print(f"✅ 策略参数已保存到: {strategy_config_path}")

        # 5. 保存修改后的 config.json
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        print(f"\n✅ 配置已更新: {config_path}")
        print(f"📋 修改内容:")
        print(f"   - order_types: 改为 limit")
        print(f"   - order_time_in_force: 添加")
        print(f"   - unfilledtimeout: entry=1分钟, exit=3分钟")
        print(f"   - 预设方案: {preset_name}")
        print(f"\n⚠️  原配置已备份到: {backup_path}")
        print(f"⚠️  如需回滚: cp {backup_path} {config_path}")

        return True

    except Exception as e:
        print(f"❌ 修改配置失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def interactive_patch(config_path: str = None):
    """交互式修改配置"""
    print("\n" + "="*80)
    print("交互式配置修改工具".center(80))
    print("="*80 + "\n")

    # 查找 config.json
    if config_path is None:
        candidates = [
            'work_dir/config.json',
            'config.json',
            '../work_dir/config.json',
            'user_data/config.json',
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                config_path = candidate
                break

        if config_path is None:
            print("❌ 找不到 config.json")
            config_path = input("请输入 config.json 路径: ").strip()

    print(f"📄 配置文件: {config_path}\n")

    if not os.path.exists(config_path):
        print(f"❌ 文件不存在: {config_path}")
        return False

    print("请选择预设配置:")
    print("  1. 保守策略")
    print("  2. 平衡策略（推荐）")
    print("  3. 激进策略")
    print("  4. 高波动策略")
    print("  5. BTC/ETH 优化")
    print("  6. 山寨币优化")

    choice = input("\n请输入选择 (1-6): ").strip()

    preset_map = {
        '1': 'conservative',
        '2': 'balanced',
        '3': 'aggressive',
        '4': 'high_volatility',
        '5': 'btc_eth',
        '6': 'altcoin',
    }

    if choice not in preset_map:
        print("❌ 无效选择")
        return False

    preset_name = preset_map[choice]

    print(f"\n⚠️  即将修改配置文件，原文件会备份")
    confirm = input("确认继续? (y/n): ").strip().lower()

    if confirm != 'y':
        print("❌ 已取消")
        return False

    return patch_config_json(config_path, preset_name)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'compare':
            print_config_comparison()

        elif command == 'patch':
            # ⭐ 新命令：修改现有配置
            config_path = sys.argv[2] if len(sys.argv) > 2 else None
            preset = sys.argv[3] if len(sys.argv) > 3 else 'balanced'

            if config_path and not config_path.endswith('.json'):
                preset = config_path
                config_path = None

            if config_path is None:
                # 自动查找
                candidates = ['work_dir/config.json', 'config.json']
                for c in candidates:
                    if os.path.exists(c):
                        config_path = c
                        break

            if config_path:
                patch_config_json(config_path, preset)
            else:
                print("❌ 找不到 config.json")

        elif command == 'interactive' or command == 'modify':
            # ⭐ 交互式修改
            config_path = sys.argv[2] if len(sys.argv) > 2 else None
            interactive_patch(config_path)

        else:
            print(f"❌ 未知命令: {command}")

    else:
        print("\n用法:")
        print("  python strategy_config_tool.py compare                           # 对比所有预设")
        print("  python strategy_config_tool.py patch [配置文件] [预设]              # 修改现有配置")
        print("  python strategy_config_tool.py interactive                       # 交互式修改")
        print("\n示例:")
        print("  python strategy_config_tool.py compare")
        print("  python strategy_config_tool.py patch work_dir/config.json balanced")
        print("  python strategy_config_tool.py patch balanced  # 自动查找 config.json")
        print("  python strategy_config_tool.py interactive")
        print("\n可用预设: conservative, balanced, aggressive, high_volatility, btc_eth, altcoin")
        print()