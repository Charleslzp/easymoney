"""
freqtrade_commander.py - Freqtrade 命令执行器
通过 Docker API 在容器内执行 Freqtrade 命令
"""

import docker
import logging
from typing import Tuple, Optional, Dict, Any
import json
import time

logger = logging.getLogger(__name__)


class FreqtradeCommander:
    """Freqtrade 命令执行器"""

    def __init__(self):
        """初始化 Docker 客户端"""
        try:
            self.client = docker.from_env()
            logger.info("[INFO] Docker 客户端连接成功")
        except Exception as e:
            logger.error(f"[ERROR] Docker 客户端连接失败: {e}")
            self.client = None

    def _get_container_name(self, user_id: int) -> str:
        """获取用户容器名称"""
        return f"freqtrade_{user_id}"

    def _find_container(self, user_id: int):
        """查找用户的容器"""
        if not self.client:
            return None

        service_name = self._get_container_name(user_id)

        try:
            # 尝试通过服务名查找
            service = self.client.services.get(service_name)
            tasks = service.tasks(filters={'desired-state': 'running'})

            if tasks:
                # 获取容器 ID
                container_id = tasks[0]['Status']['ContainerStatus']['ContainerID']
                return self.client.containers.get(container_id)

            return None

        except docker.errors.NotFound:
            logger.warning(f"[WARN] 服务 {service_name} 不存在")
            return None
        except Exception as e:
            logger.error(f"[ERROR] 查找容器失败: {e}")
            return None

    def execute_command(
            self,
            user_id: int,
            command: str,
            timeout: int = 30
    ) -> Tuple[bool, str]:
        """
        在容器内执行 Freqtrade 命令

        Args:
            user_id: 用户 ID
            command: 要执行的命令（不包含 freqtrade 前缀）
            timeout: 超时时间（秒）

        Returns:
            (成功标志, 输出内容)
        """
        container = self._find_container(user_id)

        if not container:
            return False, "容器未运行或不存在"

        try:
            # 构建完整命令
            full_command = f"freqtrade {command}"

            logger.info(f"[INFO] 执行命令: {full_command}")

            # 执行命令
            exec_result = container.exec_run(
                full_command,
                stdout=True,
                stderr=True,
                demux=True,
                workdir='/freqtrade'
            )

            # 解析输出
            exit_code = exec_result.exit_code
            output = exec_result.output

            # 处理输出（可能是 tuple 或 bytes）
            if isinstance(output, tuple):
                stdout, stderr = output
                stdout_text = stdout.decode('utf-8') if stdout else ""
                stderr_text = stderr.decode('utf-8') if stderr else ""
                output_text = stdout_text + stderr_text
            else:
                output_text = output.decode('utf-8') if output else ""

            if exit_code == 0:
                return True, output_text
            else:
                return False, f"命令执行失败 (退出码: {exit_code})\n{output_text}"

        except Exception as e:
            logger.error(f"[ERROR] 执行命令失败: {e}")
            return False, f"执行命令异常: {str(e)}"

    # ========== Freqtrade 常用命令封装 ==========

    def show_config(self, user_id: int) -> Tuple[bool, str]:
        """显示配置"""
        return self.execute_command(
            user_id,
            "show-config -c /freqtrade/custom_config/config.json"
        )

    def list_strategies(self, user_id: int) -> Tuple[bool, str]:
        """列出可用策略"""
        return self.execute_command(user_id, "list-strategies")

    def list_exchanges(self, user_id: int) -> Tuple[bool, str]:
        """列出支持的交易所"""
        return self.execute_command(user_id, "list-exchanges")

    def show_trades(self, user_id: int, limit: int = 10) -> Tuple[bool, str]:
        """
        显示交易记录

        Args:
            user_id: 用户 ID
            limit: 显示记录数
        """
        return self.execute_command(
            user_id,
            f"show-trades --db-url sqlite:////freqtrade/custom_database/tradesv3.sqlite --trade-ids --limit {limit}"
        )

    def profit_show(self, user_id: int) -> Tuple[bool, str]:
        """显示利润统计"""
        return self.execute_command(
            user_id,
            "profit --db-url sqlite:////freqtrade/custom_database/tradesv3.sqlite"
        )

    def performance_show(self, user_id: int) -> Tuple[bool, str]:
        """显示各币种性能"""
        return self.execute_command(
            user_id,
            "performance --db-url sqlite:////freqtrade/custom_database/tradesv3.sqlite"
        )

    def balance_show(self, user_id: int) -> Tuple[bool, str]:
        """显示账户余额"""
        return self.execute_command(
            user_id,
            "balance -c /freqtrade/custom_config/config.json"
        )

    def status_show(self, user_id: int) -> Tuple[bool, str]:
        """显示当前状态（持仓）"""
        return self.execute_command(
            user_id,
            "status -c /freqtrade/custom_config/config.json"
        )

    def count_show(self, user_id: int) -> Tuple[bool, str]:
        """显示交易计数"""
        return self.execute_command(
            user_id,
            "count -c /freqtrade/custom_config/config.json"
        )

    def locks_show(self, user_id: int) -> Tuple[bool, str]:
        """显示交易对锁定信息"""
        return self.execute_command(
            user_id,
            "locks --db-url sqlite:////freqtrade/custom_database/tradesv3.sqlite"
        )

    def version_show(self, user_id: int) -> Tuple[bool, str]:
        """显示 Freqtrade 版本"""
        return self.execute_command(user_id, "--version")

    def backtest(
            self,
            user_id: int,
            strategy: str = "MyStrategy",
            timerange: str = None,
            timeframe: str = "1m"
    ) -> Tuple[bool, str]:
        """
        运行回测

        Args:
            user_id: 用户 ID
            strategy: 策略名称
            timerange: 时间范围 (如: 20231201-20231231)
            timeframe: 时间周期
        """
        cmd = f"backtesting --strategy {strategy} --timeframe {timeframe}"

        if timerange:
            cmd += f" --timerange {timerange}"

        cmd += " -c /freqtrade/custom_config/config.json"

        return self.execute_command(user_id, cmd, timeout=300)  # 回测可能需要更长时间

    def download_data(
            self,
            user_id: int,
            pairs: str = None,
            timeframe: str = "1m",
            days: int = 30
    ) -> Tuple[bool, str]:
        """
        下载历史数据

        Args:
            user_id: 用户 ID
            pairs: 交易对（逗号分隔，如 "BTC/USDT,ETH/USDT"）
            timeframe: 时间周期
            days: 下载天数
        """
        cmd = f"download-data --timeframe {timeframe} --days {days}"

        if pairs:
            cmd += f" --pairs {pairs}"

        cmd += " -c /freqtrade/custom_config/config.json"

        return self.execute_command(user_id, cmd, timeout=600)

    def custom_command(self, user_id: int, command: str) -> Tuple[bool, str]:
        """
        执行自定义命令

        Args:
            user_id: 用户 ID
            command: 完整的 Freqtrade 命令（不含 freqtrade 前缀）
        """
        return self.execute_command(user_id, command)

    # ========== 高级功能 ==========

    def get_whitelist(self, user_id: int) -> Tuple[bool, list]:
        """获取交易对白名单"""
        success, output = self.execute_command(
            user_id,
            "show-config -c /freqtrade/custom_config/config.json"
        )

        if not success:
            return False, []

        try:
            # 解析配置中的 pair_whitelist
            # 这里需要根据实际输出格式解析
            lines = output.split('\n')
            whitelist = []

            in_whitelist = False
            for line in lines:
                if 'pair_whitelist' in line:
                    in_whitelist = True
                elif in_whitelist:
                    if line.strip().startswith('-'):
                        pair = line.strip().lstrip('- ').strip()
                        whitelist.append(pair)
                    elif not line.strip().startswith(' '):
                        break

            return True, whitelist

        except Exception as e:
            logger.error(f"解析白名单失败: {e}")
            return False, []

    def parse_profit_output(self, output: str) -> Dict[str, Any]:
        """解析 profit 命令输出"""
        try:
            result = {
                'total_profit': 0.0,
                'total_profit_percent': 0.0,
                'trade_count': 0,
                'winning_trades': 0,
                'losing_trades': 0
            }

            lines = output.split('\n')
            for line in lines:
                if 'Total profit' in line or '总利润' in line:
                    # 提取数字
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if 'USDT' in part or '$' in part:
                            try:
                                result['total_profit'] = float(parts[i - 1].replace(',', ''))
                            except:
                                pass

                if 'Avg profit' in line or '平均利润' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if '%' in part:
                            try:
                                result['total_profit_percent'] = float(parts[i].replace('%', ''))
                            except:
                                pass

                if 'Total trades' in line or '总交易' in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        try:
                            result['trade_count'] = int(parts[1].strip().split()[0])
                        except:
                            pass

                if 'Winning trades' in line or '盈利交易' in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        try:
                            result['winning_trades'] = int(parts[1].strip().split()[0])
                        except:
                            pass

                if 'Losing trades' in line or '亏损交易' in line:
                    parts = line.split(':')
                    if len(parts) > 1:
                        try:
                            result['losing_trades'] = int(parts[1].strip().split()[0])
                        except:
                            pass

            return result

        except Exception as e:
            logger.error(f"解析 profit 输出失败: {e}")
            return {}

    def parse_performance_output(self, output: str) -> list:
        """解析 performance 命令输出"""
        try:
            performances = []
            lines = output.split('\n')

            # 跳过表头，查找数据行
            for line in lines:
                if '|' in line and 'Pair' not in line and '---' not in line:
                    parts = [p.strip() for p in line.split('|') if p.strip()]

                    if len(parts) >= 3:
                        try:
                            performances.append({
                                'pair': parts[0],
                                'trades': int(parts[1]),
                                'profit': float(parts[2].replace('%', '').strip())
                            })
                        except:
                            pass

            return performances

        except Exception as e:
            logger.error(f"解析 performance 输出失败: {e}")
            return []

    def health_check(self, user_id: int) -> bool:
        """健康检查 - 检查容器是否可以执行命令"""
        success, _ = self.execute_command(user_id, "--version")
        return success


# 便捷函数
def create_commander():
    """创建命令执行器实例"""
    return FreqtradeCommander()


# 测试函数
def test_commander(user_id: int):
    """测试命令执行器"""
    commander = FreqtradeCommander()

    print("=" * 50)
    print("测试 Freqtrade 命令执行器")
    print("=" * 50)

    # 测试版本
    print("\n1. 测试版本命令:")
    success, output = commander.version_show(user_id)
    print(f"成功: {success}")
    print(f"输出:\n{output}")

    # 测试状态
    print("\n2. 测试状态命令:")
    success, output = commander.status_show(user_id)
    print(f"成功: {success}")
    print(f"输出:\n{output}")

    # 测试利润
    print("\n3. 测试利润命令:")
    success, output = commander.profit_show(user_id)
    print(f"成功: {success}")
    print(f"输出:\n{output}")

    # 测试性能
    print("\n4. 测试性能命令:")
    success, output = commander.performance_show(user_id)
    print(f"成功: {success}")
    print(f"输出:\n{output}")


if __name__ == "__main__":
    # 测试
    import sys

    if len(sys.argv) > 1:
        test_user_id = int(sys.argv[1])
        test_commander(test_user_id)
    else:
        print("用法: python freqtrade_commander.py <user_id>")