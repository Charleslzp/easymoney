"""
utils.py - 工具函数模块
提供API验证、日志格式化等通用功能
"""

import ccxt
import logging
from datetime import datetime
from typing import Tuple, Optional, Any

# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def validate_binance_api(api_key: str, secret: str) -> Tuple[bool, str]:
    """
    验证币安API密钥
    
    Args:
        api_key: API密钥
        secret: 密钥Secret
    
    Returns:
        (是否有效, 错误信息)
    """
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret,
            'enableRateLimit': True
        })
        
        # 加载市场
        exchange.load_markets()
        
        # 尝试获取余额
        balance = exchange.fetch_balance()
        
        logger.info("API验证成功")
        return True, "验证成功"
    
    except ccxt.AuthenticationError as e:
        logger.error(f"API认证失败: {e}")
        return False, "API密钥或Secret错误"
    
    except ccxt.NetworkError as e:
        logger.error(f"网络错误: {e}")
        return False, "网络连接失败，请稍后重试"
    
    except ccxt.ExchangeError as e:
        logger.error(f"交易所错误: {e}")
        return False, f"交易所错误: {str(e)}"
    
    except Exception as e:
        logger.error(f"未知错误: {e}")
        return False, f"验证失败: {str(e)}"


def format_timestamp(timestamp: str) -> str:
    """格式化时间戳"""
    try:
        dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return timestamp


def format_bytes(bytes_size: int) -> str:
    """格式化字节大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def format_service_status(status_info: dict) -> str:
    """格式化服务状态信息为可读文本"""
    if status_info.get('status') == 'error':
        return f"❌ 错误: {status_info.get('message', '未知错误')}"
    
    if status_info.get('status') == 'stopped':
        return "⏸ 服务未运行"
    
    if status_info.get('status') == 'running':
        text = f"✅ 服务运行中\n\n"
        text += f"📦 服务名: {status_info.get('service_name', 'N/A')}\n"
        text += f"🆔 服务ID: {status_info.get('service_id', 'N/A')[:12]}\n"
        text += f"📊 副本数: {status_info.get('replicas', 0)}/{status_info.get('desired_replicas', 0)}\n"
        
        if 'created' in status_info:
            text += f"🕐 创建时间: {format_timestamp(status_info['created'])}\n"
        
        if 'tasks' in status_info and status_info['tasks']:
            text += f"\n📋 最近任务:\n"
            for task in status_info['tasks'][:3]:
                state = task.get('state', 'unknown')
                emoji = '🟢' if state == 'running' else '🔴'
                text += f"{emoji} {task.get('id', 'N/A')} - {state}\n"
        
        return text
    
    return "❓ 未知状态"


def format_log_output(logs: str, max_lines: int = 50) -> str:
    """格式化日志输出"""
    if not logs or logs == "暂无日志":
        return "📋 暂无日志"
    
    lines = logs.split('\n')
    
    # 限制行数
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        prefix = f"...(仅显示最后{max_lines}行)\n\n"
    else:
        prefix = ""
    
    # 限制总长度
    output = '\n'.join(lines)
    if len(output) > 4000:
        output = output[-4000:]
        prefix = "...(日志过长，仅显示最后4000字符)\n\n" + prefix
    
    return f"📋 日志输出:\n\n\n{prefix}{output}\n"


def sanitize_api_key_display(api_key: str) -> str:
    """安全显示API密钥（隐藏中间部分）"""
    if not api_key:
        return "未设置"
    
    if len(api_key) <= 12:
        return "*"
    
    return f"{api_key[:6]}...{api_key[-4:]}"


def validate_user_input(text: str, max_length: int = 1000) -> Tuple[bool, str]:
    """验证用户输入"""
    if not text or not text.strip():
        return False, "输入不能为空"
    
    if len(text) > max_length:
        return False, f"输入过长，最多{max_length}个字符"
    
    return True, ""


def parse_config_key_value(text: str) -> Optional[Tuple[str, str]]:
    """
    解析配置键值对
    格式: key=value 或 key:value
    """
    for separator in ['=', ':']:
        if separator in text:
            parts = text.split(separator, 1)
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                if key and value:
                    return (key, value)
    return None


class RateLimiter:
    """简单的速率限制器"""
    
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}
    
    def is_allowed(self, user_id: int) -> bool:
        """检查用户是否允许请求"""
        now = datetime.now().timestamp()
        
        if user_id not in self.requests:
            self.requests[user_id] = []
        
        # 清理过期的请求记录
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < self.time_window
        ]
        
        # 检查是否超过限制
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        
        # 记录本次请求
        self.requests[user_id].append(now)
        return True
    
    def get_remaining_requests(self, user_id: int) -> int:
        """获取剩余请求数"""
        now = datetime.now().timestamp()
        
        if user_id not in self.requests:
            return self.max_requests
        
        # 清理过期的请求
        self.requests[user_id] = [
            req_time for req_time in self.requests[user_id]
            if now - req_time < self.time_window
        ]
        
        return max(0, self.max_requests - len(self.requests[user_id]))


def create_service_menu_text() -> str:
    """创建服务菜单文本"""
    return """
🤖 Freqtrade 交易机器人管理系统

请选择操作：

基础操作：
• 📝 注册 - 注册新账户
• 🔗 绑定API - 绑定币安API密钥
• ▶️ 启动交易 - 启动交易机器人
• ⏸️ 停止交易 - 停止交易机器人

监控管理：
• 📊 查看状态 - 查看服务运行状态
• 📋 查看日志 - 查看交易日志
• ⚙️ 配置管理 - 管理配置文件

帮助：
• ❓ 帮助 - 查看使用说明
"""


def create_help_text() -> str:
    """创建帮助文本"""
    return """
📚 使用指南

命令列表：
• /start - 开始使用
• /register - 注册账户
• /bind <key> <secret> - 绑定API
• /startbot - 启动交易
• /stopbot - 停止交易
• /status - 查看状态
• /logs [行数] - 查看日志
• /config - 配置管理
• /help - 帮助信息

使用流程：
1️⃣ 注册账户
2️⃣ 绑定币安API密钥
3️⃣ 启动交易机器人
4️⃣ 监控运行状态

注意事项：
⚠️ API只需开启交易权限
⚠️ 不要开启提现权限
⚠️ 建议设置IP白名单
⚠️ 定期查看交易日志

如有问题，请联系管理员。
"""
