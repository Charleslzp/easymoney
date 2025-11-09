"""
完整的 SwarmManager 实现
所有方法都已实现，可以直接替换原文件
"""

import docker
import os
import time
import socket
from typing import Optional, Tuple, Dict, List, Any
from database import Database
from config_manager import ConfigManager


def get_local_ip():
    """获取本地IP地址"""
    try:
        # 创建一个UDP socket连接到外部地址（不会真的发送数据）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 连接到Google的DNS服务器（8.8.8.8）
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        print(f"获取本地IP失败: {e}")
        # 返回默认值
        return "127.0.0.1"


class SwarmManager:
    """Docker Swarm 管理类 - 完整实现版"""

    def __init__(self):
        """初始化 Swarm Manager"""
        try:
            self.client = docker.from_env()
            self.db = Database()
            self.config_manager = ConfigManager()

            self._ensure_overlay_network()

            if not self._is_swarm_initialized():
                print("[WARN] Docker Swarm 未初始化，尝试初始化...")
                self._init_swarm()

            print("[INFO] Docker Swarm 客户端连接成功")

        except Exception as e:
            print(f"[ERROR] 无法连接到 Docker: {e}")
            self.client = None

    # ========================================
    # Swarm 初始化与检查
    # ========================================

    def _ensure_overlay_network(self):
        """确保 overlay 网络存在且健康"""
        import subprocess

        network_name = 'freqtrade_network'

        try:
            networks = self.client.networks.list(names=[network_name])
            if not networks:
                print(f"[INFO] 创建 overlay 网络 '{network_name}'...")
                self.client.networks.create(
                    name=network_name,
                    driver='overlay',
                    attachable=True,
                    check_duplicate=True
                )
                print(f"[INFO] ✅ Overlay 网络 '{network_name}' 创建成功")
            else:
                print(f"[INFO] Overlay 网络 '{network_name}' 已存在")

            # 🧠 增加底层健康检测
            result = subprocess.run("ip addr | grep vxlan", shell=True, capture_output=True, text=True)
            if not result.stdout.strip():
                print("[⚠️ WARNING] 本节点未检测到 vxlan 接口，overlay 网络可能异常")
                print("请检查 UDP 4789 / TCP+UDP 7946 端口是否在所有节点间放通")

            return True

        except docker.errors.APIError as e:
            if 'already exists' in str(e):
                print(f"[INFO] Overlay 网络 '{network_name}' 已存在")
                return True
            print(f"[ERROR] 创建 overlay 网络失败: {e}")
            return False

    def _is_swarm_initialized(self) -> bool:
        """检查 Swarm 是否已初始化"""
        try:
            info = self.client.info()
            return info.get('Swarm', {}).get('LocalNodeState') == 'active'
        except:
            return False

    def _init_swarm(self) -> bool:
        """初始化 Docker Swarm"""
        try:
            self.client.swarm.init()
            print("[INFO] Docker Swarm 初始化成功")
            return True
        except docker.errors.APIError as e:
            if 'already part of a swarm' in str(e):
                print("[INFO] Swarm 已经初始化")
                return True
            print(f"[ERROR] Swarm 初始化失败: {e}")
            return False

    # ========================================
    # 服务命名与目录管理
    # ========================================

    def _get_service_name(self, user_id: int) -> str:
        """生成服务名称"""
        return f"freqtrade_{user_id}"

    def _ensure_user_directories(self, user_dir: str) -> bool:
        """确保用户目录结构存在"""
        try:
            config_dir = f"{user_dir}/config"
            logs_dir = f"{user_dir}/logs"
            db_dir = f"{user_dir}/database"

            os.makedirs(config_dir, exist_ok=True)
            os.makedirs(logs_dir, exist_ok=True)
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

    # ========================================
    # 智能节点选择 - 完整实现
    # ========================================

    def _get_node_container_count(self, node_id: str) -> int:
        """获取指定节点上运行的 freqtrade 容器数量"""
        try:
            services = self.client.services.list(filters={'label': 'app=freqtrade'})

            container_count = 0
            for service in services:
                tasks = service.tasks(filters={
                    'node': node_id,
                    'desired-state': 'running'
                })

                running_tasks = [
                    t for t in tasks
                    if t.get('Status', {}).get('State') == 'running'
                ]
                container_count += len(running_tasks)

            return container_count

        except Exception as e:
            print(f"[ERROR] 获取节点容器数量失败: {e}")
            return 999  # 返回大数，避免选择该节点

    def _get_node_max_containers(self, node: Any) -> int:
        """获取节点的最大容器限制"""
        try:
            labels = node.attrs.get('Spec', {}).get('Labels', {})
            if 'max_containers' in labels:
                return int(labels['max_containers'])

            # 默认值（已增加）
            role = node.attrs.get('Spec', {}).get('Role', 'worker')
            return 30 if role == 'manager' else 50

        except Exception as e:
            print(f"[ERROR] 获取节点最大容器限制失败: {e}")
            return 50

    def _get_node_ip(self, node_id: str) -> Optional[str]:
        """获取节点的 IP 地址"""
        try:
            node = self.client.nodes.get(node_id)

            # 方式 1: ManagerStatus.Addr
            manager_status = node.attrs.get('ManagerStatus', {})
            if manager_status and 'Addr' in manager_status:
                addr = manager_status['Addr']
                return addr.split(':')[0]

            # 方式 2: Status.Addr
            status = node.attrs.get('Status', {})
            if 'Addr' in status:
                return status['Addr']

            # 方式 3: 从 hostname 解析
            description = node.attrs.get('Description', {})
            hostname = description.get('Hostname', '')

            try:
                socket.inet_aton(hostname)
                return hostname
            except socket.error:
                try:
                    return socket.gethostbyname(hostname)
                except:
                    pass

            print(f"[WARN] 无法获取节点 {node_id} 的 IP 地址")
            return None

        except Exception as e:
            print(f"[ERROR] 获取节点 IP 失败: {e}")
            return None

    def _find_best_node(self) -> Optional[Dict[str, Any]]:
        """查找最佳节点部署服务 - 完整实现"""
        try:
            # 1. 优先获取 Worker 节点
            nodes = self.client.nodes.list(filters={'role': 'worker'})

            # 2. 如果没有 Worker 节点，获取所有节点
            if not nodes:
                print("[WARN] 没有 Worker 节点，将考虑所有节点")
                nodes = self.client.nodes.list()

            # 3. 如果仍然没有节点
            if not nodes:
                print("[ERROR] 集群中没有任何节点")
                return None

            available_nodes = []

            for node in nodes:
                # 只考虑 Ready 状态的节点
                state = node.attrs['Status']['State']
                if state != 'ready':
                    print(f"[SKIP] 节点 {node.attrs['Description']['Hostname']} 状态: {state}")
                    continue

                # 只考虑可用的节点
                availability = node.attrs['Spec'].get('Availability', 'active')
                if availability != 'active':
                    print(f"[SKIP] 节点 {node.attrs['Description']['Hostname']} 可用性: {availability}")
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
                else:
                    print(f"[SKIP] 节点 {hostname} 已达到容器上限")

            if not available_nodes:
                print("[ERROR] 没有可用节点（所有节点都已达到容器上限）")
                return None

            # 排序：优先级 -> 负载最低
            available_nodes.sort(key=lambda x: (x['priority'], x['current']))

            best_node = available_nodes[0]
            print(f"[INFO] ✅ 选择最佳节点: {best_node['hostname']} "
                  f"({best_node['current']}/{best_node['max']} 容器)")

            return best_node

        except Exception as e:
            print(f"[ERROR] 查找最佳节点失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ========================================
    # 核心服务管理
    # ========================================

    def create_service(self, user_id: int) -> Tuple[bool, str]:
        """创建 Freqtrade 服务 - 完整实现"""
        if not self.client:
            return False, "Docker 未连接"

        service_name = self._get_service_name(user_id)
        nfs_base = "/mnt/freqtrade-data"
        user_dir = os.path.join(nfs_base, "user_data_manager", str(user_id))



        if not self._ensure_user_directories(user_dir):
            return False, "创建用户目录失败或配置文件不存在"



        try:
            # 1. 查找最佳节点
            best_node = self._find_best_node()
            if not best_node:
                return False, (
                    "❌ 无可用节点\n\n"
                    "所有节点都已达到容器上限或不满足条件。\n"
                    "请联系管理员扩容或等待其他容器停止。"
                )

            # 2. 获取节点 IP
            node_ip = self._get_node_ip(best_node['id'])
            if not node_ip:
                print(f"[WARN] 无法获取节点 IP，使用 hostname: {best_node['hostname']}")
                node_ip = best_node['hostname']

            # 3. 清理已存在的服务
            try:
                existing_service = self.client.services.get(service_name)
                print(f"[INFO] 发现已存在的服务，正在清理...")
                existing_service.remove()
                time.sleep(2)
            except docker.errors.NotFound:
                pass

            # 4. 获取用户 API 密钥
            user = self.db.get_user_by_telegram_id(user_id)
            if not user:
                return False, "用户不存在"

            api_key = user.get('api_key')
            secret = user.get('security')

            if not api_key or not secret:
                return False, "API 密钥未配置，请先使用 /bind 命令绑定"

            print(f"[INFO] 从数据库获取 API 密钥")
            print(f"[INFO] API Key: {api_key[:8]}...{api_key[-4:]}")
            print(f"[INFO] 🔒 使用 jq 启动脚本注入")
            print(f"[INFO] 📍 目标节点: {best_node['hostname']} ({best_node['role']})")
            print(f"[INFO] 🌐 节点 IP: {node_ip}")

            # 5. 配置目录挂载
            from docker.types import Mount, Resources, RestartPolicy, EndpointSpec

            config_dir = f"{user_dir}/config"
            logs_dir = f"{user_dir}/logs"
            db_dir = f"{user_dir}/database"

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

            # 6. 资源限制
            resources = Resources(
                cpu_limit=1000000000,           # 1 CPU
                mem_limit=4096 * 1024 * 1024,   # 2GB
                cpu_reservation=500000000,      # 0.5 CPU
                mem_reservation=256 * 1024 * 1024  # 256MB
            )

            # 7. 重启策略
            restart_policy = RestartPolicy(
                condition='on-failure',
                delay=5000000000,
                max_attempts=3
            )

            # 8. 端口映射
            api_port = self.config_manager.get_user_api_port(user_id)
            endpoint_spec = EndpointSpec(
                ports=[
                    {
                        'Protocol': 'tcp',
                        'TargetPort': 8080,  # ⭐ 容器内部：freqtrade 监听 8080
                        'PublishedPort': api_port,  # ⭐ 对外暴露：用户访问 8729
                        'PublishMode': 'ingress'
                    }
                ]
            )
            local_ip = get_local_ip()

            subscription = self.db.get_user_subscription(user_id)
            if subscription:
                max_capital= subscription['max_capital']
                env_vars = [
                    f'API_KEY={api_key}',
                    f'API_SECRET={secret}',
                    f'FT_MAX_CAPITAL={max_capital}',
                    f'REMOTE_IP={local_ip}',

                    'CONFIG_TEMPLATE=/freqtrade/custom_config/config.json',
                    'CONFIG_RUNTIME=/freqtrade/runtime_config.json'
                ]
            else:
                print(f'未订阅 {user_id}')
                env_vars = [
                    f'API_KEY={api_key}',
                    f'API_SECRET={secret}',
                    f'REMOTE_IP={local_ip}',

                    'CONFIG_TEMPLATE=/freqtrade/custom_config/config.json',
                    'CONFIG_RUNTIME=/freqtrade/runtime_config.json'
                ]

            # 9. 环境变量


            # 10. jq 注入启动脚本
            entrypoint_script = '''#!/bin/bash
            set -e

            echo "======================================"
            echo "🔐 Freqtrade Secure Startup"
            echo "======================================"

            API_KEY="${{API_KEY}}"
            API_SECRET="${{API_SECRET}}"
            FT_MAX_CAPITAL="${{FT_MAX_CAPITAL}}"
            REMOTE_IP="${{REMOTE_IP}}"
            CONFIG_TEMPLATE="${{CONFIG_TEMPLATE:-/freqtrade/custom_config/config.json}}"
            CONFIG_RUNTIME="${{CONFIG_RUNTIME:-/freqtrade/runtime_config.json}}"

            echo "🔧 修复权限..."
            chown -R ftuser:ftuser /freqtrade/user_data_manager/{user_id} 2>/dev/null || true
            chmod -R 755 /freqtrade/user_data_manager/{user_id} 2>/dev/null || true
            find /freqtrade/user_data_manager/{user_id} -type f -exec chmod 644 {{}} \\; 2>/dev/null || true

            echo "✅ 权限修复完成"
            echo "🚀 启动 Freqtrade..."

            if [ -z "$API_KEY" ] || [ -z "$API_SECRET" ]; then
                echo "❌ ERROR: API_KEY or API_SECRET not set"
                exit 1
            fi

            if [ -z "$FT_MAX_CAPITAL" ] ; then
                echo "❌ FT_MAX_CAPITAL not set"
                exit 1
            fi

            if [ -z "$REMOTE_IP" ] ; then
                echo "❌ REMOTE_IP not set"
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
               ' "$CONFIG_TEMPLATE" > "$CONFIG_RUNTIME"

            if [ $? -ne 0 ]; then
                echo "❌ ERROR: Failed to create runtime configuration"
                exit 1
            fi

            echo "✅ Runtime configuration created: $CONFIG_RUNTIME"

            KEY_IN_CONFIG=$(jq -r '.exchange.key' "$CONFIG_RUNTIME")
            SECRET_IN_CONFIG=$(jq -r '.exchange.secret' "$CONFIG_RUNTIME")

            if [ "$KEY_IN_CONFIG" = "$API_KEY" ] && [ "$SECRET_IN_CONFIG" = "$API_SECRET" ]; then
                echo "✅ Configuration verified successfully"
                echo "   Injected API Key: ${{KEY_IN_CONFIG:0:8}}...${{KEY_IN_CONFIG: -4}}"
            else
                echo "❌ ERROR: Configuration verification failed"
                exit 1
            fi

            echo "======================================"
            echo "🚀 Starting Freqtrade..."
            echo "======================================"

            exec freqtrade trade \\
                -c "$CONFIG_RUNTIME" \\
                --logfile /freqtrade/custom_logs/freqtrade.log \\
                --db-url sqlite:////freqtrade/custom_database/tradesv3.sqlite \\
                --strategy MyStrategy 
            '''.format(user_id=user_id)

            # 11. 创建服务
            service = self.client.services.create(
                image='freqtrade:latest',
                name=service_name,
                command=['/bin/bash', '-c', entrypoint_script],
                env=env_vars,
                mounts=mounts,
                #resources=resources,
                restart_policy=restart_policy,
                endpoint_spec=endpoint_spec,
                networks=['freqtrade_network'],
                labels={
                    'app': 'freqtrade',
                    'user_id': str(user_id),
                    'managed_by': 'telegram_bot',
                    'config_version': 'v7_fixed',
                    'api_port': str(api_port),
                    'node': best_node['hostname'],
                    'node_ip': node_ip
                },
                mode={'Replicated': {'Replicas': 1}},
                constraints=[f'node.id=={best_node["id"]}']
            )

            # 12. 更新数据库
            self.db.update_service_info(user_id, service.id, service_name, node_ip=node_ip, api_port=api_port)
            self.db.update_user_status(user_id, "运行中")
            self.db.log_operation(user_id, "start_service",
                                f"服务 {service_name} 创建成功 (节点: {best_node['hostname']})")

            print(f"[INFO] ✅ 服务创建成功: {service_name}")
            print(f"[INFO] 服务 ID: {service.id}")
            print(f"[INFO] 🔒 API 密钥通过 jq 动态注入")
            print(f"[INFO] 📍 部署节点: {best_node['hostname']} ({node_ip})")
            print(f"[INFO] 🌐 API 地址: http://{node_ip}:{api_port}")

            return True, (
                f"✅ 服务创建成功: {service_name}\n"
                f"策略: MyStrategy\n"
                f"🔒 安全模式: jq 动态注入\n"
                f"📍 部署节点: {best_node['hostname']} ({best_node['role']})\n"
                f"🌐 节点 IP: {node_ip}\n"
                f"🔌 API 端口: {api_port}\n"
                f"📊 节点负载: {best_node['current'] + 1}/{best_node['max']}"
            )

        except docker.errors.APIError as e:
            error_msg = str(e)
            print(f"[ERROR] Docker API 错误: {error_msg}")
            return False, f"创建服务失败: {error_msg}"

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[ERROR] 创建服务详细错误:\n{error_detail}")
            return False, f"创建服务失败: {str(e)}"

    def stop_service(self, user_id: int) -> Tuple[bool, str]:
        """停止并删除 Freqtrade 服务"""
        if not self.client:
            return False, "Docker 未连接"

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

    # ========================================
    # 服务监控与管理
    # ========================================

    def get_service_status(self, user_id: int) -> Dict[str, Any]:
        """获取服务详细状态"""
        if not self.client:
            return {'status': 'error', 'message': 'Docker 未连接'}

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
                'node_ip': service.attrs['Spec']['Labels'].get('node_ip', 'unknown'),
                'api_port': service.attrs['Spec']['Labels'].get('api_port', 'unknown'),
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
            return "Docker 未连接"

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


# 测试函数
def test_swarm_manager():
    """测试 SwarmManager 功能"""
    print("=" * 60)
    print("测试 SwarmManager")
    print("=" * 60)

    manager = SwarmManager()

    if not manager.client:
        print("❌ Docker 客户端连接失败")
        return

    # 测试查找最佳节点
    print("\n测试查找最佳节点:")
    best_node = manager._find_best_node()

    if best_node:
        print(f"✅ 找到最佳节点: {best_node['hostname']}")
        print(f"   容器数: {best_node['current']}/{best_node['max']}")
        print(f"   角色: {best_node['role']}")
    else:
        print("❌ 未找到可用节点")


if __name__ == "__main__":
    test_swarm_manager()