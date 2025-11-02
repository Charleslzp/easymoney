"""
improved_formatters.py - 改进的格式化函数（双语支持）
增强功能：
1. 持仓信息增加持仓时长和清晰的方向说明
2. 余额信息增加累计利润显示
3. 完善胜率统计(基于交易笔数,包含盈亏交易列表和盈亏比)
4. ⭐ 支持中文/英文双语输出
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def calculate_duration(start_time_str: str, lang: str = 'zh') -> str:
    """
    计算持仓时长

    Args:
        start_time_str: 开仓时间字符串
        lang: 语言 ('zh' 或 'en')

    Returns:
        格式化的时长字符串
    """
    try:
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        duration = datetime.now(start_time.tzinfo) - start_time

        days = duration.days
        hours = duration.seconds // 3600
        minutes = (duration.seconds % 3600) // 60

        if lang == 'zh':
            if days > 0:
                return f"{days}天{hours}小时"
            elif hours > 0:
                return f"{hours}小时{minutes}分钟"
            else:
                return f"{minutes}分钟"
        else:  # en
            if days > 0:
                return f"{days}d {hours}h"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
    except Exception as e:
        logger.warning(f"计算时长失败: {e}")
        return "未知" if lang == 'zh' else "Unknown"


def format_status_improved(data: Any, lang: str = 'zh') -> str:
    """
    改进的持仓状态格式化 - 增加持仓时长和方向说明

    Args:
        data: 持仓数据
        lang: 语言 ('zh' 或 'en')

    Returns:
        格式化的持仓报告
    """
    if not data:
        return "📊 当前无持仓" if lang == 'zh' else "📊 No Open Positions"

    if isinstance(data, dict) and 'error' in data:
        return f"❌ {data['error']}"

    trades = data if isinstance(data, list) else []

    if not trades:
        return "📊 当前无持仓" if lang == 'zh' else "📊 No Open Positions"

    if lang == 'zh':
        report = "📊 <b>当前持仓详情</b>\n"
    else:
        report = "📊 <b>Open Positions</b>\n"

    report += "=" * 30 + "\n\n"

    for trade in trades:
        # 方向判断
        is_short = trade.get('is_short', False)
        if is_short:
            direction_emoji = "🔻"
            direction_text = "做空(Short)" if lang == 'zh' else "Short"
        else:
            direction_emoji = "🔺"
            direction_text = "做多(Long)" if lang == 'zh' else "Long"

        # 盈亏情况
        profit_pct = trade.get('profit_pct', 0) or trade.get('profit_ratio', 0) * 100
        profit_abs = trade.get('profit_abs', 0) or trade.get('profit_abs_total', 0)

        # 盈亏标识
        if profit_abs > 0:
            profit_emoji = "🟢"
        elif profit_abs < 0:
            profit_emoji = "🔴"
        else:
            profit_emoji = "⚪"

        # 持仓时长
        open_date = trade.get('open_date', 'N/A')
        duration = calculate_duration(open_date, lang) if open_date != 'N/A' else ('未知' if lang == 'zh' else 'Unknown')

        report += f"{direction_emoji} <b>{trade.get('pair')}</b> {profit_emoji}\n"

        if lang == 'zh':
            report += f"<b>方向:</b> {direction_text}\n"
            report += f"<b>持仓时长:</b> {duration}\n"
            report += f"  开仓: {trade.get('open_rate', 0):.6f}\n"
            report += f"  当前: {trade.get('current_rate', 0):.6f}\n"
            report += f"  盈亏: {profit_pct:+.2f}% ({profit_abs:+.2f} USDT)\n"
            report += f"  金额: {trade.get('stake_amount', 0):.2f} USDT\n"
            report += f"  开仓时间: {open_date}\n\n"
        else:
            report += f"<b>Direction:</b> {direction_text}\n"
            report += f"<b>Duration:</b> {duration}\n"
            report += f"  Entry: {trade.get('open_rate', 0):.6f}\n"
            report += f"  Current: {trade.get('current_rate', 0):.6f}\n"
            report += f"  P/L: {profit_pct:+.2f}% ({profit_abs:+.2f} USDT)\n"
            report += f"  Amount: {trade.get('stake_amount', 0):.2f} USDT\n"
            report += f"  Open Time: {open_date}\n\n"

    return report


def format_balance_improved(data: Dict, profit_data: Optional[Dict] = None, lang: str = 'zh') -> str:
    """
    改进的余额格式化 - 增加累计利润显示

    Args:
        data: 余额数据
        profit_data: 利润数据(可选)
        lang: 语言 ('zh' 或 'en')

    Returns:
        格式化的余额报告
    """
    if not data or 'error' in data:
        error_msg = data.get('error', '无法获取余额数据' if lang == 'zh' else 'Unable to get balance data')
        return f"❌ {error_msg}"

    currencies = data.get('currencies', [])
    total = data.get('total', 0)

    if lang == 'zh':
        report = "💰 <b>账户余额</b>\n"
        report += "=" * 30 + "\n\n"
        report += f"<b>总价值: {total:.2f} USDT</b>\n\n"
    else:
        report = "💰 <b>Account Balance</b>\n"
        report += "=" * 30 + "\n\n"
        report += f"<b>Total Value: {total:.2f} USDT</b>\n\n"

    # ⭐ 如果有利润数据,显示累计利润
    if profit_data:
        profit_abs = profit_data.get('profit_all_coin', 0) or profit_data.get('profit_closed_coin', 0)
        profit_pct = profit_data.get('profit_all_percent', 0) or profit_data.get('profit_closed_percent', 0)

        if profit_abs != 0:
            profit_emoji = "📈" if profit_abs > 0 else "📉"
            if lang == 'zh':
                report += f"{profit_emoji} <b>累计利润: {profit_abs:+.2f} USDT ({profit_pct:+.2f}%)</b>\n\n"
            else:
                report += f"{profit_emoji} <b>Total Profit: {profit_abs:+.2f} USDT ({profit_pct:+.2f}%)</b>\n\n"

    # 显示各币种余额
    if lang == 'zh':
        report += "<b>各币种余额:</b>\n\n"
    else:
        report += "<b>Balances by Currency:</b>\n\n"

    has_balance = False
    for currency in currencies:
        if currency.get('free', 0) > 0.001 or currency.get('used', 0) > 0.001:
            has_balance = True
            total_curr = currency.get('total', 0)
            free = currency.get('free', 0)
            used = currency.get('used', 0)

            report += f"<b>{currency.get('currency')}</b>\n"
            if lang == 'zh':
                report += f"  可用: {free:.6f}\n"
                report += f"  冻结: {used:.6f}\n"
                report += f"  总计: {total_curr:.6f}\n\n"
            else:
                report += f"  Available: {free:.6f}\n"
                report += f"  In Use: {used:.6f}\n"
                report += f"  Total: {total_curr:.6f}\n\n"

    if not has_balance:
        report += "暂无余额数据" if lang == 'zh' else "No balance data"

    return report


def format_profit_improved(data: Dict, trades_data: Optional[List[Dict]] = None,
                           positions_data: Optional[List[Dict]] = None, lang: str = 'zh') -> str:
    """
    改进的利润统计格式化 - 增加详细的胜率、盈亏比、交易列表、未实现盈亏

    Args:
        data: 利润统计数据
        trades_data: 详细的交易数据列表
        positions_data: 当前持仓数据
        lang: 语言 ('zh' 或 'en')

    Returns:
        格式化的利润报告
    """
    if not data or isinstance(data, dict) and 'error' in data:
        error_msg = data.get('error', '无法获取利润数据' if lang == 'zh' else 'Unable to get profit data')
        return f"❌ {error_msg}"

    # ⭐⭐⭐ 关键修复：使用交易历史重新计算统计数据
    if trades_data and len(trades_data) > 0:
        closed_trades = [t for t in trades_data if not t.get('is_open', True)]

        if closed_trades:
            trade_count = len(closed_trades)
            winning = 0
            losing = 0
            total_profit_abs = 0.0

            for t in closed_trades:
                profit = t.get('profit_abs') or 0
                total_profit_abs += profit

                if profit > 0:
                    winning += 1
                elif profit < 0:
                    losing += 1

            if trade_count > 0:
                avg_profit_ratio = sum((t.get('profit_ratio') or 0) for t in closed_trades) / trade_count
                profit_pct = avg_profit_ratio * 100
            else:
                profit_pct = 0

            logger.info(f"[Profit] 修正数据: {trade_count}笔 ({winning}盈/{losing}亏), 总盈亏: {total_profit_abs:.2f}")

            data['trade_count'] = trade_count
            data['closed_trade_count'] = trade_count
            data['winning_trades'] = winning
            data['losing_trades'] = losing
            data['profit_closed_coin'] = total_profit_abs
            data['profit_all_coin'] = total_profit_abs
            data['profit_closed_percent'] = profit_pct
            data['profit_all_percent'] = profit_pct

    if lang == 'zh':
        report = "💰 <b>利润统计详情</b>\n"
    else:
        report = "💰 <b>Profit Statistics</b>\n"

    report += "=" * 30 + "\n\n"

    # 安全获取数据（已被修正）
    trade_count = data.get('trade_count') or data.get('closed_trade_count') or 0
    winning = data.get('winning_trades') or 0
    losing = data.get('losing_trades') or 0

    if lang == 'zh':
        report += f"<b>📊 交易概况</b>\n"
        report += f"已平仓交易: <b>{trade_count}</b> 笔\n"
        report += f"盈利交易: <b>{winning}</b> 笔 🟢\n"
        report += f"亏损交易: <b>{losing}</b> 笔 🔴\n"
    else:
        report += f"<b>📊 Trading Overview</b>\n"
        report += f"Closed Trades: <b>{trade_count}</b>\n"
        report += f"Winning: <b>{winning}</b> 🟢\n"
        report += f"Losing: <b>{losing}</b> 🔴\n"

    # 胜率
    if trade_count > 0:
        win_rate = (winning / trade_count * 100)
        win_rate_label = "胜率" if lang == 'zh' else "Win Rate"
        report += f"<b>{win_rate_label}: {win_rate:.1f}%</b>\n\n"
    else:
        report += "\n"

    # ⭐ 已实现利润统计 - 安全处理 None
    profit_abs = data.get('profit_all_coin') or data.get('profit_closed_coin') or 0
    profit_pct = data.get('profit_all_percent') or data.get('profit_closed_percent') or 0

    profit_emoji = "📈" if profit_abs > 0 else "📉" if profit_abs < 0 else "⚪"

    if lang == 'zh':
        report += f"<b>💵 已实现盈亏</b>\n"
        report += f"{profit_emoji} 已平仓利润: <b>{profit_abs:+.2f} USDT</b>\n"
        report += f"收益率: <b>{profit_pct:+.2f}%</b>\n\n"
    else:
        report += f"<b>💵 Realized P/L</b>\n"
        report += f"{profit_emoji} Closed Profit: <b>{profit_abs:+.2f} USDT</b>\n"
        report += f"Return: <b>{profit_pct:+.2f}%</b>\n\n"

    # ⭐ 新增：未实现盈亏（持仓中）
    if positions_data and len(positions_data) > 0:
        try:
            # 安全计算未实现利润
            unrealized_profit = 0
            valid_positions = 0

            for p in positions_data:
                profit = (p.get('profit_abs') or p.get('profit_abs_total') or 0)
                if profit is not None:
                    unrealized_profit += profit
                    valid_positions += 1

            # 计算平均收益率
            unrealized_pct = 0
            if valid_positions > 0:
                for p in positions_data:
                    pct = (p.get('profit_pct') or (p.get('profit_ratio') or 0) * 100)
                    if pct is not None:
                        unrealized_pct += pct
                unrealized_pct = unrealized_pct / valid_positions

            total_profit = profit_abs + unrealized_profit
            total_emoji = "📈" if total_profit > 0 else "📉" if total_profit < 0 else "⚪"

            if lang == 'zh':
                report += f"<b>📊 持仓盈亏</b>\n"
                unrealized_emoji = "🟢" if unrealized_profit > 0 else "🔴" if unrealized_profit < 0 else "⚪"
                report += f"{unrealized_emoji} 未实现利润: <b>{unrealized_profit:+.2f} USDT</b>\n"
                report += f"平均收益率: <b>{unrealized_pct:+.2f}%</b>\n"
                report += f"持仓数量: <b>{len(positions_data)}</b> 笔\n\n"
                report += f"<b>💰 总盈亏（含持仓）</b>\n"
                report += f"{total_emoji} 总计: <b>{total_profit:+.2f} USDT</b>\n\n"
            else:
                report += f"<b>📊 Open Position P/L</b>\n"
                unrealized_emoji = "🟢" if unrealized_profit > 0 else "🔴" if unrealized_profit < 0 else "⚪"
                report += f"{unrealized_emoji} Unrealized Profit: <b>{unrealized_profit:+.2f} USDT</b>\n"
                report += f"Avg Return: <b>{unrealized_pct:+.2f}%</b>\n"
                report += f"Open Positions: <b>{len(positions_data)}</b>\n\n"
                report += f"<b>💰 Total P/L (incl. open)</b>\n"
                report += f"{total_emoji} Total: <b>{total_profit:+.2f} USDT</b>\n\n"
        except Exception as e:
            logger.warning(f"计算持仓盈亏失败: {e}")

    # ⭐ 计算盈亏比和平均盈亏
    if trades_data and len(trades_data) > 0:
        try:
            winning_trades_list = []
            losing_trades_list = []

            for trade in trades_data:
                is_open = trade.get('is_open', True)
                if is_open:
                    continue

                profit = trade.get('profit_abs') or 0
                profit_ratio = trade.get('profit_ratio') or 0

                if profit is None:
                    continue

                if profit > 0:
                    winning_trades_list.append({
                        'pair': trade.get('pair', 'N/A'),
                        'profit': profit,
                        'profit_pct': profit_ratio * 100
                    })
                elif profit < 0:
                    losing_trades_list.append({
                        'pair': trade.get('pair', 'N/A'),
                        'profit': profit,
                        'profit_pct': profit_ratio * 100
                    })

            # 计算平均盈利和平均亏损
            if winning_trades_list or losing_trades_list:
                if lang == 'zh':
                    report += f"<b>📈 盈亏分析</b>\n"
                else:
                    report += f"<b>📈 P/L Analysis</b>\n"

                if winning_trades_list:
                    avg_win = sum(t['profit'] for t in winning_trades_list) / len(winning_trades_list)
                    if lang == 'zh':
                        report += f"平均盈利: <b>+{avg_win:.2f} USDT</b>\n"
                    else:
                        report += f"Avg Win: <b>+{avg_win:.2f} USDT</b>\n"

                if losing_trades_list:
                    avg_loss = sum(t['profit'] for t in losing_trades_list) / len(losing_trades_list)
                    if lang == 'zh':
                        report += f"平均亏损: <b>{avg_loss:.2f} USDT</b>\n"
                    else:
                        report += f"Avg Loss: <b>{avg_loss:.2f} USDT</b>\n"

                # ⭐ 盈亏比
                if winning_trades_list and losing_trades_list:
                    avg_win_amount = sum(t['profit'] for t in winning_trades_list) / len(winning_trades_list)
                    avg_loss_amount = abs(sum(t['profit'] for t in losing_trades_list) / len(losing_trades_list))

                    if avg_loss_amount > 0:
                        profit_loss_ratio = avg_win_amount / avg_loss_amount
                        ratio_label = "盈亏比" if lang == 'zh' else "Profit/Loss Ratio"
                        report += f"<b>{ratio_label}: {profit_loss_ratio:.2f}</b>\n"

                report += "\n"

            # ⭐ 显示最近的盈利交易(最多5笔)
            if winning_trades_list:
                if lang == 'zh':
                    report += "<b>🟢 最近盈利交易:</b>\n"
                else:
                    report += "<b>🟢 Recent Winning Trades:</b>\n"

                for trade in winning_trades_list[:5]:
                    report += f"  • {trade['pair']}: +{trade['profit']:.2f} USDT ({trade['profit_pct']:+.2f}%)\n"
                report += "\n"

            # ⭐ 显示最近的亏损交易(最多5笔)
            if losing_trades_list:
                if lang == 'zh':
                    report += "<b>🔴 最近亏损交易:</b>\n"
                else:
                    report += "<b>🔴 Recent Losing Trades:</b>\n"

                for trade in losing_trades_list[:5]:
                    report += f"  • {trade['pair']}: {trade['profit']:.2f} USDT ({trade['profit_pct']:+.2f}%)\n"
                report += "\n"
        except Exception as e:
            logger.warning(f"计算盈亏比失败: {e}")

    # ⭐⭐⭐ 最佳/最差交易（从实际交易列表中计算）
    try:
        if trades_data and len(trades_data) > 0:
            # 从已关闭的交易中找出最佳和最差
            closed_trades_profits = []
            for trade in trades_data:
                if not trade.get('is_open', True):  # 只看已关闭的交易
                    profit_ratio = trade.get('profit_ratio') or 0
                    profit_abs = trade.get('profit_abs') or 0
                    if profit_ratio is not None:
                        closed_trades_profits.append({
                            'pair': trade.get('pair', 'N/A'),
                            'profit_ratio': profit_ratio,
                            'profit_abs': profit_abs
                        })

            if closed_trades_profits:
                # 找出最佳和最差
                best_trade = max(closed_trades_profits, key=lambda x: x['profit_ratio'])
                worst_trade = min(closed_trades_profits, key=lambda x: x['profit_ratio'])

                if lang == 'zh':
                    report += "<b>📌 极值交易</b>\n"
                    report += f"最佳单笔: <b>{best_trade['pair']}</b> +{best_trade['profit_ratio'] * 100:.2f}% (+{best_trade['profit_abs']:.2f} USDT)\n"
                    report += f"最差单笔: <b>{worst_trade['pair']}</b> {worst_trade['profit_ratio'] * 100:+.2f}% ({worst_trade['profit_abs']:+.2f} USDT)\n"
                else:
                    report += "<b>📌 Best/Worst Trades</b>\n"
                    report += f"Best Trade: <b>{best_trade['pair']}</b> +{best_trade['profit_ratio'] * 100:.2f}% (+{best_trade['profit_abs']:.2f} USDT)\n"
                    report += f"Worst Trade: <b>{worst_trade['pair']}</b> {worst_trade['profit_ratio'] * 100:+.2f}% ({worst_trade['profit_abs']:+.2f} USDT)\n"
        else:
            # 如果没有交易列表，尝试从统计数据获取
            best = data.get('best_pair_profit_ratio') or 0
            worst = data.get('worst_pair_profit_ratio') or 0

            if best != 0 or worst != 0:
                if lang == 'zh':
                    report += "<b>📌 极值交易</b>\n"
                    report += f"最佳单笔: +{best * 100:.2f}%\n"
                    report += f"最差单笔: {worst * 100:+.2f}%\n"
                else:
                    report += "<b>📌 Best/Worst Trades</b>\n"
                    report += f"Best: +{best * 100:.2f}%\n"
                    report += f"Worst: {worst * 100:+.2f}%\n"
    except Exception as e:
        logger.warning(f"获取极值交易失败: {e}")

    return report


def format_performance_improved(data: Any, lang: str = 'zh') -> str:
    """
    增强版性能格式化 - 支持双语

    Args:
        data: 性能数据列表
        lang: 语言 ('zh' 或 'en')

    Returns:
        格式化后的性能报告
    """
    if not data:
        return "📊 暂无性能数据" if lang == 'zh' else "📊 No performance data"

    if isinstance(data, dict) and 'error' in data:
        return f"❌ {data['error']}"

    performances = data if isinstance(data, list) else []

    if not performances:
        return "📊 暂无性能数据" if lang == 'zh' else "📊 No performance data"

    if lang == 'zh':
        report = "📊 <b>各币种性能详情</b>\n"
    else:
        report = "📊 <b>Performance by Pair</b>\n"

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

        # 盈亏标识
        if profit_abs > 0:
            profit_emoji = "🟢"
            winning_pairs += 1
        elif profit_abs < 0:
            profit_emoji = "🔴"
            losing_pairs += 1
        else:
            profit_emoji = "⚪"

        # 显示币种信息
        report += f"{profit_emoji} <b>{pair}</b>\n"

        if lang == 'zh':
            report += f"  交易次数: {count}笔\n"
            report += f"  总盈亏: {profit_abs:+.2f} USDT ({profit_pct:+.2f}%)\n"
            if count > 0:
                avg_profit = profit_abs / count
                report += f"  单笔平均: {avg_profit:+.2f} USDT\n"
        else:
            report += f"  Trades: {count}\n"
            report += f"  Total P/L: {profit_abs:+.2f} USDT ({profit_pct:+.2f}%)\n"
            if count > 0:
                avg_profit = profit_abs / count
                report += f"  Avg per Trade: {avg_profit:+.2f} USDT\n"

        report += "\n"

        # 累计统计
        total_trades += count
        total_profit_abs += profit_abs
        all_profits_abs.append(profit_abs)

    # 总体统计
    if lang == 'zh':
        report += "<b>📈 总体统计</b>\n"
        report += f"总交易: {total_trades}笔\n"
        report += f"总盈亏: {total_profit_abs:+.2f} USDT\n"
    else:
        report += "<b>📈 Overall Statistics</b>\n"
        report += f"Total Trades: {total_trades}\n"
        report += f"Total P/L: {total_profit_abs:+.2f} USDT\n"

    # 单笔平均
    if total_trades > 0:
        avg_per_trade = total_profit_abs / total_trades
        if lang == 'zh':
            report += f"单笔平均: {avg_per_trade:+.2f} USDT\n"
        else:
            report += f"Avg per Trade: {avg_per_trade:+.2f} USDT\n"

    # 胜率
    if len(performances) > 0:
        win_rate = (winning_pairs / len(performances)) * 100
        if lang == 'zh':
            report += f"<b>胜率: {win_rate:.1f}%</b> ({winning_pairs}盈/{losing_pairs}亏)\n"
        else:
            report += f"<b>Win Rate: {win_rate:.1f}%</b> ({winning_pairs}W/{losing_pairs}L)\n"

    # 最佳/最差表现
    if all_profits_abs:
        best_profit = max(all_profits_abs)
        worst_profit = min(all_profits_abs)
        if best_profit > 0 or worst_profit < 0:
            if lang == 'zh':
                report += f"\n最佳币种收益: +{best_profit:.2f} USDT\n"
                report += f"最差币种收益: {worst_profit:+.2f} USDT\n"
            else:
                report += f"\nBest Pair: +{best_profit:.2f} USDT\n"
                report += f"Worst Pair: {worst_profit:+.2f} USDT\n"

    return report


class PerformanceFormatter:
    """性能数据格式化器 - 兼容原有接口"""

    @staticmethod
    def format_enhanced_performance(data: Any, balance_data: Optional[Dict] = None, lang: str = 'zh') -> str:
        """
        增强版性能格式化

        Args:
            data: 性能数据或利润数据
            balance_data: 余额数据(可选)
            lang: 语言 ('zh' 或 'en')

        Returns:
            格式化的报告
        """
        # 如果 data 是列表，说明是性能数据，需要转换格式
        if isinstance(data, list):
            # 转换为利润统计格式
            trades_data = data
            profit_data = {
                'trade_count': sum(t.get('count', 0) or t.get('trades', 0) for t in data),
                'winning_trades': sum(1 for t in data if (t.get('profit', 0) or t.get('profit_ratio', 0)) > 0),
                'losing_trades': sum(1 for t in data if (t.get('profit', 0) or t.get('profit_ratio', 0)) < 0),
                'profit_all_coin': sum(t.get('profit_abs', 0) for t in data),
                'profit_all_percent': sum(t.get('profit', 0) or t.get('profit_ratio', 0) for t in data) * 100,
            }
            return format_profit_improved(profit_data, trades_data, lang=lang)
        else:
            # 已经是利润数据格式
            return format_profit_improved(data, balance_data, lang=lang)

    @staticmethod
    def format_simple_performance(data: Any, lang: str = 'zh') -> str:
        """简化版性能格式化"""
        return PerformanceFormatter.format_enhanced_performance(data, None, lang)

    @staticmethod
    def format_profit_summary(profit_data: Dict, lang: str = 'zh') -> str:
        """格式化利润摘要"""
        return format_profit_improved(profit_data, None, lang=lang)


# 便捷函数
def create_improved_formatters():
    """创建改进的格式化器集合"""
    return {
        'status': format_status_improved,
        'balance': format_balance_improved,
        'profit': format_profit_improved
    }