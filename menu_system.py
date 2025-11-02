# ========== 1. 修改 menu_system.py ==========

"""
menu_system.py - 多语言菜单系统 (包含邀请码子菜单)
"""

import json
import logging
from enum import Enum
from typing import Dict, List, Optional
from telegram import KeyboardButton, ReplyKeyboardMarkup

logger = logging.getLogger(__name__)


class Language(Enum):
    """语言枚举"""
    ZH = "zh"
    EN = "en"


class UserStatus(Enum):
    """用户状态"""
    NOT_REGISTERED = "not_registered"
    REGISTERED = "registered"
    API_BOUND = "api_bound"
    TRADING = "trading"
    STOPPED = "stopped"


class MenuSystem:
    """菜单系统管理类"""

    def __init__(self, config_file: str = "menu_config.json"):
        self.config_file = config_file
        self.menu_config = self._load_config()
        self.user_languages: Dict[int, Language] = {}

    def _load_config(self) -> Dict:
        """加载菜单配置"""
        default_config = {
            "zh": {
                "main_menu": {
                    "register": "📝 注册",
                    "bind_api": "🔗 绑定API",
                    "my_payment": "💰 我的充值",
                    "my_subscription": "📋 我的订阅",
                    "use_invite": "🎁 使用邀请码",  # 未使用时显示
                    "my_invite": "🎁 我的邀请码",   # ⭐ 已使用时显示
                    "start_trading": "▶️ 启动交易",
                    "stop_trading": "⏸️ 停止交易",
                    "view_status": "📊 查看状态",
                    "profit": "💰 利润统计",
                    "performance": "📈 币种性能",
                    "positions": "📍 持仓查询",
                    "balance": "💵 余额查询",
                    "config_manage": "⚙️ 配置管理",
                    "help": "❓ 帮助",
                    "switch_lang": "🌐 Switch to English"
                },
                "invite_submenu": {  # ⭐ 新增邀请码子菜单
                    "title": "🎁 邀请码系统",
                    "my_stats": "📊 我的邀请统计",
                    "my_invitees": "👥 我的邀请列表",
                    "share_code": "💬 分享邀请码",
                    "back": "🔙 返回主菜单"
                },
                "status_submenu": {
                    "title": "📊 状态查看",
                    "profit": "💰 查看收益",
                    "positions": "📍 查看持仓",
                    "performance": "📈 查看绩效",
                    "back": "🔙 返回主菜单"
                },
                "config_submenu": {
                    "title": "⚙️ 配置管理",
                    "modify_leverage": "📊 修改杠杆率",
                    "view_pairs": "💱 查看交易对",
                    "back": "🔙 返回主菜单"
                },
                "prompts": {
                    "select_option": "请选择操作:",
                    "invalid_option": "无效选项,请重新选择",
                    "register_success": "注册成功!",
                    "api_bound_success": "API绑定成功!",
                    "trading_started": "交易已启动",
                    "trading_stopped": "交易已停止",
                    "language_switched": "语言已切换为中文",
                    "invite_code_applied": "邀请码应用成功!",
                    "invite_code_invalid": "邀请码无效"
                }
            },
            "en": {
                "main_menu": {
                    "register": "📝 Register",
                    "bind_api": "🔗 Bind API",
                    "my_payment": "💰 My Recharge",
                    "my_subscription": "📋 My Subscription",
                    "use_invite": "🎁 Use Invite Code",
                    "my_invite": "🎁 My Invite Code",  # ⭐ 已使用时显示
                    "start_trading": "▶️ Start Trading",
                    "stop_trading": "⏸️ Stop Trading",
                    "view_status": "📊 View Status",
                    "profit": "💰 Profit",
                    "performance": "📈 Performance",
                    "positions": "📍 Positions",
                    "balance": "💵 Balance",
                    "config_manage": "⚙️ Configuration",
                    "help": "❓ Help",
                    "switch_lang": "🌐 切换到中文"
                },
                "invite_submenu": {  # ⭐ 新增邀请码子菜单
                    "title": "🎁 Invite System",
                    "my_stats": "📊 My Statistics",
                    "my_invitees": "👥 My Invitees",
                    "share_code": "💬 Share Code",
                    "back": "🔙 Back to Main"
                },
                "status_submenu": {
                    "title": "📊 Status View",
                    "profit": "💰 View Profit",
                    "positions": "📍 View Positions",
                    "performance": "📈 View Performance",
                    "back": "🔙 Back to Main"
                },
                "config_submenu": {
                    "title": "⚙️ Configuration",
                    "modify_leverage": "📊 Modify Leverage",
                    "view_pairs": "💱 View Pairs",
                    "back": "🔙 Back to Main"
                },
                "prompts": {
                    "select_option": "Please select an option:",
                    "invalid_option": "Invalid option, please try again",
                    "register_success": "Registration successful!",
                    "api_bound_success": "API bound successfully!",
                    "trading_started": "Trading started",
                    "trading_stopped": "Trading stopped",
                    "language_switched": "Language switched to English",
                    "invite_code_applied": "Invite code applied!",
                    "invite_code_invalid": "Invalid invite code"
                }
            }
        }

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            return default_config

    def get_user_language(self, user_id: int) -> Language:
        """获取用户语言设置"""
        return self.user_languages.get(user_id, Language.ZH)

    def switch_language(self, user_id: int) -> str:
        """切换用户语言"""
        current = self.get_user_language(user_id)
        new_lang = Language.EN if current == Language.ZH else Language.ZH
        self.user_languages[user_id] = new_lang
        lang_code = new_lang.value
        return self.menu_config[lang_code]["prompts"]["language_switched"]

    def get_main_keyboard(self, user_id: int, user_status: UserStatus,
                         has_invite_code: bool = False) -> ReplyKeyboardMarkup:
        """
        获取主菜单键盘(根据用户状态动态生成)

        Args:
            user_id: 用户ID
            user_status: 用户状态
            has_invite_code: 是否已使用邀请码 ⭐ 新增参数
        """
        lang = self.get_user_language(user_id).value
        menu = self.menu_config[lang]["main_menu"]

        keyboard = []

        # 第一行: 注册和绑定API
        row1 = []
        if user_status == UserStatus.NOT_REGISTERED:
            row1.append(KeyboardButton(menu["register"]))

        if user_status == UserStatus.REGISTERED:
            row1.append(KeyboardButton(menu["bind_api"]))

        if row1:
            keyboard.append(row1)

        # API绑定后显示充值和订阅
        if user_status.value in ["api_bound", "trading", "stopped"]:
            keyboard.append([
                KeyboardButton(menu["my_payment"]),
                KeyboardButton(menu["my_subscription"])
            ])

            # ⭐ 邀请码按钮 - 根据是否已使用显示不同文本
            if has_invite_code:
                # 已使用邀请码 - 显示"我的邀请码"
                keyboard.append([KeyboardButton(menu["my_invite"])])
            else:
                # 未使用邀请码 - 显示"使用邀请码"
                keyboard.append([KeyboardButton(menu["use_invite"])])

            # 启动/停止交易按钮
            if user_status != UserStatus.TRADING:
                keyboard.append([KeyboardButton(menu["start_trading"])])
            else:
                keyboard.append([KeyboardButton(menu["stop_trading"])])

            # 状态查看和交易信息
            keyboard.append([
                KeyboardButton(menu["view_status"]),
                KeyboardButton(menu["profit"])
            ])

            keyboard.append([
                KeyboardButton(menu["performance"]),
                KeyboardButton(menu["positions"])
            ])

            keyboard.append([
                KeyboardButton(menu["balance"]),
                KeyboardButton(menu["config_manage"])
            ])

        # 最后一行: 帮助和语言切换
        keyboard.append([
            KeyboardButton(menu["help"]),
            KeyboardButton(menu["switch_lang"])
        ])

        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_invite_keyboard(self, user_id: int) -> ReplyKeyboardMarkup:
        """⭐ 获取邀请码子菜单键盘"""
        lang = self.get_user_language(user_id).value
        submenu = self.menu_config[lang]["invite_submenu"]

        keyboard = [
            [KeyboardButton(submenu["my_stats"])],
            [KeyboardButton(submenu["my_invitees"])],
            [KeyboardButton(submenu["share_code"])],
            [KeyboardButton(submenu["back"])]
        ]

        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_status_keyboard(self, user_id: int) -> ReplyKeyboardMarkup:
        """获取状态子菜单键盘"""
        lang = self.get_user_language(user_id).value
        submenu = self.menu_config[lang]["status_submenu"]

        keyboard = [
            [KeyboardButton(submenu["profit"])],
            [KeyboardButton(submenu["positions"])],
            [KeyboardButton(submenu["performance"])],
            [KeyboardButton(submenu["back"])]
        ]

        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_config_keyboard(self, user_id: int) -> ReplyKeyboardMarkup:
        """获取配置子菜单键盘"""
        lang = self.get_user_language(user_id).value
        submenu = self.menu_config[lang]["config_submenu"]

        keyboard = [
            [KeyboardButton(submenu["modify_leverage"])],
            [KeyboardButton(submenu["view_pairs"])],
            [KeyboardButton(submenu["back"])]
        ]

        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_text(self, user_id: int, key: str, category: str = "prompts") -> str:
        """获取本地化文本"""
        lang = self.get_user_language(user_id).value
        return self.menu_config[lang][category].get(key, "")

    def get_help_text(self, user_id: int) -> str:
        """获取帮助文本"""
        lang = self.get_user_language(user_id).value

        if lang == "zh":
            return """
    📚 <b>命令帮助</b>

    <b>主菜单命令:</b>
    /start - 显示主菜单
    /register - 注册新用户
    /bind - 绑定交易所API
    /help - 显示帮助信息

    <b>💎 邀请系统:</b>
    /invite &lt;邀请码&gt; - 使用邀请码
    /my_invite - 查看邀请统计
    /my_invitees - 查看邀请列表

    <b>邀请奖励说明:</b>
    - 使用邀请码后,充值额外赠送 <b>10%</b>
    - 自动获得您的专属邀请码
    - 好友使用您的码,TA充值您获得 <b>10%</b> 奖励
    - 双向收益,永久有效!

    <b>示例:</b>
    1️⃣ 使用邀请码: <code>/invite WELCOME10</code>
    2️⃣ 充值 1000 USDT → 到账 <b>1100 USDT</b>
    3️⃣ 获得您的邀请码: USER12345ABCD
    4️⃣ 好友用您的码充值 1000 → 您获得 <b>100 USDT</b>

    <b>充值相关:</b>
    /my_address - 查看充值地址
    /my_subscription - 查看订阅状态
    /plans - 查看套餐列表
    /recharge_history - 充值记录

    <b>交易控制:</b>
    /startbot - 启动自动交易
    /stopbot - 停止自动交易
    /status - 查看服务状态

    <b>交易信息:</b>
    /profit - 查看收益统计
    /performance - 查看币种性能
    /positions - 查看当前持仓
    /balance - 查看账户余额
    /pairs - 查看交易对列表

    <b>配置管理:</b>
    /config - 配置管理菜单

    <b>语言切换:</b>
    点击 "🌐 Switch to English" 切换到英文

    <b>💡 提示:</b>
    - 完成注册后,"注册"按钮会自动消失
    - 完成API绑定后,"绑定API"按钮会自动消失
    - 使用邀请码后,按钮变为"我的邀请码"
    - 启动交易前需要先充值并订阅套餐
            """
        else:
            return """
    📚 <b>Command Help</b>

    <b>Main Menu:</b>
    /start - Show main menu
    /register - Register new user
    /bind - Bind exchange API
    /help - Show help

    <b>💎 Invite System:</b>
    /invite &lt;CODE&gt; - Use invite code
    /my_invite - View invite stats
    /my_invitees - View invitee list

    <b>Invite Rewards:</b>
    - Use code: Get <b>10%</b> bonus on recharge
    - Get your own invite code automatically
    - Friends use your code: Earn <b>10%</b> of their recharge
    - Win-win, forever!

    <b>Example:</b>
    1️⃣ Use code: <code>/invite WELCOME10</code>
    2️⃣ Recharge 1000 USDT → Get <b>1100 USDT</b>
    3️⃣ Your code: USER12345ABCD
    4️⃣ Friend recharges 1000 → You earn <b>100 USDT</b>

    <b>Recharge:</b>
    /my_address - View recharge address
    /my_subscription - View subscription
    /plans - View plans
    /recharge_history - Recharge history

    <b>Trading Control:</b>
    /startbot - Start trading
    /stopbot - Stop trading
    /status - View service status

    <b>Trading Info:</b>
    /profit - View profit statistics
    /performance - View coin performance
    /positions - View positions
    /balance - View account balance
    /pairs - View trading pairs

    <b>Configuration:</b>
    /config - Configuration menu

    <b>Language:</b>
    Click "🌐 切换到中文" to switch to Chinese

    <b>💡 Tips:</b>
    - "Register" button disappears after registration
    - "Bind API" button disappears after binding
    - After using invite code, button changes to "My Invite Code"
    - Recharge required before trading
            """

    def match_button_action(self, user_id: int, text: str) -> Optional[str]:
        """匹配按钮文本到动作（支持中英文）"""
        # 获取用户当前语言的菜单配置
        lang = self.get_user_language(user_id).value
        menu = self.menu_config[lang]["main_menu"]
        status_menu = self.menu_config[lang]["status_submenu"]
        config_menu = self.menu_config[lang]["config_submenu"]
        invite_menu = self.menu_config[lang]["invite_submenu"]

        # ⭐ 同时创建两种语言的映射表
        zh_menu = self.menu_config['zh']["main_menu"]
        en_menu = self.menu_config['en']["main_menu"]
        zh_status = self.menu_config['zh']["status_submenu"]
        en_status = self.menu_config['en']["status_submenu"]
        zh_config = self.menu_config['zh']["config_submenu"]
        en_config = self.menu_config['en']["config_submenu"]
        zh_invite = self.menu_config['zh']["invite_submenu"]
        en_invite = self.menu_config['en']["invite_submenu"]

        # ⭐ 创建完整的双语映射表
        action_map = {
            # 主菜单 - 中文
            zh_menu["register"]: "register",
            zh_menu["bind_api"]: "bind_api",
            zh_menu["my_payment"]: "my_payment",
            zh_menu["my_subscription"]: "my_subscription",
            zh_menu["use_invite"]: "use_invite",
            zh_menu["my_invite"]: "my_invite_menu",
            zh_menu["start_trading"]: "start_trading",
            zh_menu["stop_trading"]: "stop_trading",
            zh_menu["view_status"]: "view_status",
            zh_menu["profit"]: "profit",
            zh_menu["performance"]: "performance",
            zh_menu["positions"]: "positions",
            zh_menu["balance"]: "balance",
            zh_menu["config_manage"]: "config_manage",
            zh_menu["help"]: "help",
            zh_menu["switch_lang"]: "switch_lang",

            # 主菜单 - 英文
            en_menu["register"]: "register",
            en_menu["bind_api"]: "bind_api",
            en_menu["my_payment"]: "my_payment",
            en_menu["my_subscription"]: "my_subscription",
            en_menu["use_invite"]: "use_invite",
            en_menu["my_invite"]: "my_invite_menu",
            en_menu["start_trading"]: "start_trading",
            en_menu["stop_trading"]: "stop_trading",
            en_menu["view_status"]: "view_status",
            en_menu["profit"]: "profit",
            en_menu["performance"]: "performance",
            en_menu["positions"]: "positions",
            en_menu["balance"]: "balance",
            en_menu["config_manage"]: "config_manage",
            en_menu["help"]: "help",
            en_menu["switch_lang"]: "switch_lang",

            # 邀请码子菜单 - 中文
            zh_invite["my_stats"]: "my_invite_stats",
            zh_invite["my_invitees"]: "my_invitees",
            zh_invite["share_code"]: "share_invite_code",
            zh_invite["back"]: "back_to_main",

            # 邀请码子菜单 - 英文
            en_invite["my_stats"]: "my_invite_stats",
            en_invite["my_invitees"]: "my_invitees",
            en_invite["share_code"]: "share_invite_code",
            en_invite["back"]: "back_to_main",

            # 状态子菜单 - 中文
            zh_status["profit"]: "profit",
            zh_status["positions"]: "positions",
            zh_status["performance"]: "performance",
            zh_status["back"]: "back_to_main",

            # 状态子菜单 - 英文
            en_status["profit"]: "profit",
            en_status["positions"]: "positions",
            en_status["performance"]: "performance",
            en_status["back"]: "back_to_main",

            # 配置子菜单 - 中文
            zh_config["modify_leverage"]: "modify_leverage",
            zh_config["view_pairs"]: "view_pairs",
            zh_config["back"]: "back_to_main",

            # 配置子菜单 - 英文
            en_config["modify_leverage"]: "modify_leverage",
            en_config["view_pairs"]: "view_pairs",
            en_config["back"]: "back_to_main"
        }

        return action_map.get(text)
