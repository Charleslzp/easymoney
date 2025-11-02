"""
freqtrade_api_client.py - Freqtrade REST API 客户端(带认证)
修改: 集成 improved_performance_formatter
"""

import requests
from requests.auth import HTTPBasicAuth
import logging
from typing import Dict, List, Tuple, Optional, Any

# 导入增强的性能格式化器
try:
    from improved_performance_formatter  import  PerformanceFormatter
    HAS_ENHANCED_FORMATTER = True
except ImportError:
    HAS_ENHANCED_FORMATTER = False
    logging.warning("未找到 improved_performance_formatter,使用原始格式化")

logger = logging.getLogger(__name__)


class FreqtradeAPIClient:
    """Freqtrade REST API 客户端"""

    def __init__(self):
        """初始化 API 客户端"""
        self.base_url_template = "http://localhost:{port}/api/v1"
        self.timeout = 10
        # API 认证信息
        self.username = "pythonuser"
        self.password = "lzplzp123123"

        # 初始化性能格式化器
        if HAS_ENHANCED_FORMATTER:
            self.performance_formatter = PerformanceFormatter
            logger.info("已加载增强的性能格式化器")
        else:
            self.performance_formatter = None

    def _get_api_port(self, user_id: int) -> int:
        """获取用户的 API 端口"""
        return 8080 + (user_id % 1000)

    def _get_base_url(self, user_id: int) -> str:
        """获取用户的 API 基础 URL"""
        port = self._get_api_port(user_id)
        return self.base_url_template.format(port=port)

    def _get_auth(self, user_id: int) -> HTTPBasicAuth:
        """获取认证信息"""
        return HTTPBasicAuth(self.username, self.password)

    def _request(
        self,
        user_id: int,
        endpoint: str,
        method: str = "GET",
        data: dict = None
    ) -> Tuple[bool, Any]:
        """
        发送 API 请求(带认证)

        Args:
            user_id: 用户 ID
            endpoint: API 端点
            method: HTTP 方法
            data: 请求数据

        Returns:
            (成功标志, 响应数据)
        """
        base_url = self._get_base_url(user_id)
        url = f"{base_url}/{endpoint}"
        auth = self._get_auth(user_id)

        try:
            if method == "GET":
                response = requests.get(url, auth=auth, timeout=self.timeout)
            elif method == "POST":
                response = requests.post(url, json=data, auth=auth, timeout=self.timeout)
            else:
                return False, {"error": f"不支持的方法: {method}"}

            if response.status_code == 200:
                return True, response.json()
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.error(f"API 请求失败: {error_msg}")
                return False, {"error": error_msg}

        except requests.exceptions.ConnectionError:
            return False, {"error": "无法连接到 Freqtrade API，请确保服务已启动且 API 已启用"}
        except requests.exceptions.Timeout:
            return False, {"error": "API 请求超时"}
        except Exception as e:
            logger.error(f"API 请求异常: {e}")
            return False, {"error": str(e)}

    # ========== Freqtrade API 端点 ==========

    def ping(self, user_id: int) -> Tuple[bool, Dict]:
        """Ping - 测试 API 连接"""
        return self._request(user_id, "ping")

    def version(self, user_id: int) -> Tuple[bool, Dict]:
        """获取版本信息"""
        return self._request(user_id, "version")

    def show_config(self, user_id: int) -> Tuple[bool, Dict]:
        """显示配置"""
        return self._request(user_id, "show_config")

    def status(self, user_id: int) -> Tuple[bool, Dict]:
        """获取当前交易状态(持仓)"""
        return self._request(user_id, "status")

    def balance(self, user_id: int) -> Tuple[bool, Dict]:
        """获取账户余额"""
        return self._request(user_id, "balance")

    def profit(self, user_id: int) -> Tuple[bool, Dict]:
        """获取利润统计"""
        return self._request(user_id, "profit")

    def performance(self, user_id: int) -> Tuple[bool, Dict]:
        """获取各币种性能"""
        return self._request(user_id, "performance")

    def daily(self, user_id: int, days: int = 7) -> Tuple[bool, Dict]:
        """获取每日统计"""
        return self._request(user_id, f"daily?timescale={days}")

    def count(self, user_id: int) -> Tuple[bool, Dict]:
        """获取交易计数"""
        return self._request(user_id, "count")

    def locks(self, user_id: int) -> Tuple[bool, Dict]:
        """获取交易对锁定信息"""
        return self._request(user_id, "locks")

    def trades(self, user_id: int, limit: int = 50) -> Tuple[bool, Dict]:
        """获取交易历史"""
        return self._request(user_id, f"trades?limit={limit}")

    def trade(self, user_id: int, trade_id: int) -> Tuple[bool, Dict]:
        """获取特定交易详情"""
        return self._request(user_id, f"trade/{trade_id}")

    def whitelist(self, user_id: int) -> Tuple[bool, Dict]:
        """获取交易对白名单"""
        return self._request(user_id, "whitelist")

    def blacklist(self, user_id: int) -> Tuple[bool, Dict]:
        """获取交易对黑名单"""
        return self._request(user_id, "blacklist")

    def stats(self, user_id: int) -> Tuple[bool, Dict]:
        """获取统计信息"""
        return self._request(user_id, "stats")

    # ========== 控制命令 ==========

    def start_trading(self, user_id: int) -> Tuple[bool, Dict]:
        """启动交易"""
        return self._request(user_id, "start", method="POST")

    def stop_trading(self, user_id: int) -> Tuple[bool, Dict]:
        """停止交易"""
        return self._request(user_id, "stop", method="POST")

    def reload_config(self, user_id: int) -> Tuple[bool, Dict]:
        """重新加载配置"""
        return self._request(user_id, "reload_config", method="POST")

    def stopbuy(self, user_id: int) -> Tuple[bool, Dict]:
        """停止买入"""
        return self._request(user_id, "stopbuy", method="POST")

    def forcebuy(self, user_id: int, pair: str, price: float = None) -> Tuple[bool, Dict]:
        """强制买入"""
        data = {"pair": pair}
        if price:
            data["price"] = price
        return self._request(user_id, "forcebuy", method="POST", data=data)

    def forcesell(self, user_id: int, trade_id: int) -> Tuple[bool, Dict]:
        """强制卖出"""
        return self._request(user_id, f"forcesell", method="POST", data={"tradeid": trade_id})

    # ========== 格式化输出函数 ==========

    def format_status(self, data: Any) -> str:
        """格式化持仓状态"""
        if not data:
            return "📊 当前无持仓"

        if isinstance(data, dict) and 'error' in data:
            return f"❌ {data['error']}"

        trades = data if isinstance(data, list) else []

        if not trades:
            return "📊 当前无持仓"

        report = "📊 <b>当前持仓</b>\n"
        report += "=" * 30 + "\n\n"

        for trade in trades:
            direction = "📻" if trade.get('is_short') else "📺"
            profit_pct = trade.get('profit_pct', 0) or trade.get('profit_ratio', 0) * 100
            profit_abs = trade.get('profit_abs', 0) or trade.get('profit_abs_total', 0)

            report += f"{direction} <b>{trade.get('pair')}</b>\n"
            report += f"  开仓: {trade.get('open_rate', 0):.6f}\n"
            report += f"  当前: {trade.get('current_rate', 0):.6f}\n"
            report += f"  盈亏: {profit_pct:+.2f}% ({profit_abs:+.2f} USDT)\n"
            report += f"  金额: {trade.get('stake_amount', 0):.2f} USDT\n"
            report += f"  时间: {trade.get('open_date', 'N/A')}\n\n"

        return report

    def format_profit(self, data: Dict) -> str:
        """格式化利润统计"""
        if not data or isinstance(data, dict) and 'error' in data:
            return f"❌ {data.get('error', '无法获取利润数据')}"

        report = "💰 <b>利润统计</b>\n"
        report += "=" * 30 + "\n\n"

        # 交易统计
        trade_count = data.get('trade_count', 0) or data.get('closed_trade_count', 0)
        winning = data.get('winning_trades', 0)
        losing = data.get('losing_trades', 0)

        report += f"总交易: {trade_count} 笔\n"
        report += f"盈利: {winning} 笔 | 亏损: {losing} 笔\n"

        if trade_count > 0:
            win_rate = (winning / trade_count * 100) if trade_count > 0 else 0
            report += f"胜率: {win_rate:.1f}%\n\n"
        else:
            report += "\n"

        # 利润统计
        profit_abs = data.get('profit_all_coin', 0) or data.get('profit_closed_coin', 0)
        profit_pct = data.get('profit_all_percent', 0) or data.get('profit_closed_percent', 0)

        report += f"总利润: <b>{profit_abs:.2f} USDT</b>\n"
        report += f"收益率: <b>{profit_pct:.2f}%</b>\n\n"

        # 最佳/最差交易
        best = data.get('best_pair_profit_ratio', 0)
        worst = data.get('worst_pair_profit_ratio', 0)

        if best or worst:
            report += f"最佳交易: +{best * 100:.2f}%\n"
            report += f"最差交易: {worst * 100:+.2f}%\n"

        return report

    def format_performance(self, data: Any, user_id: int = None) -> str:
        """
        格式化性能数据 - 使用增强版格式化器（向后兼容）

        Args:
            data: 性能数据
            user_id: 用户ID(可选,用于获取余额数据)
        """
        # 如果有增强格式化器且提供了user_id,尝试获取余额数据
        if self.performance_formatter and user_id:
            try:
                balance_success, balance_data = self.balance(user_id)
                balance_info = balance_data if balance_success else None
            except Exception as e:
                logger.warning(f"获取余额数据失败: {e}, 使用无余额模式")
                balance_info = None

            return self.performance_formatter.format_enhanced_performance(
                data,
                balance_info
            )
        elif self.performance_formatter:
            # 有格式化器但没有user_id,使用无余额模式
            return self.performance_formatter.format_enhanced_performance(data, None)

        # 否则使用原始格式化
        return self._format_performance_original(data)

    def _format_performance_original(self, data: Any) -> str:
        """原始性能格式化(向后兼容)"""
        if not data:
            return "📊 暂无性能数据"

        if isinstance(data, dict) and 'error' in data:
            return f"❌ {data['error']}"

        performances = data if isinstance(data, list) else []

        if not performances:
            return "📊 暂无性能数据"

        report = "📊 <b>各币种性能</b>\n"
        report += "=" * 30 + "\n\n"

        for perf in performances[:15]:
            profit = perf.get('profit', 0) or perf.get('profit_ratio', 0)
            profit_pct = profit * 100 if profit < 1 else profit
            count = perf.get('count', 0) or perf.get('trades', 0)

            emoji = "🟢" if profit_pct > 0 else "🔴"

            report += f"{emoji} <b>{perf.get('pair')}</b>\n"
            report += f"  交易: {count}次 | 利润: {profit_pct:+.2f}%\n\n"

        return report

    def format_balance(self, data: Dict) -> str:
        """格式化余额信息"""
        if not data or 'error' in data:
            return f"❌ {data.get('error', '无法获取余额数据')}"

        currencies = data.get('currencies', [])
        total = data.get('total', 0)

        report = "💰 <b>账户余额</b>\n"
        report += "=" * 30 + "\n\n"

        report += f"总价值: <b>{total:.2f} USDT</b>\n\n"

        # 只显示有余额的币种
        has_balance = False
        for currency in currencies:
            if currency.get('free', 0) > 0.001 or currency.get('used', 0) > 0.001:
                has_balance = True
                total_curr = currency.get('total', 0)
                free = currency.get('free', 0)
                used = currency.get('used', 0)

                report += f"<b>{currency.get('currency')}</b>\n"
                report += f"  可用: {free:.6f}\n"
                report += f"  冻结: {used:.6f}\n"
                report += f"  总计: {total_curr:.6f}\n\n"

        if not has_balance:
            report += "暂无余额数据"

        return report

    def format_daily(self, data: Dict) -> str:
        """格式化每日统计"""
        if not data or 'error' in data:
            return f"❌ {data.get('error', '无法获取每日数据')}"

        daily_data = data.get('data', [])

        if not daily_data:
            return "📊 暂无每日数据"

        report = "📅 <b>每日统计</b>\n"
        report += "=" * 30 + "\n\n"

        for day in daily_data[-7:]:  # 最近7天
            date = day.get('date', 'N/A')
            profit = day.get('abs_profit', 0)
            trades = day.get('trade_count', 0)

            emoji = "🟢" if profit > 0 else "🔴" if profit < 0 else "⚪"

            report += f"{emoji} <b>{date}</b>\n"
            report += f"  交易: {trades}笔 | 盈亏: {profit:+.2f} USDT\n\n"

        return report


# 便捷函数
def create_api_client():
    """创建 API 客户端实例"""
    return FreqtradeAPIClient()


# 测试函数
def test_api_client(user_id: int):
    """测试 API 客户端"""
    client = FreqtradeAPIClient()

    print("=" * 50)
    print(f"测试 Freqtrade API 客户端 (用户 {user_id})")
    print(f"API URL: {client._get_base_url(user_id)}")
    print(f"用户名: {client.username}")
    print("=" * 50)

    # 测试连接
    print("\n1. Ping 测试:")
    success, data = client.ping(user_id)
    print(f"成功: {success}, 数据: {data}")

    # 测试状态
    print("\n2. 持仓状态:")
    success, data = client.status(user_id)
    if success:
        print(client.format_status(data))
    else:
        print(f"失败: {data}")

    # 测试利润
    print("\n3. 利润统计:")
    success, data = client.profit(user_id)
    if success:
        print(client.format_profit(data))
    else:
        print(f"失败: {data}")

    # 测试性能(使用增强格式化)
    print("\n4. 性能统计:")
    success, data = client.performance(user_id)
    if success:
        print(client.format_performance(data, user_id))
    else:
        print(f"失败: {data}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_user_id = int(sys.argv[1])
        test_api_client(test_user_id)
    else:
        print("用法: python freqtrade_api_client.py <user_id>")