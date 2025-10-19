"""
portainer_manager.py - Portainer API管理模块
通过Portainer REST API管理Docker Swarm服务
"""

import requests
import json
from typing import Optional, Dict, List, Tuple, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class PortainerManager:
    """Portainer API管理类"""
    
    def __init__(self, base_url: str = "http://localhost:9000", username: str = "admin", password: str = ""):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.token = None
        self.endpoint_id = 1  # 默认端点ID
        
        # 配置重试策略
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def authenticate(self) -> bool:
        """登录Portainer获取JWT Token"""
        url = f"{self.base_url}/api/auth"
        payload = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            response = self.session.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('jwt')
                print("[INFO] Portainer认证成功")
                return True
            else:
                print(f"[ERROR] Portainer认证失败: {response.status_code}")
                return False
        except Exception as e:
            print(f"[ERROR] 连接Portainer失败: {e}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        if not self.token:
            self.authenticate()
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """统一的请求方法"""
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        try:
            response = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
            
            # Token过期，重新认证
            if response.status_code == 401:
                print("[INFO] Token过期，重新认证...")
                if self.authenticate():
                    headers = self._get_headers()
                    response = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
            
            return response
        except Exception as e:
            print(f"[ERROR] 请求失败: {e}")
            return None
    
    def list_services(self, filters: Dict = None) -> List[Dict]:
        """列出所有服务"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/services"
        
        params = {}
        if filters:
            params['filters'] = json.dumps(filters)
        
        response = self._make_request('GET', endpoint, params=params)
        
        if response and response.status_code == 200:
            return response.json()
        return []
    
    def get_service(self, service_id: str) -> Optional[Dict]:
        """获取服务详情"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/services/{service_id}"
        response = self._make_request('GET', endpoint)
        
        if response and response.status_code == 200:
            return response.json()
        return None
    
    def create_service(self, service_spec: Dict) -> Tuple[bool, str]:
        """创建服务"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/services/create"
        
        response = self._make_request('POST', endpoint, json=service_spec)
        
        if response and response.status_code in [200, 201]:
            data = response.json()
            service_id = data.get('ID', 'unknown')
            return True, f"服务创建成功: {service_id}"
        elif response:
            return False, f"创建失败: {response.text}"
        else:
            return False, "请求失败"
    
    def update_service(self, service_id: str, version: int, service_spec: Dict) -> Tuple[bool, str]:
        """更新服务"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/services/{service_id}/update"
        params = {'version': version}
        
        response = self._make_request('POST', endpoint, params=params, json=service_spec)
        
        if response and response.status_code == 200:
            return True, "服务更新成功"
        elif response:
            return False, f"更新失败: {response.text}"
        else:
            return False, "请求失败"
    
    def delete_service(self, service_id: str) -> Tuple[bool, str]:
        """删除服务"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/services/{service_id}"
        
        response = self._make_request('DELETE', endpoint)
        
        if response and response.status_code in [200, 204]:
            return True, "服务删除成功"
        elif response:
            return False, f"删除失败: {response.text}"
        else:
            return False, "请求失败"
    
    def get_service_logs(self, service_id: str, lines: int = 50) -> str:
        """获取服务日志"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/services/{service_id}/logs"
        params = {
            'stdout': 1,
            'stderr': 1,
            'tail': lines,
            'timestamps': 1
        }
        
        response = self._make_request('GET', endpoint, params=params)
        
        if response and response.status_code == 200:
            return response.text
        return "无法获取日志"
    
    def get_service_tasks(self, service_id: str) -> List[Dict]:
        """获取服务任务列表"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/tasks"
        filters = {'service': [service_id]}
        params = {'filters': json.dumps(filters)}
        
        response = self._make_request('GET', endpoint, params=params)
        
        if response and response.status_code == 200:
            return response.json()
        return []
    
    def scale_service(self, service_id: str, replicas: int) -> Tuple[bool, str]:
        """扩展服务副本数"""
        # 先获取服务当前配置
        service = self.get_service(service_id)
        if not service:
            return False, "服务不存在"
        
        # 更新副本数
        version = service['Version']['Index']
        spec = service['Spec']
        spec['Mode']['Replicated']['Replicas'] = replicas
        
        return self.update_service(service_id, version, spec)
    
    def get_swarm_info(self) -> Optional[Dict]:
        """获取Swarm集群信息"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/swarm"
        response = self._make_request('GET', endpoint)
        
        if response and response.status_code == 200:
            return response.json()
        return None
    
    def list_nodes(self) -> List[Dict]:
        """列出Swarm节点"""
        endpoint = f"/api/endpoints/{self.endpoint_id}/docker/nodes"
        response = self._make_request('GET', endpoint)
        
        if response and response.status_code == 200:
            return response.json()
        return []
    
    def get_endpoint_info(self) -> Optional[Dict]:
        """获取端点信息"""
        endpoint = f"/api/endpoints/{self.endpoint_id}"
        response = self._make_request('GET', endpoint)
        
        if response and response.status_code == 200:
            return response.json()
        return None
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            if not self.token:
                return self.authenticate()
            
            endpoint = f"/api/endpoints/{self.endpoint_id}"
            response = self._make_request('GET', endpoint)
            return response is not None and response.status_code == 200
        except:
            return False
    
    def create_freqtrade_service_spec(self, user_id: int, user_dir: str, strategy_file: str) -> Dict:
        """创建Freqtrade服务规格"""
        service_name = f"freqtrade_{user_id}"
        
        return {
            "Name": service_name,
            "Labels": {
                "app": "freqtrade",
                "user_id": str(user_id),
                "managed_by": "telegram_bot"
            },
            "TaskTemplate": {
                "ContainerSpec": {
                    "Image": "freqtradeorg/freqtrade:stable",
                    "Args": ["trade"],
                    "Env": [
                        "FREQTRADE__STRATEGY=MyStrategy"
                    ],
                    "Mounts": [
                        {
                            "Type": "bind",
                            "Source": user_dir,
                            "Target": "/freqtrade/user_data",
                            "ReadOnly": False
                        },
                        {
                            "Type": "bind",
                            "Source": strategy_file,
                            "Target": "/freqtrade/user_data/strategies/MyStrategy.py",
                            "ReadOnly": True
                        }
                    ],
                    "Labels": {
                        "user_id": str(user_id)
                    }
                },
                "RestartPolicy": {
                    "Condition": "on-failure",
                    "Delay": 5000000000,
                    "MaxAttempts": 3
                },
                "Resources": {
                    "Limits": {
                        "NanoCPUs": 1000000000,
                        "MemoryBytes": 536870912
                    },
                    "Reservations": {
                        "NanoCPUs": 500000000,
                        "MemoryBytes": 268435456
                    }
                }
            },
            "Mode": {
                "Replicated": {
                    "Replicas": 1
                }
            }
        }
