"""
bot.py - Telegram机器人主程序 (完整集成多语言菜单系统)
处理所有用户交互和命令
集成 Freqtrade REST API + 多语言动态菜单
"""

import logging
import os
import json
from typing import List, Tuple
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler
)

# 导入自定义模块
from database import Database
from config_manager import ConfigManager
from swarm_manager import SwarmManager
from utils import (
    validate_binance_api,
    format_service_status,
    format_log_output,
    create_service_menu_text,
    create_help_text,
    RateLimiter
)
from freqtrade_api_client import FreqtradeAPIClient
from freqtrade_commander import FreqtradeCommander
from payment_system import PaymentSystem
from menu_system import MenuSystem, UserStatus  # ⭐ 新增菜单系统
from bot_subscription_commands import (
    register_flexible_subscription_commands,
    auto_subscribe_smart
)

# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 初始化管理器
db = Database()
config_manager = ConfigManager()
swarm_manager = SwarmManager()
rate_limiter = RateLimiter(max_requests=20, time_window=60)
MASTER_PRIVATE_KEY = os.getenv("MASTER_PRIVATE_KEY")
TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY")
NETWORK = os.getenv("TRON_NETWORK", "nile")  # 默
payment_system = PaymentSystem(MASTER_PRIVATE_KEY,TRONGRID_API_KEY,NETWORK)
menu_system = MenuSystem()  # ⭐ 初始化菜单系统

# 初始化 Freqtrade 客户端
ft_api = FreqtradeAPIClient()
ft_commander = FreqtradeCommander()

# Bot配置
BOT_TOKEN = os.getenv("BOT_TOKEN", "8084831161:AAGbUGzo6nyggEtVowCAjUL_w76EiMDeZdQ")


# ========== ⭐ 辅助函数 ==========

def update_user_trading_status(user_id: int, is_trading: bool):
    """更新用户交易状态到数据库"""
    try:
        status = '运行中' if is_trading else '停止'
        db.update_user_status(user_id, status)
        logger.info(f"用户 {user_id} 状态更新为: {status}")
    except Exception as e:
        logger.error(f"更新用户状态失败: {e}")


async def safe_edit_message(msg, text: str, **kwargs):
    """安全地编辑消息，处理可能的异常"""
    try:

        await msg.edit_text(text, **kwargs)
        return True
    except Exception as e:
        logger.error(f"消息编辑失败: {e}")

        # 如果编辑失败，尝试发送新消息
        try:
            await msg.reply_text(text, **kwargs)
            return True
        except Exception as e2:
            logger.error(f"发送新消息也失败: {e2}")

            # 最后尝试不带格式发送
            try:
                import re
                clean_text = re.sub('<[^<]+?>', '', text)
                safe_kwargs = {k: v for k, v in kwargs.items()
                             if k != 'reply_markup' and k != 'parse_mode'}
                await msg.reply_text(clean_text[:4000], **safe_kwargs)
                return False
            except:
                return False


# ========== ⭐ 用户状态管理 ==========

def get_user_status(user_id: int) -> tuple:
    """
    获取用户状态和邀请码状态

    Returns:
        (UserStatus, has_invite_code)
    """
    if not db.user_exists(user_id):
        return UserStatus.NOT_REGISTERED, False

    user = db.get_user_by_telegram_id(user_id)

    # 检查是否有API密钥
    if not user.get('api_key'):
        return UserStatus.REGISTERED, False

    # ⭐ 检查是否已使用邀请码
    has_invite_code = bool(db.get_user_invite_code(user_id))

    # 检查交易状态
    status = user.get('status', '停止')
    if status == '运行中':
        return UserStatus.TRADING, has_invite_code
    else:
        return UserStatus.API_BOUND, has_invite_code


# ========== 查看配置命令 ==========
def extract_coin_from_pair(pair: str) -> str:
    """
    从交易对字符串中提取币种名称

    Args:
        pair: 交易对字符串，如 "AAVE/USDT:USDT" 或 "BTC/USDT"

    Returns:
        币种名称，如 "AAVE" 或 "BTC"

    Examples:
        >>> extract_coin_from_pair("AAVE/USDT:USDT")
        'AAVE'
        >>> extract_coin_from_pair("BTC/USDT")
        'BTC'
        >>> extract_coin_from_pair("ETH/USDT:USDT")
        'ETH'
    """
    # 去掉 :USDT 后缀（如果有）
    pair = pair.split(':')[0]

    # 提取 / 前面的币种
    coin = pair.split('/')[0]

    return coin


def get_user_trading_pairs(user_id: int, config_dir: str = "user_data") -> Tuple[bool, List[str]]:
    """
    获取用户配置的交易对列表（只返回币种名称）

    Args:
        user_id: 用户ID
        config_dir: 配置文件目录

    Returns:
        (成功标志, 币种列表)

    Examples:
        >>> success, coins = get_user_trading_pairs(12345)
        >>> if success:
        ...     print(coins)
        ['AAVE', 'ADA', 'AVAX', 'BNB', 'BTC', ...]
    """
    try:
        # 构建配置文件路径
        config_path = os.path.join("user_data", str(user_id), "config", "config.json")

        # 检查文件是否存在
        if not os.path.exists(config_path):
            return False, []

        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 获取 pair_whitelist
        pair_whitelist = config.get('exchange', {}).get('pair_whitelist', [])

        if not pair_whitelist:
            return False, []

        # 提取币种名称
        coins = [extract_coin_from_pair(pair) for pair in pair_whitelist]

        return True, coins

    except json.JSONDecodeError as e:
        print(f"❌ 配置文件JSON格式错误: {e}")
        return False, []
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return False, []


def format_pairs_display(coins: List[str], lang: str = "zh") -> str:
    """
    格式化交易对显示信息

    Args:
        coins: 币种列表
        lang: 语言 ("zh" 或 "en")

    Returns:
        格式化后的显示文本
    """
    if lang == "zh":
        header = "💱 <b>当前交易对</b>\n" + "=" * 30 + "\n\n"

        if not coins:
            return header + "暂无交易对配置\n\n使用 /bind 绑定API后自动配置"

        message = header
        message += f"📊 <b>交易对数量:</b> {len(coins)} 个\n\n"
        message += "<b>币种列表:</b>\n"

        # 每行显示5个币种
        for i in range(0, len(coins), 5):
            row_coins = coins[i:i + 5]
            message += "  " + " | ".join([f"<code>{coin}</code>" for coin in row_coins]) + "\n"

        message += f"\n💡 <b>说明:</b>\n"
        message += f"• 所有交易对均与 USDT 配对\n"
        message += f"• 支持做多和做空操作\n"
        #message += f"• 使用 /config 修改配置\n"

    else:  # English
        header = "💱 <b>Current Trading Pairs</b>\n" + "=" * 30 + "\n\n"

        if not coins:
            return header + "No trading pairs configured\n\nUse /bind to configure after binding API"

        message = header
        message += f"📊 <b>Total Pairs:</b> {len(coins)}\n\n"
        message += "<b>Coin List:</b>\n"

        # 5 coins per line
        for i in range(0, len(coins), 5):
            row_coins = coins[i:i + 5]
            message += "  " + " | ".join([f"<code>{coin}</code>" for coin in row_coins]) + "\n"

        message += f"\n💡 <b>Notes:</b>\n"
        message += f"• All pairs are paired with USDT\n"
        message += f"• Supports both long and short\n"
        #message += f"• Use /config to modify settings\n"

    return message


# ========== 邀请码相关命令 (添加到 bot.py) ==========

async def use_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """使用邀请码"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 检查参数
    if not context.args or len(context.args) != 1:
        lang = menu_system.get_user_language(user_id).value
        if lang == "zh":
            await update.message.reply_text(
                "📮 <b>使用邀请码</b>\n\n"
                "<b>使用方法:</b>\n"
                "<code>/invite 邀请码</code>\n\n"
                "<b>示例:</b>\n"
                "<code>/invite WELCOME10</code>\n\n"
                "💡 <b>优惠说明:</b>\n"
                "• 使用邀请码后充值可获得额外 <b>10%</b> 赠送\n"
                "• 您将自动获得专属邀请码\n"
                "• 邀请他人充值可获得 <b>10%</b> 奖励\n\n"
                "🎁 <b>系统邀请码:</b>\n"
                "• WELCOME10 - 新手专享\n"
                "• VIP20 - VIP通道 (20%)",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "📮 <b>Use Invite Code</b>\n\n"
                "<b>Usage:</b>\n"
                "<code>/invite CODE</code>\n\n"
                "<b>Example:</b>\n"
                "<code>/invite WELCOME10</code>\n\n"
                "💡 <b>Benefits:</b>\n"
                "• Get <b>10%</b> bonus when recharging\n"
                "• Get your own invite code\n"
                "• Earn <b>10%</b> reward from invitees\n\n"
                "🎁 <b>System Codes:</b>\n"
                "• WELCOME10 - For new users\n"
                "• VIP20 - VIP channel (20%)",
                parse_mode='HTML'
            )
        return

    code = context.args[0].upper()
    msg = await update.message.reply_text("🔄 正在验证邀请码...")

    # 应用邀请码
    success, discount, message, user_code = db.apply_invite_code(user_id, code)

    lang = menu_system.get_user_language(user_id).value

    if success:
        if lang == "zh":
            response = (
                f"🎉 <b>邀请码激活成功!</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎁 <b>使用的邀请码:</b> <code>{code}</code>\n"
                f"💰 <b>充值优惠:</b> 额外赠送 <b>{discount}%</b>\n\n"
                f"🔥 <b>您的专属邀请码:</b>\n"
                f"<code>{user_code}</code>\n\n"
                f"✅ 主菜单已更新为 \"我的邀请码\"\n"
                f"点击可查看邀请统计和管理邀请列表\n\n"
                f"🚀 立即充值享受优惠!\n"
                f"使用 /my_address 查看充值地址"
            )
        else:
            response = (
                f"🎉 <b>Invite Code Activated!</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎁 <b>Code Used:</b> <code>{code}</code>\n"
                f"💰 <b>Recharge Bonus:</b> Extra <b>{discount}%</b>\n\n"
                f"🔥 <b>Your Invite Code:</b>\n"
                f"<code>{user_code}</code>\n\n"
                f"✅ Menu updated to \"My Invite Code\"\n"
                f"Click to view stats and manage invitees\n\n"
                f"🚀 Recharge now!\n"
                f"Use /my_address"
            )

        await msg.edit_text(response, parse_mode='HTML')

        # ⭐ 自动更新主菜单 - 显示"我的邀请码"按钮
        user_status, _ = get_user_status(user_id)
        keyboard = menu_system.get_main_keyboard(user_id, user_status, has_invite_code=True)

        if lang == "zh":
            await update.message.reply_text(
                "📋 主菜单已更新",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                "📋 Main menu updated",
                reply_markup=keyboard
            )

        logger.info(f"用户 {user_id} 使用邀请码: {code}, 生成邀请码: {user_code}")
    else:
        if lang == "zh":
            response = f"❌ <b>邀请码无效</b>\n\n{message}\n\n💡 使用 /invite 查看使用说明"
        else:
            response = f"❌ <b>Invalid Invite Code</b>\n\n{message}\n\n💡 Use /invite for help"

        await msg.edit_text(response, parse_mode='HTML')


async def view_invite_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示邀请码子菜单"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 检查是否已使用邀请码
    user_code = db.get_user_invite_code(user_id)

    if not user_code:
        # 还没使用邀请码,引导用户使用
        lang = menu_system.get_user_language(user_id).value
        if lang == "zh":
            await update.message.reply_text(
                "❌ 您还没有使用邀请码\n\n"
                "请先使用邀请码激活:\n"
                "<code>/invite WELCOME10</code>\n\n"
                "激活后即可获得专属邀请码!",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "❌ You haven't used an invite code yet\n\n"
                "Please activate first:\n"
                "<code>/invite WELCOME10</code>\n\n"
                "Get your own code after activation!",
                parse_mode='HTML'
            )
        return

    # 切换到邀请码子菜单
    keyboard = menu_system.get_invite_keyboard(user_id)
    title = menu_system.get_text(user_id, "title", "invite_submenu")

    lang = menu_system.get_user_language(user_id).value

    if lang == "zh":
        message = (
            f"{title}\n\n"
            f"🔥 <b>您的专属邀请码:</b>\n"
            f"<code>{user_code}</code>\n\n"
            f"💡 选择下方功能查看详情:"
        )
    else:
        message = (
            f"{title}\n\n"
            f"🔥 <b>Your Invite Code:</b>\n"
            f"<code>{user_code}</code>\n\n"
            f"💡 Select a function below:"
        )

    await update.message.reply_text(message, reply_markup=keyboard, parse_mode='HTML')


async def my_invite_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看我的邀请统计 (子菜单入口)"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 获取邀请统计
    stats = db.get_invite_stats(user_id)

    lang = menu_system.get_user_language(user_id).value

    if not stats['my_code']:
        if lang == "zh":
            await update.message.reply_text("❌ 您还没有邀请码")
        else:
            await update.message.reply_text("❌ You don't have an invite code yet")
        return

    if lang == "zh":
        message = (
            "📊 <b>我的邀请统计</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🔥 <b>我的邀请码:</b>\n"
            f"<code>{stats['my_code']}</code>\n\n"
            f"👥 <b>已邀请人数:</b> {stats['invitee_count']} 人\n"
            f"💰 <b>累计奖励:</b> {stats['total_reward']:.2f} USDT\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        # 显示邀请人信息
        if stats['inviter_info']:
            inv = stats['inviter_info']
            message += (
                f"👤 <b>我的邀请人:</b>\n"
                f"• 姓名: {inv['name']}\n"
                f"• 邀请码: <code>{inv['code']}</code>\n"
                f"• 我为TA贡献: {inv['contributed_reward']:.2f} USDT\n\n"
            )

        message += (
            f"💎 <b>邀请奖励规则:</b>\n"
            f"• 好友使用您的邀请码注册\n"
            f"• 好友每次充值,您获得 <b>10%</b> 奖励\n"
            f"• 好友充值 100 USDT → 您获得 <b>10 USDT</b>\n"
            f"• 好友充值 1000 USDT → 您获得 <b>100 USDT</b>\n\n"
            f"💬 <b>分享您的邀请码:</b>\n"
            f"让朋友使用命令:\n"
            f"<code>/invite {stats['my_code']}</code>"
        )
    else:
        message = (
            "📊 <b>My Invite Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🔥 <b>My Invite Code:</b>\n"
            f"<code>{stats['my_code']}</code>\n\n"
            f"👥 <b>Invitees:</b> {stats['invitee_count']}\n"
            f"💰 <b>Total Rewards:</b> {stats['total_reward']:.2f} USDT\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        if stats['inviter_info']:
            inv = stats['inviter_info']
            message += (
                f"👤 <b>My Inviter:</b>\n"
                f"• Name: {inv['name']}\n"
                f"• Code: <code>{inv['code']}</code>\n"
                f"• Contributed: {inv['contributed_reward']:.2f} USDT\n\n"
            )

        message += (
            f"💎 <b>Reward Rules:</b>\n"
            f"• Friends use your code\n"
            f"• Earn <b>10%</b> of their recharge\n"
            f"• 100 USDT → <b>10 USDT</b> reward\n"
            f"• 1000 USDT → <b>100 USDT</b> reward\n\n"
            f"💬 <b>Share your code:</b>\n"
            f"Let friends use:\n"
            f"<code>/invite {stats['my_code']}</code>"
        )

    await update.message.reply_text(message, parse_mode='HTML')


async def my_invitees_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看我邀请的用户列表 (子菜单入口)"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 获取邀请列表
    invitees = db.get_user_invitees(user_id, limit=20)
    stats = db.get_invite_stats(user_id)

    lang = menu_system.get_user_language(user_id).value

    if not stats['my_code']:
        if lang == "zh":
            await update.message.reply_text("❌ 您还没有邀请码")
        else:
            await update.message.reply_text("❌ You don't have an invite code yet")
        return

    if lang == "zh":
        message = (
            "👥 <b>我邀请的用户</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 <b>总计:</b> {len(invitees)} 人\n"
            f"💰 <b>累计奖励:</b> {stats['total_reward']:.2f} USDT\n\n"
        )

        if invitees:
            message += "━━━━━━━━━━━━━━━━━━\n\n"
            for i, inv in enumerate(invitees[:10], 1):
                reward = inv['reward_contributed']
                date = inv['invited_at'][:10] if inv['invited_at'] else 'N/A'
                message += (
                    f"<b>{i}. {inv['name']}</b>\n"
                    f"   💎 贡献奖励: {reward:.2f} USDT\n"
                    f"   📅 邀请时间: {date}\n\n"
                )

            if len(invitees) > 10:
                message += f"... 还有 {len(invitees) - 10} 位用户\n\n"
        else:
            message += "📭 暂无邀请记录\n\n"
            message += "💡 分享您的邀请码开始赚取奖励!\n\n"

        message += (
            f"🎁 <b>您的邀请码:</b>\n"
            f"<code>{stats['my_code']}</code>\n\n"
            f"💬 让朋友使用: <code>/invite {stats['my_code']}</code>"
        )
    else:
        message = (
            "👥 <b>My Invitees</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 <b>Total:</b> {len(invitees)} users\n"
            f"💰 <b>Total Rewards:</b> {stats['total_reward']:.2f} USDT\n\n"
        )

        if invitees:
            message += "━━━━━━━━━━━━━━━━━━\n\n"
            for i, inv in enumerate(invitees[:10], 1):
                reward = inv['reward_contributed']
                date = inv['invited_at'][:10] if inv['invited_at'] else 'N/A'
                message += (
                    f"<b>{i}. {inv['name']}</b>\n"
                    f"   💎 Rewards: {reward:.2f} USDT\n"
                    f"   📅 Date: {date}\n\n"
                )

            if len(invitees) > 10:
                message += f"... and {len(invitees) - 10} more\n\n"
        else:
            message += "📭 No invitees yet\n\n"
            message += "💡 Share your code to start earning!\n\n"

        message += (
            f"🎁 <b>Your Code:</b>\n"
            f"<code>{stats['my_code']}</code>\n\n"
            f"💬 Let friends use: <code>/invite {stats['my_code']}</code>"
        )

    await update.message.reply_text(message, parse_mode='HTML')


# ⭐ 新增: 分享邀请码功能
async def share_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """分享邀请码"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 获取用户邀请码
    user_code = db.get_user_invite_code(user_id)
    stats = db.get_invite_stats(user_id)

    lang = menu_system.get_user_language(user_id).value

    if not user_code:
        if lang == "zh":
            await update.message.reply_text("❌ 您还没有邀请码")
        else:
            await update.message.reply_text("❌ You don't have an invite code yet")
        return

    if lang == "zh":
        message = (
            "💬 <b>分享您的邀请码</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🔥 <b>您的专属邀请码:</b>\n"
            f"<code>{user_code}</code>\n\n"
            f"📊 <b>当前数据:</b>\n"
            f"• 已邀请: {stats['invitee_count']} 人\n"
            f"• 累计奖励: {stats['total_reward']:.2f} USDT\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 <b>推荐话术:</b>\n\n"
            f"「嗨!我在使用一个自动交易机器人,收益不错!\n\n"
            f"使用我的邀请码注册,充值可额外获得10%赠送:\n"
            f"<code>/invite {user_code}</code>\n\n"
            f"我们都能获得奖励,一起赚钱!💰」\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 <b>分享技巧:</b>\n"
            f"• 复制上方话术发给朋友\n"
            f"• 强调双向收益\n"
            f"• 分享您的使用体验\n"
            f"• 好友充值越多,您赚得越多!"
        )
    else:
        message = (
            "💬 <b>Share Your Invite Code</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🔥 <b>Your Code:</b>\n"
            f"<code>{user_code}</code>\n\n"
            f"📊 <b>Current Stats:</b>\n"
            f"• Invitees: {stats['invitee_count']}\n"
            f"• Total Rewards: {stats['total_reward']:.2f} USDT\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📝 <b>Suggested Message:</b>\n\n"
            f"「Hi! I'm using an auto-trading bot with great results!\n\n"
            f"Use my invite code to register and get 10% bonus:\n"
            f"<code>/invite {user_code}</code>\n\n"
            f"We both earn rewards. Let's make money together!💰」\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 <b>Sharing Tips:</b>\n"
            f"• Copy the message above\n"
            f"• Emphasize win-win benefits\n"
            f"• Share your experience\n"
            f"• More they recharge, more you earn!"
        )

    await update.message.reply_text(message, parse_mode='HTML')


async def my_invite_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """快捷命令: /my_invite - 直接查看邀请统计"""
    await my_invite_stats(update, context)


# ========== 集成到 bot.py 的函数 ==========

async def view_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    查看当前交易对命令

    用法: /pairs 或 点击 "查看交易对" 按钮
    """
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 检查是否绑定API
    user = db.get_user_by_telegram_id(user_id)
    if not user.get('api_key'):
        lang = menu_system.get_user_language(user_id).value
        if lang == "zh":
            await update.message.reply_text(
                "❌ 请先绑定API!\n\n"
                "使用 /bind 命令绑定交易所API"
            )
        else:
            await update.message.reply_text(
                "❌ Please bind API first!\n\n"
                "Use /bind command to bind exchange API"
            )
        return

    msg = await update.message.reply_text("🔄 正在获取交易对...")

    # 获取交易对列表
    success, coins = get_user_trading_pairs(user_id)

    if not success:
        await msg.edit_text("❌ 获取交易对失败\n\n配置文件不存在或格式错误")
        return

    # 格式化并显示
    lang = menu_system.get_user_language(user_id).value
    message = format_pairs_display(coins, lang)

    await msg.edit_text(message, parse_mode='HTML')
    logger.info(f"用户 {user_id} 查看交易对: {len(coins)}个")


# ========== 基础命令 ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """启动命令 - 显示动态主菜单"""
    user_id = update.message.from_user.id
    #user_status = get_user_status(user_id)

    # ⭐ 获取动态键盘
    user_status, has_invite_code = get_user_status(user_id)  # ⭐ 获取邀请码状态

    # 生成主菜单键盘
    keyboard = menu_system.get_main_keyboard(user_id, user_status, has_invite_code)  # ⭐ 传入参数

    # ⭐ 获取本地化欢迎文本
    lang = menu_system.get_user_language(user_id).value
    if lang == "zh":
        welcome_text = (
            "🤖 <b>自助量化交易机器人</b>\n\n"
            "欢迎使用EasyMoney量化交易系统!\n\n"
            "📋 <b>功能特点:</b>\n"
            "• 基于自研的两层三模型的AIAgent自动执行交易指令\n"
            "• 高收益率（复合APY 80%以上），实时盈亏监控\n"
            "• 多币种同时操作，既能做多也能做空\n"
            "• 灵活配置管理\n\n"
            "💡 <b>快速开始:</b>\n"
            "1️⃣ 点击 '📝 注册' 创建账户\n"
            "2️⃣ 使用 /bind 绑定交易所API\n"
            "3️⃣ 充值并订阅套餐\n"
            "4️⃣ 订阅成功后，点击 '▶️ 启动交易' 开始量化\n\n"
            "❓ 需要帮助? 点击 '❓ 帮助'\n"
            "白皮书参考：https://easymoney.gitbook.io/main/docs-2"
        )
    else:
        welcome_text = (
            "🤖 <b>Self-Service Quantitative Trading Bot</b>\n\n"
            "Welcome to the EasyMoney Quantitative Trading System!\n\n"
            "📋 <b>Features:</b>\n"
            "• Based on our proprietary two-layer, three-model AIAgent for automatic trading execution\n"
            "• High return rates (compound APY above 80%), real-time profit and loss monitoring\n"
            "• Multi-currency operation, capable of both long and short trades\n"
            "• Flexible configuration management\n\n"
            "💡 <b>Quick Start:</b>\n"
            "1️⃣ Click '📝 Register' to create an account\n"
            "2️⃣ Use /bind to link your exchange API\n"
            "3️⃣ Deposit funds and subscribe to a plan\n"
            "4️⃣ Once subscribed, click '▶️ Start Trading' to begin quantitative trading\n\n"
            "❓ Need help? Click '❓ Help'\n"
            "WhitePaper：https://easymoney.gitbook.io/main/docs-2"
        )

    await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode='HTML')
    logger.info(f"用户 {user_id} 启动机器人")


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """注册用户"""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.username or update.message.from_user.first_name

    # 速率限制
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⚠️ 操作过于频繁,请稍后再试")
        return

    if db.user_exists(user_id):
        await update.message.reply_text(f"ℹ️ 用户 {user_name} 已经注册过了!")
        logger.info(f"用户 {user_id} 尝试重复注册")
    else:
        new_user_id = db.insert_user(user_id, user_name)
        if new_user_id:
            # 创建用户目录
            config_manager.create_user_directory(user_id)

            # ⭐ 更新菜单
            user_status, has_invite_code = get_user_status(user_id)
            keyboard = menu_system.get_main_keyboard(user_id, user_status)

            lang = menu_system.get_user_language(user_id).value
            if lang == "zh":
                success_msg = (
                    f"✅ 欢迎,{user_name}!\n\n"
                    f"📝 注册成功\n"
                    f"🆔 系统ID: {new_user_id}\n\n"
                    f"<b>下一步:</b>\n"
                    f"请使用 /bind 命令绑定您的币安API密钥\n\n"
                    f"获取币安API的操作指南：https://easymoney.gitbook.io/main/docs-2/bi-an-api-dao-chu-ji-bang-ding-jiao-cheng\n"
                    f"<b>格式:</b>\n"                    
                    f"<code>/bind API_KEY SECRET</code>"

                )
            else:
                success_msg = (
                    f"✅ Welcome, {user_name}!\n\n"
                    f"📝 Registration successful\n"
                    f"🆔 System ID: {new_user_id}\n\n"
                    f"<b>Next Step:</b>\n"
                    f"Please use /bind command to bind your Binance API\n\n"
                    f"How to Get Your Binance API Key：https://easymoney.gitbook.io/main/binance-api-export-and-binding-tutorial\n"
                    f"<b>Format:</b>\n"
                    f"<code>/bind API_KEY SECRET</code>"
                )

            await update.message.reply_text(
                success_msg,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            logger.info(f"用户 {user_id} ({user_name}) 注册成功")
        else:
            await update.message.reply_text("❌ 注册失败,请稍后再试")
            logger.error(f"用户 {user_id} 注册失败")


async def bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """绑定API密钥"""
    user_id = update.message.from_user.id

    # 检查用户是否注册
    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 速率限制
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⚠️ 操作过于频繁,请稍后再试")
        return

    # 检查参数
    if len(context.args) != 2:
        lang = menu_system.get_user_language(user_id).value
        if lang == "zh":
            error_msg = (
                "❌ 使用格式错误!\n\n"
                "<b>正确格式:</b>\n"
                "<code>/bind API_KEY SECRET</code>\n\n"
                "<b>示例:</b>\n"
                "<code>/bind your_api_key your_secret_key</code>"
            )
        else:
            error_msg = (
                "❌ Invalid format!\n\n"
                "<b>Correct format:</b>\n"
                "<code>/bind API_KEY SECRET</code>\n\n"
                "<b>Example:</b>\n"
                "<code>/bind your_api_key your_secret_key</code>"
            )
        await update.message.reply_text(error_msg, parse_mode='HTML')
        return

    api_key = context.args[0]
    secret = context.args[1]

    # 验证API
    msg = await update.message.reply_text("🔄 正在验证API密钥...")

    is_valid, error_msg = validate_binance_api(api_key, secret)

    if not is_valid:
        await msg.edit_text(f"❌ API验证失败\n\n{error_msg}")
        logger.warning(f"用户 {user_id} API验证失败: {error_msg}")
        return

    # 保存API到数据库
    db.update_user_api(user_id, secret, api_key)

    # 创建用户配置文件
    if config_manager.create_user_config(user_id, api_key, secret):
        api_port = config_manager.get_user_api_port(user_id)

        # ⭐ 更新菜单
        user_status, has_invite_code = get_user_status(user_id)
        keyboard = menu_system.get_main_keyboard(user_id, user_status)

        lang = menu_system.get_user_language(user_id).value
        if lang == "zh":
            success_msg = (
                "✅ API绑定成功!\n\n"
                "🎉 配置文件已创建\n"
                "🌐 REST API 已启用\n"
                f"🔌 API端口: {api_port}\n"
                "✨ 您现在可以启动交易机器人了\n\n"
                "<b>下一步:</b>\n"
                "• 充值USDT到专属地址\n"
                "• 系统自动订阅套餐\n"
                "• 点击 '▶️ 启动交易' 开始"
            )
        else:
            success_msg = (
                "✅ API bound successfully!\n\n"
                "🎉 Configuration file created\n"
                "🌐 REST API enabled\n"
                f"🔌 API Port: {api_port}\n"
                "✨ You can now start the trading bot\n\n"
                "<b>Next Steps:</b>\n"
                "• Recharge USDT to your address\n"
                "• System will auto-subscribe\n"
                "• Click '▶️ Start Trading' to begin"
            )

        await msg.edit_text(success_msg, parse_mode='HTML')
        main_menu_text = "📋 主菜单已更新" if lang == "zh" else "📋 Main menu updated"
        await update.message.reply_text(main_menu_text, reply_markup=keyboard)

        logger.info(f"用户 {user_id} API绑定成功, API端口: {api_port}")
    else:
        await msg.edit_text(
            "⚠️ API已保存,但配置文件创建失败\n\n"
            "请联系管理员检查系统配置"
        )
        logger.error(f"用户 {user_id} 配置文件创建失败")


# ========== ⭐ 语言切换 ==========

async def switch_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """切换语言"""
    user_id = update.message.from_user.id

    # 切换语言
    success_msg = menu_system.switch_language(user_id)

    # 更新菜单
    user_status, has_invite_code = get_user_status(user_id)
    keyboard = menu_system.get_main_keyboard(user_id, user_status)

    await update.message.reply_text(
        f"✅ {success_msg}",
        reply_markup=keyboard
    )
    logger.info(f"用户 {user_id} 切换语言")


# ========== ⭐ 子菜单导航 ==========

async def view_status_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示状态查看子菜单"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 切换到状态子菜单
    keyboard = menu_system.get_status_keyboard(user_id)
    title = menu_system.get_text(user_id, "title", "status_submenu")

    await update.message.reply_text(
        f"{title}\n\n请选择要查看的内容:",
        reply_markup=keyboard
    )


async def view_config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示配置管理子菜单"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 切换到配置子菜单
    keyboard = menu_system.get_config_keyboard(user_id)
    title = menu_system.get_text(user_id, "title", "config_submenu")

    await update.message.reply_text(
        f"{title}\n\n请选择操作:",
        reply_markup=keyboard
    )


async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """返回主菜单"""
    user_id = update.message.from_user.id
    user_status, has_invite_code = get_user_status(user_id)  # ⭐ 获取邀请码状态
    keyboard = menu_system.get_main_keyboard(user_id, user_status, has_invite_code)

    lang = menu_system.get_user_language(user_id).value
    main_menu_text = "📋 主菜单" if lang == "zh" else "📋 Main Menu"

    await update.message.reply_text(main_menu_text, reply_markup=keyboard)


# ========== 帮助命令 ==========

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """帮助命令"""
    user_id = update.message.from_user.id
    help_text = menu_system.get_help_text(user_id)

    await update.message.reply_text(help_text, parse_mode='HTML')


# ========== 💰 支付和订阅管理命令 ==========

async def my_payment_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看我的充值地址和订阅状态"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 获取用户地址
    address = payment_system.get_user_address(user_id)

    # 获取订阅状态
    status = payment_system.get_subscription_status(user_id)

    lang = menu_system.get_user_language(user_id).value

    if lang == "zh":
        message = (
            "💰 <b>我的充值信息</b>\n"
            "=" * 30 + "\n\n"
            f"<b>您的专属充值地址 (TRC20):</b>\n"
            f"<code>{address}</code>\n\n"
            f"💵 <b>当前余额:</b> {status['balance']:.2f} USDT\n\n"
        )

        if status['active']:
            message += (
                f"✅ <b>订阅状态:</b> {status['message']}\n"
                f"📦 <b>套餐:</b> {status['plan_name']}\n"
                f"💰 <b>最大资金:</b> {status['max_capital']:,.0f} USDT\n"
                f"📅 <b>到期时间:</b> {status['end_date']}\n"
                f"⏳ <b>剩余:</b> {status['days_left']} 天\n\n"
            )
        else:
            message += f"❌ <b>订阅状态:</b> {status['message']}\n\n"

        message += (
            f"<b>💡 充值说明:</b>\n"
            f"1. 复制上方地址\n"
            f"2. 在钱包中发送 USDT (TRC20网络)\n"
            f"3. 系统将自动检测并确认充值\n"
            f"4. 余额到账后自动订阅套餐\n\n"
            f"⚠️ 请务必使用 <b>TRC20</b> 网络!\n"
            f"⚠️ 充值通常在 1-5 分钟内到账\n\n"
            f"💎 使用 /plans 查看套餐详情"
        )
    else:
        message = (
            "💰 <b>My Recharge Information</b>\n"
            "=" * 30 + "\n\n"
            f"<b>Your Exclusive Address (TRC20):</b>\n"
            f"<code>{address}</code>\n\n"
            f"💵 <b>Current Balance:</b> {status['balance']:.2f} USDT\n\n"
        )

        if status['active']:
            message += (
                f"✅ <b>Subscription:</b> {status['message']}\n"
                f"📦 <b>Plan:</b> {status['plan_name']}\n"
                f"💰 <b>Max Capital:</b> {status['max_capital']:,.0f} USDT\n"
                f"📅 <b>Expires:</b> {status['end_date']}\n"
                f"⏳ <b>Remaining:</b> {status['days_left']} days\n\n"
            )
        else:
            message += f"❌ <b>Subscription:</b> {status['message']}\n\n"

        message += (
            f"<b>💡 Recharge Instructions:</b>\n"
            f"1. Copy the address above\n"
            f"2. Send USDT via TRC20 network\n"
            f"3. System will auto-detect payment\n"
            f"4. Auto-subscribe after balance received\n\n"
            f"⚠️ Must use <b>TRC20</b> network!\n"
            f"⚠️ Usually arrives in 1-5 minutes\n\n"
            f"💎 Use /plans to view plan details"
        )

    await update.message.reply_text(message, parse_mode='HTML')


async def subscription_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看订阅详情"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    subscription = db.get_user_subscription(user_id)
    balance = db.get_user_balance(user_id)

    lang = menu_system.get_user_language(user_id).value

    if lang == "zh":
        message = "📋 <b>订阅详情</b>\n" + "=" * 30 + "\n\n"
        message += f"💰 账户余额: <b>{balance:.2f} USDT</b>\n\n"

        if subscription:
            is_valid, _ = db.is_subscription_valid(user_id)
            status_emoji = "✅" if is_valid else "❌"

            end_date = datetime.fromisoformat(subscription['end_date'])
            days_left = (end_date - datetime.now()).days

            message += f"{status_emoji} <b>订阅状态:</b> {'有效' if is_valid else '已过期'}\n"
            message += f"📦 <b>套餐:</b> {subscription['plan_name']}\n"
            message += f"💵 <b>最大资金:</b> {subscription['max_capital']:,.0f} USDT\n"

            # 格式化日期
            start_date = subscription['start_date']
            end_date_str = subscription['end_date']
            if 'T' in start_date:
                start_date = start_date.replace('T', ' ').split('.')[0]
            if 'T' in end_date_str:
                end_date_str = end_date_str.replace('T', ' ').split('.')[0]

            message += f"📅 <b>开始时间:</b> {start_date}\n"
            message += f"📅 <b>到期时间:</b> {end_date_str}\n"

            if is_valid:
                message += f"⏳ <b>剩余天数:</b> {days_left} 天\n"
        else:
            message += "❌ 未订阅\n\n"
            message += "💡 充值 USDT 后将自动订阅\n"
            message += "💡 使用 /my_address 查看充值地址"
    else:
        message = "📋 <b>Subscription Details</b>\n" + "=" * 30 + "\n\n"
        message += f"💰 Account Balance: <b>{balance:.2f} USDT</b>\n\n"

        if subscription:
            is_valid, _ = db.is_subscription_valid(user_id)
            status_emoji = "✅" if is_valid else "❌"

            end_date = datetime.fromisoformat(subscription['end_date'])
            days_left = (end_date - datetime.now()).days

            message += f"{status_emoji} <b>Status:</b> {'Active' if is_valid else 'Expired'}\n"
            message += f"📦 <b>Plan:</b> {subscription['plan_name']}\n"
            message += f"💵 <b>Max Capital:</b> {subscription['max_capital']:,.0f} USDT\n"

            # Format dates
            start_date = subscription['start_date']
            end_date_str = subscription['end_date']
            if 'T' in start_date:
                start_date = start_date.replace('T', ' ').split('.')[0]
            if 'T' in end_date_str:
                end_date_str = end_date_str.replace('T', ' ').split('.')[0]

            message += f"📅 <b>Start Date:</b> {start_date}\n"
            message += f"📅 <b>Expiry Date:</b> {end_date_str}\n"

            if is_valid:
                message += f"⏳ <b>Days Left:</b> {days_left} days\n"
        else:
            message += "❌ Not Subscribed\n\n"
            message += "💡 Will auto-subscribe after recharge\n"
            message += "💡 Use /my_address for recharge address"

    await update.message.reply_text(message, parse_mode='HTML')


async def view_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看订阅套餐"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    plans = db.get_all_plans()
    lang = menu_system.get_user_language(user_id).value

    if lang == "zh":
        message = "💎 <b>订阅套餐</b>\n" + "=" * 40 + "\n\n"

        for plan in plans:
            message += f"<b>{plan['plan_name']}</b>\n"
            message += f"💰 月费率: <b>{plan['monthly_rate']:.3f} /月</b>\n"
            message += f"📊 标准资金: <b>{plan['standard_capital']:,.0f} USDT</b>\n"
            message += f"💳 最低充值: <b>{plan['min_payment']:,.0f} USDT</b>\n"
            message += f"📝 {plan['description']}\n"
            message += "─" * 40 + "\n\n"

        message += "💡 <b>说明:</b>\n"
        message += "• 充值后系统自动订阅对应套餐\n"
        message += "• 标准资金为建议操作金额\n"
        message += "• 订阅期内可随时启停交易\n\n"
        message += "使用 /my_address 查看充值地址"
    else:
        message = "💎 <b>Subscription Plans</b>\n" + "=" * 40 + "\n\n"

        for plan in plans:
            message += f"<b>{plan['plan_name']}</b>\n"
            message += f"💰 Monthly Rate: <b>{plan['monthly_rate']:.2%} USDT/month</b>\n"
            message += f"📊 Standard Capital: <b>{plan['standard_capital']:,.0f} USDT</b>\n"
            message += f"💳 Min Payment: <b>{plan['min_payment']:,.0f} USDT</b>\n"
            message += f"📝 {plan['description']}\n"
            message += "─" * 40 + "\n\n"

        message += "💡 <b>Notes:</b>\n"
        message += "• Auto-subscribe after recharge\n"
        message += "• Standard capital is recommended amount\n"
        message += "• Start/stop trading anytime\n\n"
        message += "Use /my_address for recharge"

    await update.message.reply_text(message, parse_mode='HTML')


async def recharge_records(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看充值记录"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    records = db.get_user_recharge_records(user_id, limit=10)

    lang = menu_system.get_user_language(user_id).value

    if lang == "zh":
        message = "📜 <b>充值记录</b> (最近10条)\n" + "=" * 30 + "\n\n"

        if not records:
            message += "暂无充值记录\n\n"
            message += "使用 /my_address 查看充值地址"
        else:
            for record in records:
                status_emoji = "✅" if record['status'] == 'completed' else "⏳"
                message += f"{status_emoji} <b>{record['amount']:.2f} USDT</b>\n"

                created_time = record['created_at'].replace('T', ' ').split('.')[0]
                message += f"  时间: {created_time}\n"

                if record['tx_hash']:
                    tx_short = f"{record['tx_hash'][:8]}...{record['tx_hash'][-6:]}"
                    message += f"  哈希: <code>{tx_short}</code>\n"

                message += "\n"
    else:
        message = "📜 <b>Recharge History</b> (Last 10)\n" + "=" * 30 + "\n\n"

        if not records:
            message += "No recharge records\n\n"
            message += "Use /my_address for recharge address"
        else:
            for record in records:
                status_emoji = "✅" if record['status'] == 'completed' else "⏳"
                message += f"{status_emoji} <b>{record['amount']:.2f} USDT</b>\n"

                created_time = record['created_at'].replace('T', ' ').split('.')[0]
                message += f"  Time: {created_time}\n"

                if record['tx_hash']:
                    tx_short = f"{record['tx_hash'][:8]}...{record['tx_hash'][-6:]}"
                    message += f"  Hash: <code>{tx_short}</code>\n"

                message += "\n"

    await update.message.reply_text(message, parse_mode='HTML')


# ========== 交易控制命令 ==========

async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """启动交易机器人(添加订阅检查)"""
    user_id = update.message.from_user.id

    logger.info(f"📍 [STEP 1] 用户 {user_id} 准备启动服务")

    if not db.user_exists(user_id):
        logger.info(f"📍 [STEP 1.1] 用户 {user_id} 不存在")
        await update.message.reply_text("❌ 请先注册!")
        return

    logger.info(f"📍 [STEP 2] 用户 {user_id} 通过用户存在检查")

    # 速率限制
    if not rate_limiter.is_allowed(user_id):
        logger.info(f"📍 [STEP 2.1] 用户 {user_id} 触发速率限制")
        await update.message.reply_text("⚠️ 操作过于频繁,请稍后再试")
        return

    logger.info(f"📍 [STEP 3] 用户 {user_id} 开始检查订阅状态")

    # ⭐ 检查订阅状态
    try:
        status = payment_system.get_subscription_status(user_id)
        logger.info(f"📍 [STEP 3.1] 用户 {user_id} 订阅状态: {status}")
    except Exception as e:
        logger.error(f"❌ [STEP 3.1 ERROR] 获取订阅状态失败: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 获取订阅状态失败: {str(e)}")
        return

    if not status['active']:
        logger.info(f"📍 [STEP 3.2] 用户 {user_id} 订阅未激活")
        address = status['address']
        balance = status['balance']

        lang = menu_system.get_user_language(user_id).value
        if lang == "zh":
            message = (
                f"❌ 无法启动交易\n\n"
                f"原因: {status['message']}\n\n"
                f"💰 当前余额: {balance:.2f} USDT\n"
                f"📍 您的充值地址:\n"
                f"<code>{address}</code>\n\n"
                f"💡 请充值 USDT 到上方地址\n"
                f"💡 系统将自动订阅并激活服务\n\n"
                f"使用 /my_address 查看充值详情"
            )
        else:
            message = (
                f"❌ Cannot start trading\n\n"
                f"Reason: {status['message']}\n\n"
                f"💰 Current Balance: {balance:.2f} USDT\n"
                f"📍 Your Recharge Address:\n"
                f"<code>{address}</code>\n\n"
                f"💡 Please recharge USDT to the address\n"
                f"💡 System will auto-subscribe\n\n"
                f"Use /my_address for details"
            )

        await update.message.reply_text(message, parse_mode='HTML')
        return

    logger.info(f"📍 [STEP 4] 用户 {user_id} 检查 API 绑定")

    # 检查是否绑定API
    try:
        user = db.get_user_by_telegram_id(user_id)
        logger.info(f"📍 [STEP 4.1] 用户 {user_id} 数据: {user.get('api_key', 'None')[:10]}...")
    except Exception as e:
        logger.error(f"❌ [STEP 4.1 ERROR] 获取用户数据失败: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 获取用户数据失败: {str(e)}")
        return

    if not user.get('api_key') or not user.get('security'):
        logger.info(f"📍 [STEP 4.2] 用户 {user_id} API 未绑定")
        await update.message.reply_text("❌ 请先绑定API密钥!\n\n使用 /bind 命令绑定")
        return

    logger.info(f"📍 [STEP 5] 用户 {user_id} 检查配置文件")

    # 检查配置文件
    if not config_manager.config_exists(user_id):
        logger.info(f"📍 [STEP 5.1] 用户 {user_id} 配置文件不存在")
        await update.message.reply_text("❌ 配置文件不存在,请重新绑定API")
        return

    logger.info(f"📍 [STEP 6] 用户 {user_id} 开始发送启动消息")

    try:
        msg = await update.message.reply_text("🔄 正在启动交易机器人...")
        logger.info(f"📍 [STEP 6.1] 用户 {user_id} 启动消息已发送")
    except Exception as e:
        logger.error(f"❌ [STEP 6.1 ERROR] 发送消息失败: {e}", exc_info=True)
        return

    try:
        logger.info(f"📍 [STEP 7] 用户 {user_id} 调用 swarm_manager.create_service")

        # 创建服务
        success, message = swarm_manager.create_service(user_id)

        logger.info(f"📍 [STEP 7.1] 用户 {user_id} create_service 返回: success={success}, message={message}")

        if success:
            logger.info(f"📍 [STEP 8] 用户 {user_id} 更新交易状态")

            # ⭐⭐ 关键修复: 立即更新数据库状态
            update_user_trading_status(user_id, True)

            logger.info(f"📍 [STEP 8.1] 用户 {user_id} 交易状态已更新")

            lang = menu_system.get_user_language(user_id).value
            if lang == "zh":
                success_text = (
                    f"✅ 启动成功!\n\n"
                    f"{message}\n\n"
                    f"💰 最大操作资金: {status['max_capital']:,.0f} USDT\n"
                    f"📅 订阅到期: {status['end_date']}\n"
                    f"⏳ 剩余: {status['days_left']} 天\n\n"
                    f"🤖 交易机器人已启动\n"
                    f"📊 使用 /profit 查看利润\n"
                    f"📈 使用 /performance 查看性能"
                )
            else:
                success_text = (
                    f"✅ Started successfully!\n\n"
                    f"{message}\n\n"
                    f"💰 Max Capital: {status['max_capital']:,.0f} USDT\n"
                    f"📅 Expires: {status['end_date']}\n"
                    f"⏳ Remaining: {status['days_left']} days\n\n"
                    f"🤖 Trading bot is running\n"
                    f"📊 Use /profit to view profit\n"
                    f"📈 Use /performance for stats"
                )

            logger.info(f"📍 [STEP 9] 用户 {user_id} 获取菜单键盘")

            # ⭐ 更新菜单为交易状态
            user_status, has_invite_code = get_user_status(user_id)
            keyboard = menu_system.get_main_keyboard(user_id, user_status, has_invite_code)

            logger.info(f"📍 [STEP 9.1] 用户 {user_id} 准备编辑消息")

            # 使用安全的编辑函数
            await safe_edit_message(msg, success_text, reply_markup=keyboard, parse_mode='HTML')

            logger.info(f"✅ [COMPLETE] 用户 {user_id} 启动服务成功")
        else:
            logger.info(f"📍 [STEP 8 FAILED] 用户 {user_id} 启动失败")

            # 启动失败，确保状态是停止
            update_user_trading_status(user_id, False)

            # 更新菜单
            user_status, has_invite_code = get_user_status(user_id)
            keyboard = menu_system.get_main_keyboard(user_id, user_status, has_invite_code)

            await safe_edit_message(
                msg,
                f"❌ 启动失败\n\n{message}",
                reply_markup=keyboard
            )
            logger.error(f"❌ [FAILED] 用户 {user_id} 启动服务失败: {message}")

    except Exception as e:
        logger.error(f"❌ [EXCEPTION] 启动机器人时发生异常: {e}", exc_info=True)

        # 确保状态正确
        update_user_trading_status(user_id, False)

        # 恢复菜单
        user_status, has_invite_code = get_user_status(user_id)
        keyboard = menu_system.get_main_keyboard(user_id, user_status, has_invite_code)

        await safe_edit_message(
            msg,
            f"❌ 启动过程中发生错误: {str(e)}",
            reply_markup=keyboard
        )


async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """停止交易机器人(改进版 - 确保状态同步)"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 速率限制
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⚠️ 操作过于频繁,请稍后再试")
        return

    msg = await update.message.reply_text("🔄 正在停止交易机器人...")

    try:
        success, message = swarm_manager.stop_service(user_id)

        # ⭐⭐ 关键修复: 无论成功与否，更新数据库状态
        if success or "已停止" in message or "不存在" in message:
            update_user_trading_status(user_id, False)

        # ⭐ 更新菜单为停止状态
        user_status, has_invite_code = get_user_status(user_id)
        keyboard = menu_system.get_main_keyboard(user_id, user_status, has_invite_code)

        if success:
            await safe_edit_message(
                msg,
                f"✅ 已停止\n\n{message}",
                reply_markup=keyboard
            )
            logger.info(f"用户 {user_id} 停止服务")
        else:
            await safe_edit_message(
                msg,
                f"⚠️ {message}",
                reply_markup=keyboard
            )
            logger.warning(f"用户 {user_id} 停止服务: {message}")

    except Exception as e:
        logger.error(f"停止机器人时发生异常: {e}")

        # 假设停止成功，更新状态
        update_user_trading_status(user_id, False)

        # 恢复菜单
        user_status, has_invite_code = get_user_status(user_id)
        keyboard = menu_system.get_main_keyboard(user_id, user_status, has_invite_code)

        await safe_edit_message(
            msg,
            f"⚠️ 停止过程中发生错误，但可能已停止\n\n{str(e)}",
            reply_markup=keyboard
        )


async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """重启交易机器人"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    msg = await update.message.reply_text("🔄 正在重启交易机器人...")

    success, message = swarm_manager.restart_service(user_id)

    if success:
        await msg.edit_text(f"✅ 重启成功\n\n{message}")
        logger.info(f"用户 {user_id} 重启服务")
    else:
        await msg.edit_text(f"❌ 重启失败\n\n{message}")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看状态"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    msg = await update.message.reply_text("🔄 正在获取状态...")

    user = db.get_user_by_telegram_id(user_id)
    status_info = swarm_manager.get_service_status(user_id)

    lang = menu_system.get_user_language(user_id).value

    if lang == "zh":
        status_text = f"👤 用户信息\n\n"
        status_text += f"📝 用户名: {user['name']}\n"
        status_text += f"🔑 API状态: {'✅ 已绑定' if user.get('api_key') else '❌ 未绑定'}\n"
        status_text += f"💾 配置状态: {'✅ 已创建' if config_manager.config_exists(user_id) else '❌ 未创建'}\n"

        # 显示 API 端口
        if status_info.get('status') == 'running':
            api_port = status_info.get('api_port', 'N/A')
            status_text += f"🔌 API端口: {api_port}\n"

        status_text += "\n🤖 服务状态\n\n"
    else:
        status_text = f"👤 User Information\n\n"
        status_text += f"📝 Username: {user['name']}\n"
        status_text += f"🔑 API Status: {'✅ Bound' if user.get('api_key') else '❌ Not Bound'}\n"
        status_text += f"💾 Config: {'✅ Created' if config_manager.config_exists(user_id) else '❌ Not Created'}\n"

        # Show API port
        if status_info.get('status') == 'running':
            api_port = status_info.get('api_port', 'N/A')
            status_text += f"🔌 API Port: {api_port}\n"

        status_text += "\n🤖 Service Status\n\n"

    status_text += format_service_status(status_info)

    await msg.edit_text(status_text)
    logger.info(f"用户 {user_id} 查看状态")


async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看日志"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 获取行数参数
    lines = 30
    if context.args and context.args[0].isdigit():
        lines = min(int(context.args[0]), 100)  # 最多100行

    msg = await update.message.reply_text("🔄 正在获取日志...")

    logs = swarm_manager.get_service_logs(user_id, lines)
    formatted_logs = format_log_output(logs, lines)

    await msg.edit_text(formatted_logs)
    logger.info(f"用户 {user_id} 查看日志")


# ========== Freqtrade REST API 命令 ==========

async def ft_profit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看利润统计（增强版 - 包含持仓盈亏）"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    user = db.get_user_by_telegram_id(user_id)
    if not user.get('api_key'):
        await update.message.reply_text("❌ 请先绑定API!\n\n使用 /bind 命令绑定")
        return

    # ⭐ 获取用户语言
    lang = menu_system.get_user_language(user_id).value

    print(f"[DEBUG] 用户 {user_id} 的语言设置: {lang}")
    logger.info(f"用户 {user_id} 的语言设置: {lang}")

    msg = await update.message.reply_text("🔄 正在获取利润数据..." if lang == 'zh' else "🔄 Loading profit data...")

    try:
        profit_success, profit_data = ft_api.profit(user_id)
        positions_success, positions_data = ft_api.status(user_id)
        trades_success, trades_data = ft_api.trades(user_id, limit=50)

        if not profit_success:
            await msg.edit_text(f"❌ 获取利润数据失败\n\n{profit_data.get('error', '未知错误')}" if lang == 'zh'
                              else f"❌ Failed to get profit data\n\n{profit_data.get('error', 'Unknown error')}")
            return

        positions = positions_data if positions_success and isinstance(positions_data, list) else None
        trades = trades_data.get('trades', []) if trades_success and isinstance(trades_data, dict) else None

        from improved_performance_formatter import format_profit_improved
        message = format_profit_improved(
            profit_data,
            trades_data=trades,
            positions_data=positions,
            lang=lang  # ⭐ 传入语言参数
        )

        await msg.edit_text(message, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查看利润统计（含持仓盈亏）")

    except Exception as e:
        logger.error(f"获取利润数据异常: {e}")
        await msg.edit_text(f"❌ 系统错误: {str(e)}")


async def ft_performance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示各币种性能（增强版 - 双语支持）"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    user = db.get_user_by_telegram_id(user_id)
    if not user.get('api_key'):
        await update.message.reply_text("❌ 请先绑定API!\n\n使用 /bind 命令绑定")
        return

    # ⭐ 获取用户语言
    lang = menu_system.get_user_language(user_id).value

    msg = await update.message.reply_text("🔄 正在查询性能数据..." if lang == 'zh' else "🔄 Loading performance data...")

    try:
        success, data = ft_api.performance(user_id)

        if not success:
            error_msg = data.get('error', '未知错误' if lang == 'zh' else 'Unknown error')
            await msg.edit_text(f"❌ {'查询失败' if lang == 'zh' else 'Query failed'}\n\n{error_msg}")
            return

        # ⭐ 使用支持双语的格式化函数
        from improved_performance_formatter import format_performance_improved
        message = format_performance_improved(data, lang=lang)

        await msg.edit_text(message, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查询性能（语言: {lang}）")

    except Exception as e:
        logger.error(f"查询性能时发生异常: {e}")
        import traceback
        traceback.print_exc()
        await msg.edit_text(f"❌ {'查询过程中发生错误' if lang == 'zh' else 'Error occurred'}: {str(e)}")


async def ft_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看当前持仓（增强版 - 显示方向和持仓时长）"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    user = db.get_user_by_telegram_id(user_id)
    if not user.get('api_key'):
        await update.message.reply_text("❌ 请先绑定API!\n\n使用 /bind 命令绑定")
        return

    # ⭐ 获取用户语言
    lang = menu_system.get_user_language(user_id).value

    msg = await update.message.reply_text("🔄 正在获取持仓数据..." if lang == 'zh' else "🔄 Loading positions...")

    try:
        success, data = ft_api.status(user_id)

        if not success:
            await msg.edit_text(f"❌ {data.get('error', '获取失败')}")
            return

        from improved_performance_formatter import format_status_improved
        message = format_status_improved(data, lang=lang)  # ⭐ 传入语言参数

        await msg.edit_text(message, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查看持仓")

    except Exception as e:
        logger.error(f"获取持仓数据异常: {e}")
        await msg.edit_text(f"❌ 系统错误: {str(e)}")


async def ft_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看账户余额"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    user = db.get_user_by_telegram_id(user_id)
    if not user.get('api_key'):
        await update.message.reply_text("❌ 请先绑定API!\n\n使用 /bind 命令绑定")
        return

    # ⭐ 获取用户语言
    lang = menu_system.get_user_language(user_id).value

    msg = await update.message.reply_text("🔄 正在获取余额数据..." if lang == 'zh' else "🔄 Loading balance...")

    try:
        success, data = ft_api.balance(user_id)

        if not success:
            await msg.edit_text(f"❌ {data.get('error', '获取失败')}")
            return

        # 可选：同时获取利润数据
        profit_success, profit_data = ft_api.profit(user_id)
        profit_info = profit_data if profit_success else None

        from improved_performance_formatter import format_balance_improved
        message = format_balance_improved(data, profit_info, lang=lang)  # ⭐ 传入语言参数

        await msg.edit_text(message, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查看余额")

    except Exception as e:
        logger.error(f"获取余额数据异常: {e}")
        await msg.edit_text(f"❌ 系统错误: {str(e)}")


async def ft_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示每日统计"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    # 获取天数参数
    days = 7
    if context.args and context.args[0].isdigit():
        days = min(int(context.args[0]), 30)

    msg = await update.message.reply_text(f"🔄 正在查询最近{days}天数据...")

    success, data = ft_api.daily(user_id, days)

    if success:
        report = ft_api.format_daily(data, days)
        await msg.edit_text(report, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查询每日统计")
    else:
        await msg.edit_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


async def ft_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示交易计数"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    msg = await update.message.reply_text("🔄 正在查询交易计数...")

    success, data = ft_api.count(user_id)

    if success:
        lang = menu_system.get_user_language(user_id).value
        if lang == "zh":
            report = "📊 <b>交易计数</b>\n\n"
            report += f"当前持仓: {data.get('current', 0)}\n"
            report += f"最大持仓: {data.get('max', 0)}\n"
            report += f"总交易数: {data.get('total', 0)}\n"
        else:
            report = "📊 <b>Trade Count</b>\n\n"
            report += f"Current: {data.get('current', 0)}\n"
            report += f"Max: {data.get('max', 0)}\n"
            report += f"Total: {data.get('total', 0)}\n"

        await msg.edit_text(report, parse_mode='HTML')
    else:
        await msg.edit_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


async def ft_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示版本信息"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    success, data = ft_api.version(user_id)

    if success:
        version = data.get('version', 'N/A')
        await update.message.reply_text(f"ℹ️ Freqtrade 版本: {version}")
    else:
        await update.message.reply_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


# ========== 交易控制命令 ==========

async def ft_start_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过API启动交易"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    msg = await update.message.reply_text("🔄 正在启动交易...")

    success, data = ft_api.start(user_id)

    if success:
        await msg.edit_text("✅ 交易已启动")
        logger.info(f"用户 {user_id} 通过API启动交易")
    else:
        await msg.edit_text(f"❌ 启动失败\n\n{data.get('error', '未知错误')}")


async def ft_stop_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过API停止交易"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    msg = await update.message.reply_text("🔄 正在停止交易...")

    success, data = ft_api.stop(user_id)

    if success:
        await msg.edit_text("✅ 交易已停止")
        logger.info(f"用户 {user_id} 通过API停止交易")
    else:
        await msg.edit_text(f"❌ 停止失败\n\n{data.get('error', '未知错误')}")


# ========== Docker 命令(备用) ==========

async def ft_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """执行自定义 Freqtrade 命令(通过 Docker)"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册!")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ 请提供命令!\n\n"
            "使用格式:\n"
            "/ft <命令>\n\n"
            "示例:\n"
            "/ft show-config\n"
            "/ft list-strategies\n"
            "/ft --version"
        )
        return

    command = " ".join(context.args)
    msg = await update.message.reply_text(f"🔄 执行命令: {command}")

    success, output = ft_commander.custom_command(user_id, command)

    if success:
        result = f"✅ 执行成功\n\n<pre>{output[:3800]}</pre>"
    else:
        result = f"❌ 执行失败\n\n<pre>{output[:3800]}</pre>"

    await msg.edit_text(result, parse_mode='HTML')


# ========== 配置管理 ==========

async def config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """配置管理菜单"""
    keyboard = [
        #[InlineKeyboardButton("📄 查看配置", callback_data="config_view")],
        #[InlineKeyboardButton("✏️ 修改持仓数", callback_data="config_positions")],
        #[InlineKeyboardButton("💰 修改资金", callback_data="config_stake")],
        [InlineKeyboardButton("🔙 返回", callback_data="config_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ 配置管理\n\n请选择操作:",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "config_view":
        if not db.user_exists(user_id):
            await query.message.reply_text("❌ 请先注册!")
            return

        config_display = config_manager.get_config_display(user_id)
        await query.message.reply_text(
            f"📄 当前配置:\n\n```json\n{config_display[:3500]}\n```",
            parse_mode='Markdown'
        )

    elif query.data == "config_back":
        await query.message.reply_text("已返回主菜单")

    logger.info(f"用户 {user_id} 点击按钮: {query.data}")


# ========== ⭐ 消息处理器 (动态路由) ==========

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理所有文本消息(仅处理按钮点击,不处理命令)"""
    user_id = update.message.from_user.id
    text = update.message.text

    # ⭐ 忽略所有命令(以 / 开头的消息)
    if text.startswith('/'):
        return

    # 匹配按钮动作
    action = menu_system.match_button_action(user_id, text)

    if not action:
        # ⭐ 如果不是按钮文本，记录日志便于调试
        logger.debug(f"未识别的消息: {text} (用户 {user_id})")
        return

    # 路由到对应的处理函数
    handlers = {
        "register": register,
        "bind_api": bind,
        "my_payment": my_payment_address,
        "my_subscription": subscription_info,
        "use_invite": use_invite_code,
        "my_invite_menu": view_invite_menu,
        "my_invite_stats": my_invite_stats,
        "my_invitees": my_invitees_list,
        "share_invite_code": share_invite_code,
        "start_trading": start_bot,
        "stop_trading": stop_bot,
        "view_status": view_status_menu,
        "profit": ft_profit,
        "performance": ft_performance,
        "positions": ft_status,
        "balance": ft_balance,
        "config_manage": view_config_menu,
        "help": help_command,
        "switch_lang": switch_language,
        "back_to_main": back_to_main,
        "modify_leverage": lambda u, c: u.message.reply_text("🚧 功能开发中..."),
        "view_pairs": view_pairs
    }

    handler = handlers.get(action)
    if handler:
        try:
            await handler(update, context)
        except Exception as e:
            logger.error(f"处理按钮 {action} 时出错: {e}")
            import traceback
            traceback.print_exc()
    else:
        logger.warning(f"未找到处理器: {action}")


# ========== 错误处理 ==========

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """改进的错误处理器 - 提供更详细的错误信息"""
    import traceback

    # 记录完整错误信息到日志
    error_traceback = ''.join(traceback.format_exception(
        type(context.error), context.error, context.error.__traceback__
    ))
    logger.error(f"更新 {update} 引发错误:\n{error_traceback}")

    if update and update.effective_message:
        user_id = update.effective_user.id if update.effective_user else None

        # 尝试恢复用户菜单
        try:
            if user_id and db.user_exists(user_id):
                user_status, has_invite_code = get_user_status(user_id)
                keyboard = menu_system.get_main_keyboard(
                    user_id, user_status, has_invite_code
                )

                await update.effective_message.reply_text(
                    "❌ 发生错误，请稍后重试\n\n"
                    "如果问题持续，请联系管理员",
                    reply_markup=keyboard
                )
            else:
                await update.effective_message.reply_text(
                    "❌ 发生错误，请稍后重试或联系管理员"
                )
        except Exception as e:
            logger.error(f"错误处理器本身出错: {e}")
            # 最后的兜底
            try:
                await update.effective_message.reply_text(
                    "❌ 发生错误，请使用 /start 重新开始"
                )
            except:
                pass


# ========== 主函数 ==========

def main():
    """主函数"""
    # 创建数据库
    db.create_tables()

    # 检查Bot Token
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("请先设置Bot Token!")
        print("❌ 错误:请先在代码中设置Bot Token或设置环境变量 BOT_TOKEN")
        return

    # 创建应用
    try:
        app = Application.builder().token(BOT_TOKEN).build()

        # ========== 基础命令 ==========
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("register", register))
        app.add_handler(CommandHandler("bind", bind))
        app.add_handler(CommandHandler("lang", switch_language))  # ⭐ 新增
        app.add_handler(CommandHandler("help", help_command))

        # ========== 交易控制命令 ==========
        app.add_handler(CommandHandler("startbot", start_bot))
        app.add_handler(CommandHandler("stopbot", stop_bot))
        #app.add_handler(CommandHandler("restart", restart_bot))
        #app.add_handler(CommandHandler("status", status))
        #app.add_handler(CommandHandler("logs", view_logs))
        app.add_handler(CommandHandler("config", config_menu))

        # ========== ⭐ 支付和订阅命令 ==========
        app.add_handler(CommandHandler("my_address", my_payment_address))
        app.add_handler(CommandHandler("recharge", my_payment_address))  # 别名
        #app.add_handler(CommandHandler("my_subscription", subscription_info))
        #app.add_handler(CommandHandler("plans", view_plans))
        #app.add_handler(CommandHandler("recharge_history", recharge_records))

        # ========== Freqtrade REST API 命令 ==========
        app.add_handler(CommandHandler("profit", ft_profit))
        app.add_handler(CommandHandler("performance", ft_performance))
        app.add_handler(CommandHandler("positions", ft_status))
        app.add_handler(CommandHandler("balance", ft_balance))
        #app.add_handler(CommandHandler("daily", ft_daily))
        #app.add_handler(CommandHandler("count", ft_count))
        app.add_handler(CommandHandler("version", ft_version))

        # ========== 交易控制命令 ==========
        app.add_handler(CommandHandler("ft_start", ft_start_trading))
        app.add_handler(CommandHandler("ft_stop", ft_stop_trading))

        # ========== Docker 命令(备用) ==========
        app.add_handler(CommandHandler("ft", ft_command))

        # ========== ⭐ 按钮回调和消息处理 ==========
        app.add_handler(CallbackQueryHandler(button_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # ⭐ 添加邀请码命令
        app.add_handler(CommandHandler("invite", use_invite_code))
        app.add_handler(CommandHandler("my_invite", my_invite_info))
        app.add_handler(CommandHandler("my_invitees", my_invitees_list))  # 新增

        # ... 其他代码 ...

        logger.info("✅ 邀请码系统已加载")


        # ========== 错误处理 ==========
        app.add_error_handler(error_handler)

        # 启动机器人
        logger.info("=" * 50)
        logger.info("🤖 Freqtrade Telegram Bot 启动中...")
        logger.info("=" * 50)
        logger.info("✅ REST API 客户端已加载")
        logger.info("✅ Docker 命令执行器已加载")
        logger.info("✅ 多语言菜单系统已加载")  # ⭐ 新增
        logger.info("=" * 50)
        register_flexible_subscription_commands(app,menu_system)

        app.run_polling(allowed_updates=Update.ALL_TYPES,drop_pending_updates=True)

    except Exception as e:
        logging.error(f"Error occurred: {e}")


if __name__ == "__main__":
    main()