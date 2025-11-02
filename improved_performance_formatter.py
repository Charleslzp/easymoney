"""
improved_performance_formatter.py - 增强的性能数据格式化模块
提供清晰的收益展示和统计信息
"""

from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class PerformanceFormatter:
    """性能数据格式化器 - 提供清晰的USDT收益展示"""

    @staticmethod
    def format_enhanced_performance(
            data: Any,
            balance_data: Optional[Dict] = None
    ) -> str:
        """
        增强版性能格式化 - 显示USDT收益和详细统计

        Args:
            data: 性能数据列表 (从 API 或 Commander 获取)
            balance_data: 账户余额数据(可选,用于计算整体收益率)

        Returns:
            格式化后的性能报告
        """
        if not data:
            return "📊 暂无性能数据"

        if isinstance(data, dict) and 'error' in data:
            return f"❌ {data['error']}"

        # 统一数据格式
        performances = data if isinstance(data, list) else []

        if not performances:
            return "📊 暂无性能数据"

        # 获取账户总金额
        total_balance = 0
        if balance_data and isinstance(balance_data, dict):
            total_balance = balance_data.get('total', 0)

        report = "📊 <b>各币种性能详情</b>\n"
        report += "=" * 30 + "\n\n"

        # 统计总数据
        total_trades = 0
        total_profit_abs = 0.0
        winning_pairs = 0
        losing_pairs = 0
        all_profits_abs = []

        # 遍历每个币种
        for perf in performances[:15]:  # 最多显示15个币种
            pair = perf.get('pair', 'Unknown')
            count = perf.get('count', 0) or perf.get('trades', 0)

            # 利润百分比
            profit_ratio = perf.get('profit', 0) or perf.get('profit_ratio', 0)
            profit_pct = profit_ratio * 100 if profit_ratio < 1 else profit_ratio

            # 绝对利润(USDT)
            profit_abs = perf.get('profit_abs', 0) or perf.get('profit_abs_total', 0)

            # 如果没有绝对利润但有百分比,进行估算
            if profit_abs == 0 and profit_pct != 0 and total_balance > 0:
                # 假设均匀分配资金
                estimated_stake = total_balance / max(len(performances), 1)
                profit_abs = estimated_stake * (profit_pct / 100)

            # 累计统计
            total_trades += count
            if profit_abs != 0:
                total_profit_abs += profit_abs
                all_profits_abs.append(profit_abs)

            # 判断盈亏
            if profit_pct > 0:
                winning_pairs += 1
                emoji = "🟢"
            elif profit_pct < 0:
                losing_pairs += 1
                emoji = "🔴"
            else:
                emoji = "⚪"

            # 格式化单个币种信息
            report += f"{emoji} <b>{pair}</b>\n"
            report += f"  交易次数: {count}次\n"

            # 显示收益信息
            if profit_abs != 0:
                report += f"  <b>累计收益: {profit_abs:+.2f} USDT ({profit_pct:+.2f}%)</b>\n"
            else:
                report += f"  收益率: <b>{profit_pct:+.2f}%</b>\n"

            # 计算并显示平均每笔收益
            if count > 0:
                if profit_abs != 0:
                    avg_profit_per_trade = profit_abs / count
                    avg_pct_per_trade = profit_pct / count
                    report += f"  单笔平均: {avg_profit_per_trade:+.2f} USDT ({avg_pct_per_trade:+.2f}%)\n"
                else:
                    avg_pct_per_trade = profit_pct / count
                    report += f"  单笔平均: {avg_pct_per_trade:+.2f}%\n"

            report += "\n"

        # ========== 汇总统计部分 ==========
        report += "=" * 30 + "\n"
        report += "<b>📈 汇总统计</b>\n\n"

        report += f"总交易次数: <b>{total_trades}</b>次\n"
        report += f"盈利币种: <b>{winning_pairs}</b> | 亏损币种: <b>{losing_pairs}</b>\n"

        # 显示总收益
        if total_profit_abs != 0:
            report += f"\n<b>💰 总累计收益: {total_profit_abs:+.2f} USDT</b>\n"

        # 整体收益率
        if total_balance > 0 and total_profit_abs != 0:
            overall_roi = (total_profit_abs / total_balance) * 100
            report += f"<b>📊 整体收益率: {overall_roi:+.2f}%</b>\n"

        # 平均每笔交易收益
        if total_trades > 0:
            avg_per_trade = total_profit_abs / total_trades if total_profit_abs != 0 else 0
            if avg_per_trade != 0:
                report += f"单笔平均: {avg_per_trade:+.2f} USDT\n"

        # 胜率
        if len(performances) > 0:
            win_rate = (winning_pairs / len(performances)) * 100
            report += f"<b>胜率: {win_rate:.1f}%</b>\n"

        # 最佳/最差表现
        if all_profits_abs:
            best_profit = max(all_profits_abs)
            worst_profit = min(all_profits_abs)
            if best_profit > 0 or worst_profit < 0:
                report += f"\n最佳币种收益: +{best_profit:.2f} USDT\n"
                report += f"最差币种收益: {worst_profit:+.2f} USDT\n"

        return report

    @staticmethod
    def format_simple_performance(data: Any) -> str:
        """
        简化版性能格式化(向后兼容)

        Args:
            data: 性能数据

        Returns:
            格式化后的简单报告
        """
        return PerformanceFormatter.format_enhanced_performance(data, None)

    @staticmethod
    def format_profit_summary(profit_data: Dict) -> str:
        """
        格式化利润摘要信息

        Args:
            profit_data: 利润数据字典

        Returns:
            格式化的利润摘要
        """
        if not profit_data:
            return "💰 暂无利润数据"

        total_profit = profit_data.get('total_profit', 0)
        total_profit_pct = profit_data.get('total_profit_percent', 0)
        trade_count = profit_data.get('trade_count', 0)
        winning = profit_data.get('winning_trades', 0)
        losing = profit_data.get('losing_trades', 0)

        report = "💰 <b>利润摘要</b>\n"
        report += "=" * 30 + "\n\n"

        report += f"<b>总收益: {total_profit:+.2f} USDT ({total_profit_pct:+.2f}%)</b>\n\n"

        report += f"总交易: {trade_count}次\n"
        report += f"盈利: {winning}次 | 亏损: {losing}次\n"

        if trade_count > 0:
            win_rate = (winning / trade_count) * 100
            avg_profit = total_profit / trade_count
            report += f"胜率: {win_rate:.1f}%\n"
            report += f"单笔平均: {avg_profit:+.2f} USDT\n"

        return report


# 便捷函数
def format_performance(data: Any, balance_data: Optional[Dict] = None) -> str:
    """
    快速格式化性能数据的便捷函数

    Args:
        data: 性能数据
        balance_data: 余额数据(可选)

    Returns:
        格式化后的报告
    """
    formatter = PerformanceFormatter()
    return formatter.format_enhanced_performance(data, balance_data)


# 测试代码
if __name__ == "__main__":
    print("=" * 50)
    print("测试增强的性能格式化器")
    print("=" * 50)

    # 模拟性能数据
    test_performance_data = [
        {
            'pair': 'ETH/USDT:USDT',
            'trades': 5,
            'profit': 0.0144,  # 1.44%
            'profit_abs': 14.4
        },
        {
            'pair': 'SOL/USDT:USDT',
            'trades': 7,
            'profit': 0.74,  # 74%
            'profit_abs': 740
        },
        {
            'pair': 'DOGE/USDT:USDT',
            'trades': 5,
            'profit': 0.98,  # 98%
            'profit_abs': 980
        },
        {
            'pair': 'BTC/USDT:USDT',
            'trades': 5,
            'profit': 0.35,  # 35%
            'profit_abs': 350
        },
        {
            'pair': 'TRB/USDT:USDT',
            'trades': 8,
            'profit': -0.09,  # -9%
            'profit_abs': -90
        }
    ]

    test_balance_data = {
        'total': 10000,
        'free': 8000,
        'used': 2000
    }

    # 测试增强版格式化
    print("\n【测试1: 增强版格式化(含余额数据)】\n")
    formatter = PerformanceFormatter()
    result = formatter.format_enhanced_performance(
        test_performance_data,
        test_balance_data
    )
    print(result)

    # 测试简化版格式化
    print("\n" + "=" * 50)
    print("\n【测试2: 简化版格式化(无余额数据)】\n")
    result2 = formatter.format_simple_performance(test_performance_data)
    print(result2)

    # 测试利润摘要
    print("\n" + "=" * 50)
    print("\n【测试3: 利润摘要】\n")
    test_profit_data = {
        'total_profit': 1994.4,
        'total_profit_percent': 19.94,
        'trade_count': 30,
        'winning_trades': 26,
        'losing_trades': 4
    }
    result3 = formatter.format_profit_summary(test_profit_data)
    print(result3)

    print("\n" + "=" * 50)
    print("测试完成!")