"""
trend_client.py - 趋势服务客户端
用于策略中访问趋势数据服务
"""

import requests
from typing import Optional, Dict, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TrendServiceClient:
    """趋势服务客户端"""

    def __init__(self, base_url: str = "http://localhost:5000", timeout: int = 5):
        """
        初始化客户端

        Args:
            base_url: 趋势服务的基础 URL
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._cache = {
            'trend': None,
            'timestamp': None,
            'cache_time': None
        }
        self._cache_ttl = 300  # 缓存5分钟

    def _make_request(self, endpoint: str, method: str = 'GET', **kwargs) -> Optional[Dict]:
        """发送HTTP请求"""
        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"请求失败: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.error(f"请求超时: {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"连接失败: {url}")
            return None
        except Exception as e:
            logger.error(f"请求异常: {e}")
            return None

    def get_trend(self, use_cache: bool = True) -> Optional[int]:
        """
        获取当前趋势信号

        Args:
            use_cache: 是否使用缓存

        Returns:
            1 (上涨) 或 -1 (下跌)，失败返回 None
        """
        # 检查缓存
        if use_cache and self._is_cache_valid():
            logger.debug("使用缓存的趋势数据")
            return self._cache['trend']

        # 请求新数据
        data = self._make_request('/api/trend')

        if data and 'trend' in data:
            # 更新缓存
            self._cache['trend'] = data['trend']
            self._cache['timestamp'] = data.get('timestamp')
            self._cache['cache_time'] = datetime.now()

            logger.info(f"获取趋势成功: {data['trend']} (更新时间: {data.get('last_update')})")
            return data['trend']

        # 如果请求失败且有缓存，使用缓存
        if self._cache['trend'] is not None:
            logger.warning("请求失败，使用缓存数据")
            return self._cache['trend']

        logger.error("获取趋势失败且无缓存")
        return None

    def get_trend_detail(self) -> Optional[Dict[str, Any]]:
        """
        获取详细的趋势信息

        Returns:
            包含 trend, macd, signal, diff 等信息的字典
        """
        return self._make_request('/api/trend')

    def get_history(self, limit: int = 10) -> Optional[list]:
        """
        获取历史趋势数据

        Args:
            limit: 返回的数据条数

        Returns:
            历史数据列表
        """
        data = self._make_request('/api/trend/history', params={'limit': limit})

        if data and 'data' in data:
            return data['data']

        return None

    def get_status(self) -> Optional[Dict[str, Any]]:
        """获取服务状态"""
        return self._make_request('/api/status')

    def health_check(self) -> bool:
        """健康检查"""
        data = self._make_request('/health')
        return data is not None and data.get('status') == 'ok'

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if self._cache['cache_time'] is None:
            return False

        elapsed = (datetime.now() - self._cache['cache_time']).total_seconds()
        return elapsed < self._cache_ttl

    def clear_cache(self):
        """清除缓存"""
        self._cache = {
            'trend': None,
            'timestamp': None,
            'cache_time': None
        }
        logger.info("缓存已清除")


# 便捷函数
def get_trend(service_url: str = "http://localhost:5000") -> Optional[int]:
    """
    快速获取趋势信号的便捷函数

    Args:
        service_url: 趋势服务URL

    Returns:
        1 (上涨) 或 -1 (下跌)，失败返回 None
    """
    client = TrendServiceClient(service_url)
    return client.get_trend()