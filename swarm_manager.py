"""
swarm_manager.py - Docker Swarm服务管理模块
⭐ 增强版：添加智能节点选择功能
- 监控节点容器数量
- 优先使用 Worker 节点
- 优先使用 Worker 节点
- 遵守节点容器数量限制
"""

import docker
import os
import time
from typing import Optional, Tuple, Dict, List, Any
from database import Database
from config_manager import ConfigManager

class SwarmManager:
    """Docker Swarm管理类 - 智能节点选择版"""

    def __init__(self):
        try:
            self.client = docker.from_env()
            self.db = Database()
            self.config_manager = ConfigManager()

            if not self._is_swarm_initialized():
                print("[WARN] Docker Swarm未初始化，尝试初始化...")
                self._init_swarm()

            print("[INFO] Docker Swarm客户端连接成功")
        except Exception as e:
            print(f"[ERROR] 无法连接到Docker: {e}")
            self.client = None

    def _is_swarm_initialized(self) -> bool:
        """检查Swarm是否已初始化"""
        try:
            info = self.client.info()
            return info.get('Swarm', {}).get('LocalNodeState') == 'active'
        except:
            return False

    def _init_swarm(self) -> bool:
        """初始化Docker Swarm"""
        try:
            self.client.swarm.init()
            print("[INFO] Docker Swarm初始化成功")
            return True
        except docker.errors.APIError as e:
            if 'already part of a swarm' in str(e):
                print("[INFO] Swarm已经初始化")
                return True
            print(f"[ERROR] Swarm初始化失败: {e}")
            return False

    def _get_service_name(self, user_id: int) -> str:
        """生成服务名称"""
        return f"freqtrade_{user_id}"

    def _ensure_user_directories(self, user_dir: str) -> bool:
        """确保用户目录结构存在"""
        try:
            config_dir = f"{user_dir}/config"
            os.makedirs(config_dir, exist_ok=True)

            logs_dir = f"{user_dir}/logs"
            os.makedirs(logs_dir, exist_ok=True)

            db_dir = f"{user_dir}/database"
            os.makedirs(db_dir, exist_ok=True)

            db_path = f"{db_dir}/tradesv3.sqlite"
            if not os.path.exists(db_path):
                open(db_path, 'a').close()
                print(f"[INFO] 创建数据库文件: {db_path}")

            config_file = f"{config_dir}/config.json"
            if not os.path.exists(config_file):
                print(f"[ERROR] 配置模板不存在: {config_file}")
                return False

            print(f"[INFO] 用户目录结构验证通过: {user_dir}")
            return True

        except Exception as e:
            print(f"[ERROR] 创建目录失败: {e}")
            return False

    # ========== ⭐⭐⭐ 新增：智能节点选择功能 ==========

    def _get_node_container_count(self, node_id: str) -> int:
        """
        获取指定节点上运行的 freqtrade 容器数量

        Args:
            node_id: 节点ID

        Returns:
            容器数量
        """
        try:
            # 获取所有 freqtrade 服务
            services = self.client.services.list(
                filters={'label': 'app=freqtrade'}
            )

            container_count = 0
            for service in services:
                # 获取该服务在指定节点上的任务
                tasks = service.tasks(
                    filters={
                        'node': node_id,
                        'desired-state': 'running'
                    }
                )

                # 统计运行中的任务
                running_tasks = [
                    t for t in tasks
                    if t.get('Status', {}).get('State') == 'running'
                ]
                container_count += len(running_tasks)

            return container_count

        except Exception as e:
            print(f"[ERROR] 获取节点容器数量失败: {e}")
            return 999  # 返回一个大数，避免选择这个节点

    def _get_node_max_containers(self, node: Any) -> int:
        """
        获取节点的最大容器限制

        Args:
            node: 节点对象

        Returns:
            最大容器数量
        """
        try:
            # 从节点标签获取
            labels = node.attrs.get('Spec', {}).get('Labels', {})
            if 'max_containers' in labels:
                return int(labels['max_containers'])

            # 默认值：Worker 节点 20 个，Manager 节点 5 个
            role = node.attrs.get('Spec', {}).get('Role', 'worker')
            return 5 if role == 'manager' else 20

        except Exception as e:
            print(f"[ERROR] 获取节点最大容器限制失败: {e}")
            return 20  # 默认值

    def _find_best_node(self) -> Optional[Dict[str, Any]]:
        """
        查找最佳节点
        - 优先选择 Worker 节点
        - 选择容器数量最少且未达到上限的节点

        Returns:
            节点信息字典，如果没有可用节点返回 None
        """
        try:
            # 先尝试获取 Worker 节点
            nodes = self.client.nodes.list(filters={'role': 'worker'})

            # 如果没有 Worker 节点，获取所有节点
            if not nodes:
                print("[WARN] 没有 Worker 节点，将考虑所有节点")
                nodes = self.client.nodes.list()

            available_nodes = []

            for node in nodes:
                # 只考虑 Ready 状态的节点
                if node.attrs['Status']['State'] != 'ready':
                    continue

                # 只考虑可用的节点
                availability = node.attrs['Spec'].get('Availability', 'active')
                if availability != 'active':
                    continue

                node_id = node.id
                hostname = node.attrs['Description']['Hostname']
                role = node.attrs['Spec']['Role']

                # 获取当前容器数量
                current_count = self._get_node_container_count(node_id)

                # 获取最大容器限制
                max_count = self._get_node_max_containers(node)

                # 计算可用容量
                available = max_count - current_count

                print(f"[INFO] 节点 {hostname} ({role}): {current_count}/{max_count} 容器")

                if available > 0:
                    # Worker 节点优先级更高
                    priority = 1 if role == 'worker' else 2

                    available_nodes.append({
                        'id': node_id,
                        'hostname': hostname,
                        'role': role,
                        'current': current_count,
                        'max': max_count,
                        'available': available,
                        'priority': priority
                    })

            if not available_nodes:
                print("[ERROR] 没有可用节点（所有节点都已达到容器上限）")
                return None

            # 排序：优先级 -> 负载最低
            available_nodes.sort(key=lambda x: (x['priority'], x['current']))

            best_node = available_nodes[0]
            print(f"[INFO] 选择最佳节点: {best_node['hostname']} "
                  f"({best_node['current']}/{best_node['max']} 容器)")

            return best_node

        except Exception as e:
            print(f"[ERROR] 查找最佳节点失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ========== 原有的 create_service 方法（增强版）==========

    def create_service(self, user_id: int) -> Tuple[bool, str]:
        """
        创建Freqtrade服务 - jq 注入版本 + 智能节点选择
        ⭐ 使用 jq 在容器启动时动态注入密钥
        ⭐ 智能选择负载最低的节点
        """
        if not self.client:
            return False, "Docker未连接"

        service_name = self._get_service_name(user_id)
        nfs_base = "/mnt/freqtrade-data"
        user_dir = os.path.join(nfs_base, "user_data_manager", str(user_id))

        if not self._ensure_user_directories(user_dir):
            return False, "创建用户目录失败或配置文件不存在"

        try:
            # ⭐⭐⭐ 新增：先查找最佳节点
            best_node = self._find_best_node()

            if not best_node:
                return False, (
                    "❌ 无可用节点\n\n"
                    "所有节点都已达到容器上限。\n"
                    "请联系管理员扩容或等待其他容器停止。"
                )

            # 检查服务是否已存在
            try:
                existing_service = self.client.services.get(service_name)
                # ⭐ 修改：如果服务已存在，先删除再创建
                print(f"[INFO] 发现已存在的服务，正在清理...")
                existing_service.remove()
                time.sleep(2)
            except docker.errors.NotFound:
                pass

            # 从数据库获取 API 密钥
            user = self.db.get_user_by_telegram_id(user_id)
            if not user:
                return False, "用户不存在"

            api_key = user.get('api_key')
            secret = user.get('security')

            if not api_key or not secret:
                return False, "API密钥未配置，请先使用 /bind 命令绑定"

            print(f"[INFO] 从数据库获取API密钥")
            print(f"[INFO] API Key: {api_key[:8]}...{api_key[-4:]}")
            print(f"[INFO] 🔒 使用 jq 启动脚本注入")
            print(f"[INFO] 📍 目标节点: {best_node['hostname']} ({best_node['role']})")

            from docker.types import Mount, Resources, RestartPolicy

            config_dir = f"{user_dir}/config"
            logs_dir = f"{user_dir}/logs"
            db_dir = f"{user_dir}/database"

            print(f"[INFO] 挂载配置:")
            print(f"  - 配置目录: {config_dir}")
            print(f"  - 日志目录: {logs_dir}")
            print(f"  - 数据库目录: {db_dir}")

            mounts = [
                Mount(
                    target='/freqtrade/custom_config',
                    source=config_dir,
                    type='bind',
                    read_only=True
                ),
                Mount(
                    target='/freqtrade/custom_logs',
                    source=logs_dir,
                    type='bind'
                ),
                Mount(
                    target='/freqtrade/custom_database',
                    source=db_dir,
                    type='bind'
                )
            ]

            resources = Resources(
                cpu_limit=1000000000,
                mem_limit=2048 * 1024 * 1024,
                cpu_reservation=500000000,
                mem_reservation=256 * 1024 * 1024
            )

            restart_policy = RestartPolicy(
                condition='on-failure',
                delay=5000000000,
                max_attempts=3
            )

            # 配置端口发布
            api_port = self.config_manager.get_user_api_port(user_id)

            from docker.types import EndpointSpec
            endpoint_spec = EndpointSpec(ports={api_port: 8080})

            # 环境变量
            env_vars = [
                f'API_KEY={api_key}',
                f'API_SECRET={secret}',
                'CONFIG_TEMPLATE=/freqtrade/custom_config/config.json',
                'CONFIG_RUNTIME=/freqtrade/runtime_config.json'
            ]

            # jq 注入脚本（保持原有逻辑）
            entrypoint_script = f'''#!/bin/bash
set -e

echo "======================================"
echo "🔐 Freqtrade Secure Startup"
echo "======================================"

API_KEY="${{API_KEY}}"
API_SECRET="${{API_SECRET}}"
CONFIG_TEMPLATE="${{CONFIG_TEMPLATE:-/freqtrade/custom_config/config.json}}"
CONFIG_RUNTIME="${{CONFIG_RUNTIME:-/freqtrade/runtime_config.json}}"


if [ -z "$API_KEY" ] || [ -z "$API_SECRET" ]; then
    echo "❌ ERROR: API_KEY or API_SECRET not set"
    exit 1
fi

echo "✅ API credentials provided"
echo "   API Key: ${{API_KEY:0:8}}...${{API_KEY: -4}}"

if [ ! -f "$CONFIG_TEMPLATE" ]; then
    echo "❌ ERROR: Configuration template not found: $CONFIG_TEMPLATE"
    exit 1
fi

echo "✅ Configuration template found: $CONFIG_TEMPLATE"
echo "🔧 Injecting API credentials into configuration..."

jq --arg apikey "$API_KEY" --arg secret "$API_SECRET" '
   if .exchange then 
     .exchange.key = $apikey | 
     .exchange.secret = $secret 
   else . end |
   if .exchange.ccxt_config then 
     .exchange.ccxt_config.apiKey = $apikey | 
     .exchange.ccxt_config.secret = $secret 
   else . end |
   if .exchange.ccxt_async_config then 
     .exchange.ccxt_async_config.apiKey = $apikey | 
     .exchange.ccxt_async_config.secret = $secret 
   else . end
   ' \
   "$CONFIG_TEMPLATE" > "$CONFIG_RUNTIME"

if [ $? -ne 0 ]; then
    echo "❌ ERROR: Failed to create runtime configuration"
    exit 1
fi

echo "✅ Runtime configuration created: $CONFIG_RUNTIME"

echo "🔍 Verifying configuration..."
KEY_IN_CONFIG=$(jq -r '.exchange.key' "$CONFIG_RUNTIME")
SECRET_IN_CONFIG=$(jq -r '.exchange.secret' "$CONFIG_RUNTIME")

if [ "$KEY_IN_CONFIG" = "$API_KEY" ] && [ "$SECRET_IN_CONFIG" = "$API_SECRET" ]; then
    echo "✅ Configuration verified successfully"
    echo "   Injected API Key: ${{KEY_IN_CONFIG:0:8}}...${{KEY_IN_CONFIG: -4}}"
else
    echo "❌ ERROR: Configuration verification failed"
    echo "   Expected API Key: ${{API_KEY:0:8}}..."
    echo "   Got API Key: ${{KEY_IN_CONFIG:0:8}}..."
    exit 1
fi

echo "======================================"
echo "🚀 Starting Freqtrade..."
echo "======================================"

exec freqtrade trade \
    -c "$CONFIG_RUNTIME" \
    --logfile /freqtrade/custom_logs/freqtrade.log \
    --db-url sqlite:////freqtrade/custom_database/tradesv3.sqlite \
    --strategy MyStrategy
'''

            # ⭐⭐⭐ 关键：添加节点放置约束
            from docker.types import Placement

            # 指定节点 + 软约束后备
            placement = Placement(
                constraints=[f'node.id=={best_node["id"]}'],  # 指定节点
                preferences=[
                    {'Spread': {'SpreadDescriptor': 'node.role'}}  # 后备：优先Worker
                ]
            )

            # 创建服务
            service = self.client.services.create(
                image='freqtrade:latest',
                name=service_name,
                command=['/bin/bash', '-c', entrypoint_script],
                env=env_vars,
                mounts=mounts,
                resources=resources,
                restart_policy=restart_policy,
                endpoint_spec=endpoint_spec,
                labels={
                    'app': 'freqtrade',
                    'user_id': str(user_id),
                    'managed_by': 'telegram_bot',
                    'config_version': 'v6_jq_injection',
                    'api_port': str(api_port),
                    'node': best_node['hostname']  # ⭐ 记录部署节点
                },
                mode={'Replicated': {'Replicas': 1}},
                constraints=[f'node.id=={best_node["id"]}']  # ⭐⭐⭐ 添加约束
            )

            # 更新数据库
            self.db.update_service_info(user_id, service.id, service_name)
            self.db.update_user_status(user_id, "运行中")
            self.db.log_operation(user_id, "start_service",
                                f"服务 {service_name} 创建成功 (jq注入)")

            print(f"[INFO] ✅ 服务创建成功: {service_name}")
            print(f"[INFO] 服务ID: {service.id}")
            print(f"[INFO] 🔒 API密钥通过 jq 动态注入")
            print(f"[INFO] 📍 部署节点: {best_node['hostname']}")

            return True, (
                f"✅ 服务创建成功: {service_name}\n"
                f"策略: MyStrategy\n"
                f"🔒 安全模式: jq 动态注入\n"
                f"📍 部署节点: {best_node['hostname']} ({best_node['role']})\n"
                f"📊 节点负载: {best_node['current'] + 1}/{best_node['max']}\n"
                f"🌐 API地址: http://localhost:{api_port}"
            )

        except docker.errors.APIError as e:
            error_msg = str(e)
            print(f"[ERROR] Docker API错误: {error_msg}")
            return False, f"创建服务失败: {error_msg}"

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[ERROR] 创建服务详细错误:\n{error_detail}")
            return False, f"创建服务失败: {str(e)}"

    # ========== 保留原有的其他方法不变 ==========

    def stop_service(self, user_id: int) -> Tuple[bool, str]:
        """停止并删除Freqtrade服务"""
        if not self.client:
            return False, "Docker未连接"

        service_name = self._get_service_name(user_id)

        try:
            service = self.client.services.get(service_name)
            service.remove()

            self.db.clear_service_info(user_id)
            self.db.update_user_status(user_id, "停止")
            self.db.log_operation(user_id, "stop_service", f"服务 {service_name} 已停止")

            print(f"[INFO] 🔒 服务停止，密钥已从内存中清除")

            return True, "服务已停止并删除"

        except docker.errors.NotFound:
            self.db.clear_service_info(user_id)
            self.db.update_user_status(user_id, "停止")
            return False, "服务不存在"

        except Exception as e:
            return False, f"停止服务失败: {str(e)}"

    def restart_service(self, user_id: int) -> Tuple[bool, str]:
        """重启服务"""
        success, msg = self.stop_service(user_id)
        if not success and "不存在" not in msg:
            return False, msg

        time.sleep(1)
        return self.create_service(user_id)

    def get_service_status(self, user_id: int) -> Dict[str, Any]:
        """获取服务状态"""
        if not self.client:
            return {'status': 'error', 'message': 'Docker未连接'}

        service_name = self._get_service_name(user_id)

        try:
            service = self.client.services.get(service_name)
            tasks = service.tasks()

            status_info = {
                'status': 'running',
                'service_name': service_name,
                'service_id': service.id,
                'replicas': len([t for t in tasks if t['Status']['State'] == 'running']),
                'desired_replicas': service.attrs['Spec']['Mode']['Replicated']['Replicas'],
                'created': service.attrs['CreatedAt'],
                'updated': service.attrs['UpdatedAt'],
                'config_version': service.attrs['Spec']['Labels'].get('config_version', 'unknown'),
                'tasks': []
            }

            for task in tasks[:5]:
                status_info['tasks'].append({
                    'id': task['ID'][:12],
                    'state': task['Status']['State'],
                    'desired_state': task['DesiredState'],
                    'timestamp': task['Status']['Timestamp']
                })

            return status_info

        except docker.errors.NotFound:
            return {'status': 'stopped', 'message': '服务未运行'}

        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def get_service_logs(self, user_id: int, lines: int = 50) -> str:
        """获取服务日志"""
        if not self.client:
            return "Docker未连接"

        service_name = self._get_service_name(user_id)

        try:
            service = self.client.services.get(service_name)
            logs = service.logs(tail=lines, timestamps=True)

            if isinstance(logs, bytes):
                return logs.decode('utf-8', errors='ignore')
            else:
                return ''.join([chunk.decode('utf-8', errors='ignore') for chunk in logs])

        except docker.errors.NotFound:
            return "服务不存在"

        except Exception as e:
            return f"获取日志失败: {str(e)}"

    def scale_service(self, user_id: int, replicas: int) -> Tuple[bool, str]:
        """扩展服务副本数"""
        if not self.client:
            return False, "Docker未连接"

        service_name = self._get_service_name(user_id)

        try:
            service = self.client.services.get(service_name)
            service.scale(replicas)
            return True, f"服务已扩展到 {replicas} 个副本"

        except docker.errors.NotFound:
            return False, "服务不存在"

        except Exception as e:
            return False, f"扩展服务失败: {str(e)}"

    def update_service(self, user_id: int, **kwargs) -> Tuple[bool, str]:
        """更新服务配置"""
        if not self.client:
            return False, "Docker未连接"

        service_name = self._get_service_name(user_id)

        try:
            service = self.client.services.get(service_name)
            service.update(**kwargs)
            self.db.log_operation(user_id, "update_service", "服务配置已更新")
            return True, "服务配置已更新"

        except docker.errors.NotFound:
            return False, "服务不存在"

        except Exception as e:
            return False, f"更新服务失败: {str(e)}"

    def list_all_services(self) -> List[Dict]:
        """列出所有Freqtrade服务"""
        if not self.client:
            return []

        try:
            services = self.client.services.list(filters={'label': 'app=freqtrade'})

            service_list = []
            for service in services:
                service_list.append({
                    'name': service.name,
                    'id': service.id[:12],
                    'user_id': service.attrs['Spec']['Labels'].get('user_id', 'unknown'),
                    'replicas': len([t for t in service.tasks() if t['Status']['State'] == 'running']),
                    'created': service.attrs['CreatedAt'],
                    'config_version': service.attrs['Spec']['Labels'].get('config_version', 'v1')
                })

            return service_list

        except Exception as e:
            print(f"[ERROR] 列出服务失败: {e}")
            return []

    def cleanup_stopped_services(self) -> int:
        """清理已停止的服务"""
        if not self.client:
            return 0

        cleaned = 0
        try:
            services = self.client.services.list(filters={'label': 'app=freqtrade'})

            for service in services:
                tasks = service.tasks()
                running_tasks = [t for t in tasks if t['Status']['State'] == 'running']

                if not running_tasks:
                    service.remove()
                    cleaned += 1
                    print(f"[INFO] 清理服务: {service.name}")

            return cleaned

        except Exception as e:
            print(f"[ERROR] 清理服务失败: {e}")
            return cleaned