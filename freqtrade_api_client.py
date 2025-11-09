"""
freqtrade_api_client.py - Freqtrade REST API 客户端
⭐ 增强版: 支持跨节点访问
"""

import requests
from requests.auth import HTTPBasicAuth
import logging
from typing import Dict, List, Tuple, Optional, Any
from database import Database

logger = logging.getLogger(__name__)


class FreqtradeAPIClient:
    """Freqtrade REST API 客户端 - 支持跨节点访问"""

    def __init__(self):
        """初始化 API 客户端"""
        self.timeout = 60
        # API 认证信息
        self.username = "pythonuser"
        self.password = "lzplzp123123"

        # 数据库连接
        self.db = Database()

    def _get_api_url(self, user_id: int) -> Optional[str]:
        """
        获取用户的 API URL
        ⭐ 优先使用数据库中的节点IP

        Args:
            user_id: 用户 ID

        Returns:
            完整的 API URL,如果获取失败返回 None
        """
        try:
            # 从数据库获取节点信息
            node_info = self.db.get_user_node_info(user_id)

            if node_info and node_info.get('node_ip') and node_info.get('api_port'):
                node_ip = node_info['node_ip']
                api_port = node_info['api_port']

                # 使用节点IP构建URL
                base_url = f"http://{node_ip}:{api_port}/api/v1"
                logger.debug(f"使用节点IP访问: {base_url}")
                return base_url

            # 如果没有节点信息,回退到 localhost (仅适用于本地部署)
            api_port = self._get_api_port(user_id)
            base_url = f"http://127.0.0.1:{api_port}/api/v1"
            logger.warning(f"节点信息不存在,回退到localhost: {base_url}")
            return base_url

        except Exception as e:
            logger.error(f"获取API URL失败: {e}")
            return None

    def _get_api_port(self, user_id: int) -> int:
        """获取用户的 API 端口 (备用方法)"""
        return 8080 + (user_id % 1000)

    def _get_auth(self) -> HTTPBasicAuth:
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
        发送 API 请求

        Args:
            user_id: 用户 ID
            endpoint: API 端点
            method: HTTP 方法
            data: 请求数据

        Returns:
            (成功标志, 响应数据)
        """
        # 获取 API URL
        base_url = self._get_api_url(user_id)

        if not base_url:
            return False, {"error": "无法获取API地址"}

        url = f"{base_url}/{endpoint}"

        auth = self._get_auth()
        print(f'final url is {url} aus is {auth}')

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
            # 提供更详细的错误信息
            error_msg = (
                f"无法连接到 Freqtrade API\n"
                f"URL: {url}\n"
                f"请确保:\n"
                f"1. 服务已启动\n"
                f"2. API 已启用\n"
                f"3. 节点网络可达"
            )
            logger.error(error_msg)
            return False, {"error": error_msg}

        except requests.exceptions.Timeout:
            return False, {"error": f"API 请求超时 ({self.timeout}秒)"}

        except Exception as e:
            logger.error(f"API 请求异常: {e}")
            return False, {"error": str(e)}

    # ========== Freqtrade API 端点 (保持不变) ==========

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

    def trades(self, user_id: int, limit: int = 50, open_only: bool = False) -> Tuple[bool, Dict]:
        """获取最近交易数据"""
        params = [f"limit={limit}"]
        if open_only:
            params.append("open_only=true")

        query = "?" + "&".join(params)
        return self._request(user_id, f"trades{query}")

    def performance(self, user_id: int) -> Tuple[bool, Dict]:
        """获取各币种性能"""
        return self._request(user_id, "performance")

    def daily(self, user_id: int, days: int = 7) -> Tuple[bool, Dict]:
        """获取每日统计"""
        return self._request(user_id, f"daily?timescale={days}")

    def start(self, user_id: int) -> Tuple[bool, Dict]:
        """启动交易"""
        return self._request(user_id, "start", method="POST")

    def stop(self, user_id: int) -> Tuple[bool, Dict]:
        """停止交易"""
        return self._request(user_id, "stop", method="POST")

    def reload_config(self, user_id: int) -> Tuple[bool, Dict]:
        """重新加载配置"""
        return self._request(user_id, "reload_config", method="POST")

    # ... 其他方法保持不变 ...


def test_api_client(user_id: int):
    """测试 API 客户端"""
    client = FreqtradeAPIClient()

    print("=" * 50)
    print(f"测试 Freqtrade API 客户端 (用户 {user_id})")
    print("=" * 50)

    # 测试连接
    print("\n1. Ping 测试:")
    success, data = client.ping(user_id)
    print(f"成功: {success}, 数据: {data}")

    if success:
        print("✅ API 连接正常")
    else:
        print("❌ API 连接失败")
        print(f"错误: {data.get('error')}")

    # 测试版本
    print("\n2. 版本信息:")
    success, data = client.version(user_id)
    if success:
        print(f"Freqtrade 版本: {data.get('version')}")
    else:
        print(f"失败: {data}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        test_user_id = int(sys.argv[1])
        test_api_client(test_user_id)
    else:
        print("用法: python freqtrade_api_client.py <user_id>")