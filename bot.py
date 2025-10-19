"""
bot.py - Telegram机器人主程序
处理所有用户交互和命令
集成 Freqtrade REST API
"""

import logging
import os
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
from trade_notifier import TradeNotifier  # ⭐ 新增
from payment_system import PaymentSystem

# 初始化支付系统（在其他管理器初始化后）
payment_system = PaymentSystem()


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

# 初始化 Freqtrade 客户端
ft_api = FreqtradeAPIClient()
ft_commander = FreqtradeCommander()

# Bot配置
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ 错误:请设置环境变量 BOT_TOKEN")
    print("   方法1: export BOT_TOKEN='your_token'")
    print("   方法2: 在 .env 文件中设置")
    exit(1)


# ========== 💰 支付和订阅管理命令 ==========

async def my_payment_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看我的充值地址和订阅状态"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    # 获取用户地址
    address = payment_system.get_user_address(user_id)

    # 获取订阅状态
    status = payment_system.get_subscription_status(user_id)

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
        message += (
            f"❌ <b>订阅状态:</b> {status['message']}\n\n"
        )

    message += (
        f"<b>💡 充值说明:</b>\n"
        f"1. 复制上方地址\n"
        f"2. 在钱包中发送 USDT (TRC20网络)\n"
        f"3. 系统将自动检测并确认充值\n"
        f"4. 余额到账后自动订阅套餐\n\n"
        f"⚠️ 请务必使用 <b>TRC20</b> 网络！\n"
        f"⚠️ 充值通常在 1-5 分钟内到账\n\n"
        f"💎 使用 /plans 查看套餐详情"
    )

    await update.message.reply_text(message, parse_mode='HTML')


async def view_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看订阅套餐"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    plans = db.get_all_plans()

    message = "💎 <b>订阅套餐</b>\n"
    message += "=" * 30 + "\n\n"

    for plan in plans:
        message += f"<b>📦 {plan['plan_name']}</b>\n"
        message += f"  💰 最大资金: {plan['max_capital']:,.0f} USDT\n"
        message += f"  💵 价格: {plan['price_30days']:.0f} USDT / 30天\n"
        message += f"  📝 {plan['description']}\n\n"

    message += (
        f"<b>💡 说明:</b>\n"
        f"• 充值后自动订阅最适合的套餐\n"
        f"• 套餐决定最大可操作资金额度\n"
        f"• 订阅有效期30天\n\n"
        f"使用 /my_address 查看充值地址"
    )

    await update.message.reply_text(message, parse_mode='HTML')


async def recharge_records(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看充值记录"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    records = db.get_user_recharge_records(user_id, limit=10)

    if not records:
        await update.message.reply_text("📜 暂无充值记录")
        return

    message = "📜 <b>充值记录</b>\n"
    message += "=" * 30 + "\n\n"

    for record in records:
        status_emoji = {
            'pending': '⏳',
            'verified': '✅',
            'rejected': '❌'
        }.get(record['status'], '❓')

        status_text = {
            'pending': '待确认',
            'verified': '已确认',
            'rejected': '已拒绝'
        }.get(record['status'], '未知')

        message += f"{status_emoji} <b>记录 #{record['id']}</b>\n"
        message += f"  金额: {record['amount']:.2f} USDT\n"
        message += f"  状态: {status_text}\n"

        # 格式化时间
        created_time = record['created_at']
        if 'T' in created_time:
            created_time = created_time.replace('T', ' ').split('.')[0]
        message += f"  时间: {created_time}\n"

        if record['tx_hash']:
            tx_short = f"{record['tx_hash'][:8]}...{record['tx_hash'][-6:]}"
            message += f"  哈希: <code>{tx_short}</code>\n"

        message += "\n"

    await update.message.reply_text(message, parse_mode='HTML')


async def subscription_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看订阅详情"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    subscription = db.get_user_subscription(user_id)
    balance = db.get_user_balance(user_id)

    message = "📋 <b>订阅详情</b>\n"
    message += "=" * 30 + "\n\n"

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

    await update.message.reply_text(message, parse_mode='HTML')



# ========== 基础命令 ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """启动命令 - 显示主菜单"""
    keyboard = [
        [KeyboardButton("📝 注册111"), KeyboardButton("🔗 绑定API")],
        [KeyboardButton("💰 我的充值"), KeyboardButton("📋 我的订阅")],  # ⭐ 新增
        [KeyboardButton("▶️ 启动交易"), KeyboardButton("⏸️ 停止交易")],
        [KeyboardButton("📊 查看状态"), KeyboardButton("📋 查看日志")],
        [KeyboardButton("💰 利润统计"), KeyboardButton("📈 币种性能")],
        [KeyboardButton("📍 持仓查询"), KeyboardButton("💵 余额查询")],
        [KeyboardButton("⚙️ 配置管理"), KeyboardButton("❓ 帮助")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    welcome_text = create_service_menu_text()
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    logger.info(f"用户 {update.message.from_user.id} 启动机器人")


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """注册用户"""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.username or update.message.from_user.first_name

    # 速率限制
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⚠️ 操作过于频繁，请稍后再试")
        return

    if db.user_exists(user_id):
        await update.message.reply_text(f"ℹ️ 用户 {user_name} 已经注册过了！")
        logger.info(f"用户 {user_id} 尝试重复注册")
    else:
        new_user_id = db.insert_user(user_id, user_name)
        if new_user_id:
            # 创建用户目录
            config_manager.create_user_directory(user_id)

            await update.message.reply_text(
                f"✅ 欢迎，{user_name}！\n\n"
                f"📝 注册成功\n"
                f"🆔 系统ID: {new_user_id}\n\n"
                f"下一步：\n"
                f"请使用 /bind 命令绑定您的币安API密钥\n\n"
                f"格式：\n"
                f"/bind <API_KEY> <SECRET>"
            )
            logger.info(f"用户 {user_id} ({user_name}) 注册成功")
        else:
            await update.message.reply_text("❌ 注册失败，请稍后再试")
            logger.error(f"用户 {user_id} 注册失败")


async def bind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """绑定API密钥"""
    user_id = update.message.from_user.id

    # 检查用户是否注册
    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先使用 📝注册 按钮进行注册！")
        return

    # 速率限制
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⚠️ 操作过于频繁，请稍后再试")
        return

    # 检查参数
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ 使用格式错误！\n\n"
            "正确格式：\n"
            "/bind <API_KEY> <SECRET>\n\n"
            "示例：\n"
            "/bind your_api_key your_secret_key"
        )
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

    # 创建用户配置文件（启用API）
    if config_manager.create_user_config(user_id, api_key, secret):
        api_port = config_manager.get_user_api_port(user_id)
        await msg.edit_text(
            "✅ API绑定成功！\n\n"
            "🎉 配置文件已创建\n"
            "🌐 REST API 已启用\n"
            f"🔌 API端口: {api_port}\n"
            "✨ 您现在可以启动交易机器人了\n\n"
            "使用 ▶️启动交易 按钮开始交易"
        )
        logger.info(f"用户 {user_id} API绑定成功，API端口: {api_port}")
    else:
        await msg.edit_text(
            "⚠️ API已保存，但配置文件创建失败\n\n"
            "请联系管理员检查系统配置"
        )
        logger.error(f"用户 {user_id} 配置文件创建失败")


async def start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """启动交易机器人（添加订阅检查）"""
    user_id = update.message.from_user.id

    # 检查用户是否注册
    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    # 速率限制
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⚠️ 操作过于频繁，请稍后再试")
        return

    # ⭐ 检查订阅状态
    status = payment_system.get_subscription_status(user_id)

    if not status['active']:
        address = status['address']
        balance = status['balance']

        await update.message.reply_text(
            f"❌ 无法启动交易\n\n"
            f"原因: {status['message']}\n\n"
            f"💰 当前余额: {balance:.2f} USDT\n"
            f"📍 您的充值地址:\n"
            f"<code>{address}</code>\n\n"
            f"💡 请充值 USDT 到上方地址\n"
            f"💡 系统将自动订阅并激活服务\n\n"
            f"使用 /my_address 查看充值详情",
            parse_mode='HTML'
        )
        return

    # 检查是否绑定API
    user = db.get_user_by_telegram_id(user_id)
    if not user.get('api_key') or not user.get('security'):
        await update.message.reply_text("❌ 请先绑定API密钥！\n\n使用 /bind 命令绑定")
        return

    # 检查配置文件
    if not config_manager.config_exists(user_id):
        await update.message.reply_text("❌ 配置文件不存在，请重新绑定API")
        return

    msg = await update.message.reply_text("🔄 正在启动交易机器人...")

    # 创建服务
    success, message = swarm_manager.create_service(user_id)

    if success:
        await msg.edit_text(
            f"✅ 启动成功！\n\n"
            f"{message}\n\n"
            f"💰 最大操作资金: {status['max_capital']:,.0f} USDT\n"
            f"📅 订阅到期: {status['end_date']}\n"
            f"⏳ 剩余: {status['days_left']} 天\n\n"
            f"🤖 交易机器人已启动\n"
            f"📊 使用 /profit 查看利润\n"
            f"📈 使用 /performance 查看性能"
        )
        logger.info(f"用户 {user_id} 启动服务成功")
    else:
        await msg.edit_text(f"❌ 启动失败\n\n{message}")
        logger.error(f"用户 {user_id} 启动服务失败: {message}")


async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """停止交易机器人"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    # 速率限制
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("⚠️ 操作过于频繁，请稍后再试")
        return

    msg = await update.message.reply_text("🔄 正在停止交易机器人...")

    success, message = swarm_manager.stop_service(user_id)

    if success:
        await msg.edit_text(f"✅ 已停止\n\n{message}")
        logger.info(f"用户 {user_id} 停止服务")
    else:
        await msg.edit_text(f"⚠️ {message}")
        logger.warning(f"用户 {user_id} 停止服务: {message}")


async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """重启交易机器人"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
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
        await update.message.reply_text("❌ 请先注册！")
        return

    msg = await update.message.reply_text("🔄 正在获取状态...")

    user = db.get_user_by_telegram_id(user_id)
    status_info = swarm_manager.get_service_status(user_id)

    status_text = f"👤 用户信息\n\n"
    status_text += f"📝 用户名: {user['name']}\n"
    status_text += f"🔑 API状态: {'✅ 已绑定' if user.get('api_key') else '❌ 未绑定'}\n"
    status_text += f"💾 配置状态: {'✅ 已创建' if config_manager.config_exists(user_id) else '❌ 未创建'}\n"

    # 显示 API 端口
    if status_info.get('status') == 'running':
        api_port = status_info.get('api_port', 'N/A')
        status_text += f"🔌 API端口: {api_port}\n"

    status_text += "\n🤖 服务状态\n\n"
    status_text += format_service_status(status_info)

    await msg.edit_text(status_text)
    logger.info(f"用户 {user_id} 查看状态")


async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看日志"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
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
    """显示利润统计"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    msg = await update.message.reply_text("🔄 正在查询利润数据...")

    success, data = ft_api.profit(user_id)

    if success:
        report = ft_api.format_profit(data)
        await msg.edit_text(report, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查询利润")
    else:
        await msg.edit_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


async def ft_performance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示各币种性能"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    msg = await update.message.reply_text("🔄 正在查询性能数据...")

    success, data = ft_api.performance(user_id)

    if success:
        report = ft_api.format_performance(data)
        await msg.edit_text(report, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查询性能")
    else:
        await msg.edit_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


async def ft_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示当前持仓"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    msg = await update.message.reply_text("🔄 正在查询持仓...")

    success, data = ft_api.status(user_id)

    if success:
        report = ft_api.format_status(data)
        await msg.edit_text(report, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查询持仓")
    else:
        await msg.edit_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


async def ft_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示账户余额"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    msg = await update.message.reply_text("🔄 正在查询余额...")

    success, data = ft_api.balance(user_id)

    if success:
        report = ft_api.format_balance(data)
        await msg.edit_text(report, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查询余额")
    else:
        await msg.edit_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


async def ft_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示每日统计"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    # 获取天数参数
    days = 7
    if context.args and context.args[0].isdigit():
        days = min(int(context.args[0]), 30)

    msg = await update.message.reply_text(f"🔄 正在查询最近{days}天数据...")

    success, data = ft_api.daily(user_id, days)

    if success:
        report = ft_api.format_daily(data)
        await msg.edit_text(report, parse_mode='HTML')
        logger.info(f"用户 {user_id} 查询每日统计")
    else:
        await msg.edit_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


async def ft_start_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """API: 启动交易"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    msg = await update.message.reply_text("🔄 正在启动交易...")

    success, data = ft_api.start_trading(user_id)

    if success:
        await msg.edit_text(f"✅ 交易已启动\n\n{data.get('status', '')}")
        logger.info(f"用户 {user_id} 通过API启动交易")
    else:
        await msg.edit_text(f"❌ 启动失败\n\n{data.get('error', '未知错误')}")


async def ft_stop_trading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """API: 停止交易"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    msg = await update.message.reply_text("🔄 正在停止交易...")

    success, data = ft_api.stop_trading(user_id)

    if success:
        await msg.edit_text(f"✅ 交易已停止\n\n{data.get('status', '')}")
        logger.info(f"用户 {user_id} 通过API停止交易")
    else:
        await msg.edit_text(f"❌ 停止失败\n\n{data.get('error', '未知错误')}")


async def ft_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示 Freqtrade 版本"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    success, data = ft_api.version(user_id)

    if success:
        version = data.get('version', 'N/A')
        await update.message.reply_text(f"ℹ️ Freqtrade 版本: {version}")
    else:
        await update.message.reply_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


async def ft_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """显示交易计数"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    msg = await update.message.reply_text("🔄 正在查询交易计数...")

    success, data = ft_api.count(user_id)

    if success:
        report = "📊 <b>交易计数</b>\n\n"
        report += f"当前持仓: {data.get('current', 0)}\n"
        report += f"最大持仓: {data.get('max', 0)}\n"
        report += f"总交易数: {data.get('total', 0)}\n"

        await msg.edit_text(report, parse_mode='HTML')
    else:
        await msg.edit_text(f"❌ 查询失败\n\n{data.get('error', '未知错误')}")


# ========== Docker 命令执行（备用）==========

async def ft_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """执行自定义 Freqtrade 命令（通过 Docker）"""
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        await update.message.reply_text("❌ 请先注册！")
        return

    if not context.args:
        await update.message.reply_text(
            "❌ 请提供命令！\n\n"
            "使用格式：\n"
            "/ft <命令>\n\n"
            "示例：\n"
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
        [InlineKeyboardButton("📄 查看配置", callback_data="config_view")],
        [InlineKeyboardButton("✏️ 修改持仓数", callback_data="config_positions")],
        [InlineKeyboardButton("💰 修改资金", callback_data="config_stake")],
        [InlineKeyboardButton("🔙 返回", callback_data="config_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ 配置管理\n\n请选择操作：",
        reply_markup=reply_markup
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "config_view":
        if not db.user_exists(user_id):
            await query.message.reply_text("❌ 请先注册！")
            return

        config_display = config_manager.get_config_display(user_id)
        await query.message.reply_text(
            f"📄 当前配置：\n\n```json\n{config_display[:3500]}\n```",
            parse_mode='Markdown'
        )

    elif query.data == "config_back":
        await query.message.reply_text("已返回主菜单")

    logger.info(f"用户 {user_id} 点击按钮: {query.data}")


# ========== ⭐ 支付和订阅命令（新增）==========


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理文本消息"""
    text = update.message.text

    button_map = {
        "📝 注册": register,
        "🔗 绑定API": lambda u, c: u.message.reply_text(
            "请使用以下格式绑定API：\n\n"
            "/bind <API_KEY> <SECRET>"
        ),
        "💰 我的充值": my_payment_address,  # ⭐ 新增
        "📋 我的订阅": subscription_info,    # ⭐ 新增
        "▶️ 启动交易": start_bot,
        "⏸️ 停止交易": stop_bot,
        "📊 查看状态": status,
        "📋 查看日志": view_logs,
        "💰 利润统计": ft_profit,
        "📈 币种性能": ft_performance,
        "📍 持仓查询": ft_status,
        "💵 余额查询": ft_balance,
        "⚙️ 配置管理": config_menu,
      #  "❓ 帮助": help_command
    }

    handler = button_map.get(text)
    if handler:
        await handler(update, context)



async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """错误处理"""
    logger.error(f"更新 {update} 引发错误: {context.error}")

    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ 发生错误，请稍后重试或联系管理员"
        )


def main():
    """主函数"""
    # 创建数据库
    db.create_tables()

    # 检查Bot Token
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("请先设置Bot Token！")
        print("❌ 错误：请先在代码中设置Bot Token或设置环境变量 BOT_TOKEN")
        return

    # 创建应用
    app = Application.builder().token(BOT_TOKEN).build()

    # ========== 基础命令 ==========
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("bind", bind))
    app.add_handler(CommandHandler("startbot", start_bot))
    app.add_handler(CommandHandler("stopbot", stop_bot))
    app.add_handler(CommandHandler("restart", restart_bot))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("logs", view_logs))
    app.add_handler(CommandHandler("config", config_menu))
    #app.add_handler(CommandHandler("help", help_command))

    # ========== ⭐ 支付和订阅命令（新增）==========
    app.add_handler(CommandHandler("my_address", my_payment_address))
    app.add_handler(CommandHandler("recharge", my_payment_address))  # 别名
    app.add_handler(CommandHandler("my_subscription", subscription_info))
    app.add_handler(CommandHandler("plans", view_plans))
    app.add_handler(CommandHandler("recharge_history", recharge_records))

    # ========== Freqtrade REST API 命令 ==========
    app.add_handler(CommandHandler("profit", ft_profit))
    app.add_handler(CommandHandler("performance", ft_performance))
    app.add_handler(CommandHandler("positions", ft_status))
    app.add_handler(CommandHandler("balance", ft_balance))
    app.add_handler(CommandHandler("daily", ft_daily))
    app.add_handler(CommandHandler("count", ft_count))
    app.add_handler(CommandHandler("version", ft_version))

    # ========== 交易控制命令 ==========
    app.add_handler(CommandHandler("ft_start", ft_start_trading))
    app.add_handler(CommandHandler("ft_stop", ft_stop_trading))

    # ========== Docker 命令（备用）==========
    app.add_handler(CommandHandler("ft", ft_command))

    # ========== 按钮回调和消息处理 ==========
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ========== 错误处理 ==========
    app.add_error_handler(error_handler)

    # 启动机器人
    logger.info("=" * 50)
    logger.info("🤖 Freqtrade Telegram Bot 启动中...")
    logger.info("=" * 50)
    logger.info("✅ REST API 客户端已加载")
    logger.info("✅ Docker 命令执行器已加载")
    logger.info("=" * 50)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()