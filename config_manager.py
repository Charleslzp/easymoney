"""
config_manager.py - 配置文件管理模块（安全版本）
配置模板不包含敏感信息，运行时动态注入
"""

import json
import os
import shutil
import tempfile
from typing import Optional, Dict, Any

class ConfigManager:
    """配置文件管理类 - 安全版本"""

    def __init__(self, template_dir: str = "work_dir"):
        self.base_dir = "/mnt/freqtrade-data/user_data"
        self.template_file = "work_dir/config.json"
        self.template_dir = template_dir
        self.template_config_path = os.path.join(template_dir, "config.json")
        self.strategy_path = os.path.join(template_dir, "MyStrategy.py")
        self.user_data_base = "user_data"

    def _get_user_dir(self, user_id: int) -> str:
        """获取用户目录路径"""
        return os.path.join(self.user_data_base, str(user_id))

    def _get_user_config_path(self, user_id: int) -> str:
        """获取用户配置文件路径"""
        return os.path.join(self._get_user_dir(user_id), "config", "config.json")

    def _get_user_config_dir(self, user_id: int) -> str:
        """获取用户配置目录路径"""
        return os.path.join(self._get_user_dir(user_id), "config")

    def _get_user_logs_dir(self, user_id: int) -> str:
        """获取用户日志目录路径"""
        return os.path.join(self._get_user_dir(user_id), "logs")

    def _get_user_database_dir(self, user_id: int) -> str:
        """获取用户数据库目录路径"""
        return os.path.join(self._get_user_dir(user_id), "database")

    def get_user_api_port(self, user_id: int) -> int:
        """计算用户的API端口"""
        return 8080 + (user_id % 1000)

    def create_user_directory(self, user_id: int) -> bool:
        """创建用户目录结构"""
        user_dir = self._get_user_dir(user_id)

        try:
            os.makedirs(user_dir, exist_ok=True)

            subdirs = ['config', 'logs', 'database']
            for subdir in subdirs:
                subdir_path = os.path.join(user_dir, subdir)
                os.makedirs(subdir_path, exist_ok=True)

            db_path = os.path.join(self._get_user_database_dir(user_id), "tradesv3.sqlite")
            if not os.path.exists(db_path):
                open(db_path, 'a').close()
                print(f"[INFO] 创建数据库文件: {db_path}")

            print(f"[INFO] 为用户 {user_id} 创建目录结构成功")
            return True

        except Exception as e:
            print(f"[ERROR] 创建用户目录失败: {e}")
            return False

    def create_user_config(self, user_id: int, api_key: str = None, secret: str = None) -> bool:
        """
        为用户创建配置文件（⭐ 安全版本：不保存密钥）
        只保存配置模板，不包含 API 密钥
        """
        config_path = self._get_user_config_path(user_id)

        self.create_user_directory(user_id)

        try:
            if not os.path.exists(self.template_config_path):
                print(f"[ERROR] 配置模板不存在: {self.template_config_path}")
                return False

            with open(self.template_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # ⭐ 关键修改：不保存真实的 API 密钥
            # 使用占位符，运行时动态替换
            if 'exchange' not in config:
                config['exchange'] = {}

            config['exchange']['key'] = "PLACEHOLDER_API_KEY"
            config['exchange']['secret'] = "PLACEHOLDER_SECRET"

            # 数据库路径
            config['db_url'] = "sqlite:////freqtrade/custom_database/tradesv3.sqlite"
            config['user_data_dir'] = '/freqtrade/user_data'
            config['strategy_path'] = '/freqtrade/user_data/strategies'
            config['bot_name'] = f"freqtrade_{user_id}"
            config['logfile'] = '/freqtrade/custom_logs/freqtrade.log'

            # API Server 配置
            api_port = self.get_user_api_port(user_id)
            if 'api_server' not in config:
                config['api_server'] = {}

            config['api_server']['enabled'] = True
            config['api_server']['listen_ip_address'] = '0.0.0.0'
            config['api_server']['listen_port'] = 8080
            config['api_server']['username'] = 'pythonuser'
            config['api_server']['password'] = 'lzplzp123123'

            # 保存配置（不含真实密钥）
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            print(f"[INFO] 为用户 {user_id} 创建配置文件成功（安全模式）")
            print(f"[INFO] API密钥将在运行时动态注入，不保存到配置文件")
            return True

        except Exception as e:
            print(f"[ERROR] 创建配置文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_runtime_config(self, user_id: int, api_key: str, secret: str) -> Optional[str]:
        """
        ⭐ 创建运行时临时配置文件（包含真实密钥）
        返回临时文件路径，用于启动容器

        Args:
            user_id: 用户ID
            api_key: API密钥
            secret: 密钥Secret

        Returns:
            临时配置文件路径，失败返回 None
        """
        config_path = self._get_user_config_path(user_id)

        if not os.path.exists(config_path):
            print(f"[ERROR] 配置文件不存在: {config_path}")
            return None

        try:
            # 读取配置模板
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # ⭐ 注入真实的 API 密钥
            config['exchange']['key'] = api_key
            config['exchange']['secret'] = secret

            # 创建临时文件
            temp_dir = os.path.join(self._get_user_config_dir(user_id))
            temp_file = os.path.join(temp_dir, f'config_runtime_{user_id}.json')

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            print(f"[INFO] 创建运行时配置: {temp_file}")
            return temp_file

        except Exception as e:
            print(f"[ERROR] 创建运行时配置失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def cleanup_runtime_config(self, user_id: int) -> bool:
        """
        ⭐ 清理运行时临时配置文件

        Args:
            user_id: 用户ID

        Returns:
            是否清理成功
        """
        try:
            temp_file = os.path.join(
                self._get_user_config_dir(user_id),
                f'config_runtime_{user_id}.json'
            )

            if os.path.exists(temp_file):
                os.remove(temp_file)
                print(f"[INFO] 清理临时配置文件: {temp_file}")
                return True
            return True

        except Exception as e:
            print(f"[ERROR] 清理临时配置失败: {e}")
            return False

    def get_user_config(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户配置（不含密钥）"""
        config_path = self._get_user_config_path(user_id)

        if not os.path.exists(config_path):
            print(f"[WARN] 配置文件不存在: {config_path}")
            return None

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] 读取配置失败: {e}")
            return None

    def update_user_config(self, user_id: int, updates: Dict[str, Any]) -> bool:
        """更新用户配置（支持嵌套键）"""
        config_path = self._get_user_config_path(user_id)

        if not os.path.exists(config_path):
            print(f"[ERROR] 配置文件不存在: {config_path}")
            return False

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            for key, value in updates.items():
                keys = key.split('.')
                temp = config
                for k in keys[:-1]:
                    if k not in temp:
                        temp[k] = {}
                    temp = temp[k]
                temp[keys[-1]] = value

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            print(f"[INFO] 用户 {user_id} 配置更新成功")
            return True

        except Exception as e:
            print(f"[ERROR] 更新配置失败: {e}")
            return False

    def get_config_display(self, user_id: int) -> str:
        """获取配置的友好显示（隐藏敏感信息）"""
        config = self.get_user_config(user_id)
        if not config:
            return "配置不存在"

        display_config = json.loads(json.dumps(config))

        # 隐藏敏感信息（虽然现在配置里没有真实密钥）
        if 'exchange' in display_config:
            if 'key' in display_config['exchange']:
                display_config['exchange']['key'] = "***运行时注入***"
            if 'secret' in display_config['exchange']:
                display_config['exchange']['secret'] = "***运行时注入***"

        if 'telegram' in display_config:
            if 'token' in display_config['telegram']:
                display_config['telegram']['token'] = "***已设置***"

        return json.dumps(display_config, indent=2, ensure_ascii=False)

    def config_exists(self, user_id: int) -> bool:
        """检查配置文件是否存在"""
        return os.path.exists(self._get_user_config_path(user_id))

    def get_user_config_dir_absolute_path(self, user_id: int) -> str:
        """获取用户配置目录的绝对路径"""
        return os.path.abspath(self._get_user_config_dir(user_id))

    def get_user_logs_dir_absolute_path(self, user_id: int) -> str:
        """获取用户日志目录的绝对路径"""
        return os.path.abspath(self._get_user_logs_dir(user_id))

    def get_user_database_dir_absolute_path(self, user_id: int) -> str:
        """获取用户数据库目录的绝对路径"""
        return os.path.abspath(self._get_user_database_dir(user_id))