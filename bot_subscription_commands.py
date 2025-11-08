"""
bot_subscription_commands.py - 优化后的订阅命令处理（支持中英双语）

新增功能：
1. 查看所有套餐及费率
2. 自定义订阅金额
3. 显示实时计算的可用额度
4. 中英双语支持
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import Database
from menu_system import MenuSystem

db = Database()
menu_system = None


def set_menu_system(ms):
    """设置 menu_system 实例"""
    global menu_system
    menu_system = ms



async def view_plans_flexible(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    查看订阅套餐（灵活版 - 双语）
    显示每个档位的费率和计算规则
    """
    user_id = update.message.from_user.id

    if not db.user_exists(user_id):
        lang = menu_system.get_user_language(user_id).value
        error_msg = "❌ 请先注册！" if lang == "zh" else "❌ Please register first!"
        await update.message.reply_text(error_msg)
        return

    plans = db.get_all_plans()
    balance = db.get_user_balance(user_id)
    lang = menu_system.get_user_language(user_id).value

    if lang == "zh":
        message = "💎 <b>灵活订阅套餐</b>\n" + "=" * 50 + "\n\n"
        message += f"💰 <b>当前余额:</b> {balance:.2f} USDT\n\n"
        message += "<b>📊 套餐档位说明:</b>\n\n"

        for plan in plans:
            rate = plan['monthly_rate']
            min_pay = plan['min_payment']
            standard_cap = plan['standard_capital']

            message += f"<b>【{plan['plan_name']}】</b>\n"
            message += f"├─ 📈 月费率: <b>{rate}%</b>\n"
            message += f"├─ 💵 最低订阅: <b>{min_pay} USDT/月</b>\n"
            message += f"├─ 💼 标准额度: <b>{standard_cap:,} USDT</b>\n"
            message += f"└─ 📝 说明: {plan['description']}\n\n"

        message += "=" * 50 + "\n"
        message += "<b>💡 灵活订阅说明:</b>\n\n"
        message += "✨ <b>您可以自由选择订阅金额！</b>\n\n"
        message += "<b>计算公式:</b>\n"
        message += "可用额度 = 订阅金额 ÷ 费率\n\n"
        message += "<b>举例说明:</b>\n"
        message += "• 进阶档(0.8%)支付 600 USDT\n"
        message += "  → 可用额度 = 600 ÷ 0.008 = 75,000 USDT\n\n"
        message += "• 旗舰档(0.5%)支付 3000 USDT\n"
        message += "  → 可用额度 = 3000 ÷ 0.005 = 600,000 USDT\n\n"
        message += "=" * 50 + "\n"
        message += "<b>📝 订阅方式:</b>\n"
        message += "使用命令: <code>/subscribe [金额]</code>\n"
        message += "例如: <code>/subscribe 600</code>\n\n"
        message += "💡 或使用 /my_address 充值后自动订阅"
    else:
        message = "💎 <b>Flexible Subscription Plans</b>\n" + "=" * 50 + "\n\n"
        message += f"💰 <b>Current Balance:</b> {balance:.2f} USDT\n\n"
        message += "<b>📊 Plan Tiers:</b>\n\n"

        for plan in plans:
            rate = plan['monthly_rate']
            min_pay = plan['min_payment']
            standard_cap = plan['standard_capital']

            message += f"<b>【{plan['plan_name']}】</b>\n"
            message += f"├─ 📈 Monthly Rate: <b>{rate}%</b>\n"
            message += f"├─ 💵 Min Payment: <b>{min_pay} USDT/month</b>\n"
            message += f"├─ 💼 Standard Capital: <b>{standard_cap:,} USDT</b>\n"
            message += f"└─ 📝 Description: {plan['description']}\n\n"

        message += "=" * 50 + "\n"
        message += "<b>💡 Flexible Subscription:</b>\n\n"
        message += "✨ <b>Choose your subscription amount freely!</b>\n\n"
        message += "<b>Formula:</b>\n"
        message += "Available Quota = Payment Amount ÷ Rate\n\n"
        message += "<b>Examples:</b>\n"
        message += "• Advanced (0.8%) pay 600 USDT\n"
        message += "  → Quota = 600 ÷ 0.008 = 75,000 USDT\n\n"
        message += "• Flagship (0.5%) pay 3000 USDT\n"
        message += "  → Quota = 3000 ÷ 0.005 = 600,000 USDT\n\n"
        message += "=" * 50 + "\n"
        message += "<b>📝 How to Subscribe:</b>\n"
        message += "Use command: <code>/subscribe [amount]</code>\n"
        message += "Example: <code>/subscribe 600</code>\n\n"
        message += "💡 Or use /my_address to recharge and auto-subscribe"

    await update.message.reply_text(message, parse_mode='HTML')


async def subscribe_flexible(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    灵活订阅命令（双语）
    用法: /subscribe [金额]
    """
    user_id = update.message.from_user.id
    lang = menu_system.get_user_language(user_id).value

    if not db.user_exists(user_id):
        error_msg = "❌ 请先使用 /register 注册" if lang == "zh" else "❌ Please use /register first"
        await update.message.reply_text(error_msg)
        return

    # 检查参数
    if not context.args or len(context.args) == 0:
        if lang == "zh":
            await update.message.reply_text(
                "❌ 请指定订阅金额\n\n"
                "用法: <code>/subscribe [金额]</code>\n"
                "例如: <code>/subscribe 600</code>\n\n"
                "💡 使用 /plans 查看套餐详情",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "❌ Please specify subscription amount\n\n"
                "Usage: <code>/subscribe [amount]</code>\n"
                "Example: <code>/subscribe 600</code>\n\n"
                "💡 Use /plans to view plan details",
                parse_mode='HTML'
            )
        return

    try:
        payment_amount = float(context.args[0])

        if payment_amount < 100:
            error_msg = "❌ 订阅金额不能少于100 USDT" if lang == "zh" else "❌ Subscription amount cannot be less than 100 USDT"
            await update.message.reply_text(error_msg)
            return

        # 预览订阅信息
        tier_info = db.get_tier_by_payment(payment_amount)

        if not tier_info:
            if lang == "zh":
                await update.message.reply_text(
                    f"❌ 订阅金额 {payment_amount} USDT 不足最低要求\n\n"
                    "最低订阅金额为 100 USDT"
                )
            else:
                await update.message.reply_text(
                    f"❌ Subscription amount {payment_amount} USDT is below minimum requirement\n\n"
                    "Minimum subscription is 100 USDT"
                )
            return

        # 显示订阅预览
        balance = db.get_user_balance(user_id)

        if lang == "zh":
            message = "📋 <b>订阅预览</b>\n" + "=" * 40 + "\n\n"
            message += f"📦 <b>套餐档位:</b> {tier_info['plan_name']}\n"
            message += f"📈 <b>月费率:</b> {tier_info['monthly_rate']}%\n"
            message += f"💵 <b>订阅金额:</b> {payment_amount} USDT\n"
            message += f"💼 <b>可用额度:</b> {tier_info['actual_capital']:,.2f} USDT\n"
            message += f"📅 <b>订阅期限:</b> 30天\n\n"
            message += "=" * 40 + "\n"
            message += f"💰 <b>当前余额:</b> {balance:.2f} USDT\n"

            if balance < payment_amount:
                message += f"❌ <b>余额不足！</b>\n\n"
                message += f"还需要: {payment_amount - balance:.2f} USDT\n"
                message += "请使用 /my_address 充值"
                await update.message.reply_text(message, parse_mode='HTML')
                return

            message += f"✅ <b>余额充足！</b>\n\n"
            message += "确认订阅请点击下方按钮:"

            confirm_text = "✅ 确认订阅"
            cancel_text = "❌ 取消"
        else:
            message = "📋 <b>Subscription Preview</b>\n" + "=" * 40 + "\n\n"
            message += f"📦 <b>Plan Tier:</b> {tier_info['plan_name']}\n"
            message += f"📈 <b>Monthly Rate:</b> {tier_info['monthly_rate']}%\n"
            message += f"💵 <b>Payment:</b> {payment_amount} USDT\n"
            message += f"💼 <b>Available Quota:</b> {tier_info['actual_capital']:,.2f} USDT\n"
            message += f"📅 <b>Duration:</b> 30 days\n\n"
            message += "=" * 40 + "\n"
            message += f"💰 <b>Current Balance:</b> {balance:.2f} USDT\n"

            if balance < payment_amount:
                message += f"❌ <b>Insufficient Balance!</b>\n\n"
                message += f"Need: {payment_amount - balance:.2f} USDT more\n"
                message += "Use /my_address to recharge"
                await update.message.reply_text(message, parse_mode='HTML')
                return

            message += f"✅ <b>Balance Sufficient!</b>\n\n"
            message += "Click button below to confirm:"

            confirm_text = "✅ Confirm"
            cancel_text = "❌ Cancel"

        # 创建确认按钮
        keyboard = [
            [
                InlineKeyboardButton(confirm_text, callback_data=f"confirm_sub_{payment_amount}"),
                InlineKeyboardButton(cancel_text, callback_data="cancel_sub")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

    except ValueError:
        error_msg = "❌ 请输入有效的数字金额" if lang == "zh" else "❌ Please enter a valid number"
        await update.message.reply_text(error_msg)
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")


async def handle_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理订阅确认回调（双语）
    """
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    callback_data = query.data
    lang = menu_system.get_user_language(user_id).value

    if callback_data == "cancel_sub":
        cancel_msg = "❌ 已取消订阅" if lang == "zh" else "❌ Subscription cancelled"
        await query.edit_message_text(cancel_msg)
        return

    if callback_data.startswith("confirm_sub_"):
        try:
            payment_amount = float(callback_data.split("_")[2])

            # 执行订阅
            success, message = db.create_subscription_flexible(user_id, payment_amount, days=30)

            if success:
                # 获取新的订阅信息
                subscription = db.get_user_subscription(user_id)
                balance = db.get_user_balance(user_id)

                if lang == "zh":
                    result_message = "✅ <b>订阅成功！</b>\n" + "=" * 40 + "\n\n"
                    result_message += f"📦 <b>套餐:</b> {subscription['plan_name']}\n"
                    result_message += f"📈 <b>费率:</b> {subscription['monthly_rate']}%\n"
                    result_message += f"💵 <b>支付:</b> {subscription['payment_amount']} USDT\n"
                    result_message += f"💼 <b>可用额度:</b> {subscription['max_capital']:,.2f} USDT\n"
                    result_message += f"📅 <b>到期时间:</b> {subscription['end_date'][:10]}\n\n"
                    result_message += f"💰 <b>剩余余额:</b> {balance:.2f} USDT\n\n"
                    result_message += "🎉 您现在可以开始交易了！\n"
                    result_message += "使用 /startbot 启动自动交易"
                else:
                    result_message = "✅ <b>Subscription Successful!</b>\n" + "=" * 40 + "\n\n"
                    result_message += f"📦 <b>Plan:</b> {subscription['plan_name']}\n"
                    result_message += f"📈 <b>Rate:</b> {subscription['monthly_rate']}%\n"
                    result_message += f"💵 <b>Payment:</b> {subscription['payment_amount']} USDT\n"
                    result_message += f"💼 <b>Available Quota:</b> {subscription['max_capital']:,.2f} USDT\n"
                    result_message += f"📅 <b>Expires:</b> {subscription['end_date'][:10]}\n\n"
                    result_message += f"💰 <b>Remaining Balance:</b> {balance:.2f} USDT\n\n"
                    result_message += "🎉 You can now start trading!\n"
                    result_message += "Use /startbot to start auto-trading"

                await query.edit_message_text(result_message, parse_mode='HTML')
            else:
                error_msg = f"❌ 订阅失败\n\n{message}" if lang == "zh" else f"❌ Subscription failed\n\n{message}"
                await query.edit_message_text(error_msg)

        except Exception as e:
            error_msg = f"❌ 订阅失败: {str(e)}" if lang == "zh" else f"❌ Subscription failed: {str(e)}"
            await query.edit_message_text(error_msg)


async def calculate_quota(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    计算订阅额度工具（双语）
    用法: /calculate [金额]
    """
    user_id = update.message.from_user.id
    lang = menu_system.get_user_language(user_id).value

    if not context.args or len(context.args) == 0:
        if lang == "zh":
            await update.message.reply_text(
                "💡 <b>额度计算器</b>\n\n"
                "用法: <code>/calculate [金额]</code>\n"
                "例如: <code>/calculate 600</code>\n\n"
                "将显示该金额在各档位可获得的交易额度",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "💡 <b>Quota Calculator</b>\n\n"
                "Usage: <code>/calculate [amount]</code>\n"
                "Example: <code>/calculate 600</code>\n\n"
                "Shows available trading quota for each tier",
                parse_mode='HTML'
            )
        return

    try:
        payment_amount = float(context.args[0])

        if payment_amount < 100:
            error_msg = "❌ 金额不能少于100 USDT" if lang == "zh" else "❌ Amount cannot be less than 100 USDT"
            await update.message.reply_text(error_msg)
            return

        plans = db.get_all_plans()

        if lang == "zh":
            message = f"💰 <b>支付金额: {payment_amount} USDT</b>\n"
            message += "=" * 50 + "\n\n"
            message += "<b>📊 各档位可获额度:</b>\n\n"

            for plan in plans:
                rate = plan['monthly_rate']
                min_pay = plan['min_payment']

                if payment_amount >= min_pay:
                    actual_capital = db.calculate_actual_capital(rate, payment_amount)
                    status = "✅ 可订阅"
                else:
                    actual_capital = db.calculate_actual_capital(rate, min_pay)
                    status = f"❌ 最低需要 {min_pay} USDT"

                message += f"<b>{plan['plan_name']}</b> (费率{rate}%)\n"
                message += f"  └─ {status}\n"
                if payment_amount >= min_pay:
                    message += f"  └─ 可获额度: <b>{actual_capital:,.2f} USDT</b>\n\n"
                else:
                    message += f"  └─ 标准额度: {plan['standard_capital']:,} USDT\n\n"

            message += "=" * 50 + "\n"
            message += "💡 使用 <code>/subscribe [金额]</code> 进行订阅"
        else:
            message = f"💰 <b>Payment Amount: {payment_amount} USDT</b>\n"
            message += "=" * 50 + "\n\n"
            message += "<b>📊 Available Quota by Tier:</b>\n\n"

            for plan in plans:
                rate = plan['monthly_rate']
                min_pay = plan['min_payment']

                if payment_amount >= min_pay:
                    actual_capital = db.calculate_actual_capital(rate, payment_amount)
                    status = "✅ Available"
                else:
                    actual_capital = db.calculate_actual_capital(rate, min_pay)
                    status = f"❌ Min required: {min_pay} USDT"

                message += f"<b>{plan['plan_name']}</b> (Rate {rate}%)\n"
                message += f"  └─ {status}\n"
                if payment_amount >= min_pay:
                    message += f"  └─ Quota: <b>{actual_capital:,.2f} USDT</b>\n\n"
                else:
                    message += f"  └─ Standard: {plan['standard_capital']:,} USDT\n\n"

            message += "=" * 50 + "\n"
            message += "💡 Use <code>/subscribe [amount]</code> to subscribe"

        await update.message.reply_text(message, parse_mode='HTML')

    except ValueError:
        error_msg = "❌ 请输入有效的数字金额" if lang == "zh" else "❌ Please enter a valid number"
        await update.message.reply_text(error_msg)
    except Exception as e:
        await update.message.reply_text(f"❌ {str(e)}")


async def my_subscription_flexible(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    查看我的订阅（优化版 - 双语）
    """
    user_id = update.message.from_user.id
    lang = menu_system.get_user_language(user_id).value

    if not db.user_exists(user_id):
        error_msg = "❌ 请先注册！" if lang == "zh" else "❌ Please register first!"
        await update.message.reply_text(error_msg)
        return

    subscription = db.get_user_subscription(user_id)
    balance = db.get_user_balance(user_id)

    if lang == "zh":
        message = "📋 <b>我的订阅</b>\n" + "=" * 40 + "\n\n"
        message += f"💰 <b>账户余额:</b> {balance:.2f} USDT\n\n"

        if subscription:
            is_valid, _ = db.is_subscription_valid(user_id)
            status_emoji = "✅" if is_valid else "❌"

            from datetime import datetime
            end_date = datetime.fromisoformat(subscription['end_date'])
            days_left = (end_date - datetime.now()).days

            message += f"{status_emoji} <b>订阅状态:</b> {'有效' if is_valid else '已过期'}\n"
            message += f"📦 <b>套餐:</b> {subscription['plan_name']}\n"
            message += f"📈 <b>费率:</b> {subscription['monthly_rate']}%\n"
            message += f"💵 <b>支付金额:</b> {subscription['payment_amount']} USDT/月\n"
            message += f"💼 <b>可用额度:</b> {subscription['max_capital']:,.2f} USDT\n"

            start_date = subscription['start_date']
            end_date_str = subscription['end_date']
            if 'T' in start_date:
                start_date = start_date.replace('T', ' ').split('.')[0]
            if 'T' in end_date_str:
                end_date_str = end_date_str.replace('T', ' ').split('.')[0]

            message += f"📅 <b>开始时间:</b> {start_date}\n"
            message += f"📅 <b>到期时间:</b> {end_date_str}\n"

            if is_valid:
                message += f"⏳ <b>剩余天数:</b> {days_left} 天\n\n"

                if balance >= 100:
                    message += "=" * 40 + "\n"
                    message += "💡 <b>升级提示:</b>\n"
                    message += "您的余额充足，可以升级到更高档位！\n"
                    message += "使用 /calculate 计算升级后的额度\n"
                    message += "使用 /subscribe 进行升级订阅"
        else:
            message += "❌ <b>未订阅</b>\n\n"
            message += "💡 充值后可以灵活选择订阅金额\n"
            message += "使用 /plans 查看套餐详情\n"
            message += "使用 /subscribe [金额] 订阅\n"
            message += "使用 /my_address 查看充值地址"
    else:
        message = "📋 <b>My Subscription</b>\n" + "=" * 40 + "\n\n"
        message += f"💰 <b>Account Balance:</b> {balance:.2f} USDT\n\n"

        if subscription:
            is_valid, _ = db.is_subscription_valid(user_id)
            status_emoji = "✅" if is_valid else "❌"

            from datetime import datetime
            end_date = datetime.fromisoformat(subscription['end_date'])
            days_left = (end_date - datetime.now()).days

            message += f"{status_emoji} <b>Status:</b> {'Active' if is_valid else 'Expired'}\n"
            message += f"📦 <b>Plan:</b> {subscription['plan_name']}\n"
            message += f"📈 <b>Rate:</b> {subscription['monthly_rate']}%\n"
            message += f"💵 <b>Payment:</b> {subscription['payment_amount']} USDT/month\n"
            message += f"💼 <b>Available Quota:</b> {subscription['max_capital']:,.2f} USDT\n"

            start_date = subscription['start_date']
            end_date_str = subscription['end_date']
            if 'T' in start_date:
                start_date = start_date.replace('T', ' ').split('.')[0]
            if 'T' in end_date_str:
                end_date_str = end_date_str.replace('T', ' ').split('.')[0]

            message += f"📅 <b>Start Date:</b> {start_date}\n"
            message += f"📅 <b>Expires:</b> {end_date_str}\n"

            if is_valid:
                message += f"⏳ <b>Days Remaining:</b> {days_left} days\n\n"

                if balance >= 100:
                    message += "=" * 40 + "\n"
                    message += "💡 <b>Upgrade Available:</b>\n"
                    message += "Your balance is sufficient to upgrade!\n"
                    message += "Use /calculate to check upgrade quota\n"
                    message += "Use /subscribe to upgrade"
        else:
            message += "❌ <b>Not Subscribed</b>\n\n"
            message += "💡 Recharge to subscribe flexibly\n"
            message += "Use /plans to view plan details\n"
            message += "Use /subscribe [amount] to subscribe\n"
            message += "Use /my_address for recharge address"

    await update.message.reply_text(message, parse_mode='HTML')


# ========== 自动订阅逻辑（用于充值后）==========

def auto_subscribe_smart(user_id: int) -> tuple:
    """
    智能自动订阅
    根据用户余额自动选择最合适的套餐

    Returns:
        (是否成功, 消息)
    """
    balance = db.get_user_balance(user_id)

    if balance < 100:
        return False, "余额不足100 USDT，无法自动订阅"

    # 检查是否已有有效订阅
    subscription = db.get_user_subscription(user_id)
    if subscription:
        is_valid, _ = db.is_subscription_valid(user_id)
        if is_valid:
            return False, "您已有有效订阅"

    # 使用80%的余额进行订阅（保留20%作为交易或其他用途）
    available_for_subscription = balance * 0.8

    # 找到最合适的档位
    tier_info = db.get_tier_by_payment(available_for_subscription)

    if not tier_info:
        return False, "余额不足以订阅任何套餐"

    # 执行订阅
    success, message = db.create_subscription_flexible(user_id, available_for_subscription, days=30)

    return success, message


# ========== 命令注册辅助 ==========

def register_flexible_subscription_commands(application,menu_sys):
    """
    注册灵活订阅相关命令

    在bot.py的main()函数中调用:
    from bot_subscription_commands import register_flexible_subscription_commands
    register_flexible_subscription_commands(app)
    """
    from telegram.ext import CommandHandler, CallbackQueryHandler

    set_menu_system(menu_sys)

    # 订阅相关命令
    application.add_handler(CommandHandler("plans", view_plans_flexible))
    application.add_handler(CommandHandler("subscribe", subscribe_flexible))
    application.add_handler(CommandHandler("calculate", calculate_quota))
    application.add_handler(CommandHandler("my_subscription", my_subscription_flexible))

    # 回调处理
    application.add_handler(CallbackQueryHandler(handle_subscription_callback, pattern="^(confirm_sub_|cancel_sub)"))

    print("✅ 灵活订阅系统已加载（双语支持）")


if __name__ == "__main__":
    print("=" * 60)
    print("灵活订阅命令模块（双语版）")
    print("=" * 60)
    print("\n可用命令:")
    print("  /plans - 查看灵活订阅套餐 / View flexible plans")
    print("  /subscribe [金额] - 订阅指定金额的套餐 / Subscribe with amount")
    print("  /calculate [金额] - 计算不同档位的可用额度 / Calculate quota")
    print("  /my_subscription - 查看当前订阅详情 / View subscription")
    print("\n示例:")
    print("  /subscribe 600 - 订阅600 USDT的进阶档")
    print("  /calculate 1000 - 查看1000 USDT在各档位的额度")
    print("=" * 60)