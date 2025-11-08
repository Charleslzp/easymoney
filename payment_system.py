"""
payment_system.py - 独立支付系统模块
功能：
1. 为每个用户生成独立的 USDT(TRC20) 充值地址
2. 自动监控充值到账
3. 自动确认并订阅
"""

import logging
import asyncio
import requests
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from tronpy import Tron
from tronpy.keys import PrivateKey
from database import Database
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PaymentSystem:
    """支付系统 - HD钱包 + 自动监控"""

    def __init__(self, master_private_key: str = None, trongrid_api_key: str = None, network: str = 'mainnet'):
        """
        初始化支付系统

        Args:
            master_private_key: 主私钥（用于生成子地址）
            trongrid_api_key: TronGrid API Key
            network: 网络类型 ('mainnet', 'nile', 'shasta')
        """
        self.db = Database()

        # 网络配置
        self.network = network

        # TronGrid API
        self.trongrid_api_key = trongrid_api_key or os.getenv("TRONGRID_API_KEY", "")

        # 根据网络选择 API URL 和合约地址
        if network == 'nile':  # Nile 测试网
            self.trongrid_url = "https://nile.trongrid.io"
            self.usdt_contract = "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf"  # Nile测试网USDT
        elif network == 'shasta':  # Shasta 测试网
            self.trongrid_url = "https://api.shasta.trongrid.io"
            self.usdt_contract = "TG3XXyExBkPp9nzdajDZsozEu4BkaSJozs"  # Shasta测试网USDT
        else:  # 主网
            self.trongrid_url = "https://api.trongrid.io"
            self.usdt_contract = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # 主网USDT

        # 主钱包私钥
        self.master_private_key = master_private_key or os.getenv(
            "MASTER_PRIVATE_KEY",
            self._generate_master_key()
        )

        # Tron 客户端
        self.tron = Tron(network=network)

        # 监控间隔（秒）
        self.monitor_interval = 30

        logger.info(f"[INFO] 支付系统初始化完成 - 网络: {network}")

    def _generate_master_key(self) -> str:
        """生成主私钥（首次运行时）"""
        private_key = PrivateKey.random()
        key_hex = private_key.hex()

        logger.warning(f"[WARN] 生成新的主私钥: {key_hex}")
        logger.warning("[WARN] 请将此私钥保存到环境变量 MASTER_PRIVATE_KEY")
        logger.warning("[WARN] export MASTER_PRIVATE_KEY=\"{key_hex}\"")

        return key_hex

    def generate_user_address(self, user_id: int) -> str:
        """
        为用户生成独立的充值地址

        Args:
            user_id: 用户 ID

        Returns:
            TRC20 地址
        """
        # 检查数据库是否已有地址
        existing_address = self.db.get_user_address(user_id)

        if existing_address:
            return existing_address

        # 使用用户ID派生确定性地址
        derived_key = self._derive_key(user_id)
        address = derived_key.public_key.to_base58check_address()

        # 保存到数据库
        self.db.save_user_payment_address(user_id, address)

        logger.info(f"[INFO] 为用户 {user_id} 生成地址: {address}")

        return address

    def _derive_key(self, user_id: int) -> PrivateKey:
        """
        派生子密钥（确定性生成）

        Args:
            user_id: 用户 ID

        Returns:
            PrivateKey 对象
        """
        import hashlib

        master_bytes = bytes.fromhex(self.master_private_key)
        user_bytes = user_id.to_bytes(8, 'big')

        # 生成派生密钥
        derived_bytes = hashlib.sha256(master_bytes + user_bytes).digest()

        return PrivateKey(derived_bytes)

    def get_user_address(self, user_id: int) -> Optional[str]:
        """
        获取用户的充值地址

        Args:
            user_id: 用户 ID

        Returns:
            地址或 None
        """
        # 先从数据库查询
        address = self.db.get_user_address(user_id)

        if address:
            return address

        # 如果不存在，自动生成
        return self.generate_user_address(user_id)

    def check_address_balance(self, address: str) -> Tuple[float, List[Dict]]:
        """
        检查地址的 USDT 余额和交易记录

        Args:
            address: TRC20 地址

        Returns:
            (余额, 交易列表)
        """
        try:
            # 使用 TronGrid API 查询 TRC20 交易
            url = f"{self.trongrid_url}/v1/accounts/{address}/transactions/trc20"

            headers = {}
            if self.trongrid_api_key:
                headers['TRON-PRO-API-KEY'] = self.trongrid_api_key

            params = {
                'limit': 50,
                'contract_address': self.usdt_contract
            }

            print("=" * 60)
            print("🔍 调试信息：")
            print(f"URL: {url}")
            print(f"Contract: {self.usdt_contract}")
            print(f"Headers: {headers}")
            print(f"Params: {params}")
            from urllib.parse import urlencode
            full_url = f"{url}?{urlencode(params)}"
            print(f"完整URL: {full_url}")
            print("=" * 60)

            response = requests.get(url, headers=headers, params=params, timeout=10)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.json()}")

            if response.status_code != 200:
                logger.error(f"[ERROR] 查询余额失败: {response.text}")
                return 0.0, []

            data = response.json()
            logger.error(f"[ERROR] 查询余额失败: {response}")
            transactions = data.get('data', [])

            # 计算余额（接收的金额）
            balance = 0.0
            received_txs = []

            for tx in transactions:
                if tx.get('to') == address:
                    # 接收的交易
                    amount = int(tx.get('value', 0)) / 1_000_000  # USDT 6位小数
                    balance += amount

                    received_txs.append({
                        'tx_hash': tx.get('transaction_id'),
                        'from': tx.get('from'),
                        'to': tx.get('to'),
                        'amount': amount,
                        'timestamp': tx.get('block_timestamp'),
                        'confirmed': True
                    })

            return balance, received_txs

        except Exception as e:
            logger.error(f"[ERROR] 查询余额异常: {e}")
            return 0.0, []

    def monitor_user_address(self, user_id: int) -> Optional[Dict]:
        """
        监控用户地址，检查新充值

        Args:
            user_id: 用户 ID

        Returns:
            新充值信息或 None
        """
        address = self.get_user_address(user_id)

        if not address:
            return None

        # 获取交易记录
        _, transactions = self.check_address_balance(address)

        if not transactions:
            return None

        # 检查是否有未处理的充值
        for tx in transactions:
            tx_hash = tx['tx_hash']

            # 检查数据库中是否已处理此交易
            conn = self.db._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM recharge_records 
                WHERE user_id = ? AND tx_hash = ?
            ''', (user_id, tx_hash))

            if cursor.fetchone():
                conn.close()
                continue  # 已处理，跳过

            conn.close()

            # 新充值！
            return {
                'user_id': user_id,
                'address': address,
                'amount': tx['amount'],
                'tx_hash': tx_hash,
                'timestamp': tx['timestamp']
            }

        return None

    def auto_subscribe_if_possible(self, user_id: int) -> Tuple[bool, str]:
        """尝试自动订阅（支持灵活订阅）"""
        balance = self.db.get_user_balance(user_id)

        if balance < 100:
            return False, "余额不足100 USDT"

        subscription = self.db.get_user_subscription(user_id)
        if subscription:
            is_valid, _ = self.db.is_subscription_valid(user_id)
            if is_valid:
                return False, "已有有效订阅"

        try:
            # 优先使用灵活订阅
            if hasattr(self.db, 'create_subscription_flexible'):
                subscription_amount = balance * 0.8
                if subscription_amount < 100:
                    subscription_amount = balance

                success, message = self.db.create_subscription_flexible(
                    user_id, subscription_amount, days=30
                )

                if success:
                    logger.info(f"[自动订阅] ✅ {message}")
                    return True, message

            # 回退到传统方式
            plans = self.db.get_all_plans()
            for plan in sorted(plans, key=lambda p: p.get('standard_capital', p.get('max_capital', 0)), reverse=True):
                min_payment = plan.get('min_payment', plan.get('price_30days', 999999))
                if balance >= min_payment:
                    success = self.db.create_subscription(user_id, plan['id'], days=30)
                    if success:
                        return True, f"自动订阅: {plan['plan_name']}"

            return False, "余额不足"
        except Exception as e:
            logger.error(f"[自动订阅] ❌ {e}")
            return False, str(e)

    def process_new_recharge(self, recharge_info: dict) -> bool:
        """
        处理新充值 - 包含邀请码折扣和邀请奖励
        """
        try:
            user_id = recharge_info['user_id']
            original_amount = recharge_info['amount']
            tx_hash = recharge_info['tx_hash']

            # ⭐ 1. 检查用户是否有邀请码折扣
            discount_percent = self.db.get_user_invite_discount(user_id)

            # 计算实际到账金额
            if discount_percent > 0:
                bonus_amount = original_amount * (discount_percent / 100)
                final_amount = original_amount + bonus_amount

                logger.info(f"[充值] 💰 用户 {user_id} 使用邀请码优惠")
                logger.info(f"[充值] 充值: {original_amount} USDT")
                logger.info(f"[充值] 赠送: {bonus_amount:.2f} USDT ({discount_percent}%)")
                logger.info(f"[充值] 到账: {final_amount:.2f} USDT")
            else:
                bonus_amount = 0
                final_amount = original_amount

            # ⭐ 2. 创建充值记录
            record_id = self.db.create_recharge_record(
                user_id=user_id,
                amount=final_amount,  # 使用包含赠送的金额
                tx_hash=tx_hash,
                payment_address=recharge_info['address']
            )

            # ⭐ 3. 确认充值
            success = self.db.verify_recharge(record_id)

            if success:
                logger.info(f"[充值] ✅ 用户 {user_id} 充值成功: {final_amount:.2f} USDT")

                # ⭐ 4. 记录邀请码使用
                if bonus_amount > 0:
                    self.db.record_invite_code_usage(user_id, original_amount, bonus_amount)

                # ⭐ 5. 处理邀请奖励 - 给邀请人发奖励
                has_inviter, inviter_id, reward_amount = self.db.process_invite_reward(
                    invitee_user_id=user_id,
                    recharge_amount=original_amount,  # 基于原始充值金额计算
                    recharge_record_id=record_id
                )

                if has_inviter:
                    logger.info(f"[邀请奖励] ✅ 邀请人 {inviter_id} 获得 {reward_amount:.2f} USDT")

                # ⭐ 6. 尝试自动订阅
                self.auto_subscribe_if_possible(user_id)

                return True
            else:
                logger.error(f"[充值] ❌ 充值确认失败")
                return False

        except Exception as e:
            logger.error(f"[充值] ❌ 处理充值失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def monitor_all_users(self):
        """监控所有用户的充值地址"""
        logger.info("[INFO] 🔍 开始监控所有用户充值...")

        while True:
            try:
                # 从数据库获取所有地址
                addresses = self.db.get_all_payment_addresses()

                if addresses:
                    logger.info(f"[INFO] 监控 {len(addresses)} 个地址")

                for user_id, address in addresses.items():
                    # 监控此用户
                    new_recharge = self.monitor_user_address(user_id)

                    if new_recharge:
                        logger.info(f"[INFO] 检测到新充值: 用户 {user_id}, 金额 {new_recharge['amount']}")

                        # 处理充值
                        if self.process_new_recharge(new_recharge):
                            logger.info(f"[INFO] 充值处理成功: 用户 {user_id}")
                            # TODO: 这里可以发送 Telegram 通知

                # 等待下一次检查
                await asyncio.sleep(self.monitor_interval)

            except Exception as e:
                logger.error(f"[ERROR] 监控异常: {e}")
                await asyncio.sleep(self.monitor_interval)

    async def start(self):
        """启动支付系统"""
        logger.info("[INFO] 💰 支付系统启动中...")

        try:
            await self.monitor_all_users()
        except KeyboardInterrupt:
            logger.info("[INFO] 🛑 支付系统停止")
        except Exception as e:
            logger.error(f"[ERROR] 系统异常: {e}")

    # ========== 订阅管理（与支付系统集成）==========

    def auto_subscribe_if_sufficient_balance(self, user_id: int) -> Tuple[bool, str]:
        """
        如果余额足够，自动订阅合适的套餐

        Args:
            user_id: 用户 ID

        Returns:
            (是否订阅, 消息)
        """
        balance = self.db.get_user_balance(user_id)

        if balance <= 0:
            return False, "余额不足"

        # 获取当前订阅
        subscription = self.db.get_user_subscription(user_id)

        if subscription:
            # 已有订阅，检查是否需要续费
            is_valid, _ = self.db.is_subscription_valid(user_id)

            if is_valid:
                logger.info(f"[INFO] 用户 {user_id} 订阅仍然有效，无需自动订阅")
                return False, "订阅仍然有效"

        # 查找最适合的套餐（从最大的开始，找到余额够的）
        plans = self.db.get_all_plans()

        for plan in sorted(plans, key=lambda p: p['max_capital'], reverse=True):
            if balance >= plan['price_30days']:
                # 余额足够购买此套餐
                success = self.db.create_subscription(user_id, plan['id'], days=30)

                if success:
                    logger.info(f"[INFO] 用户 {user_id} 自动订阅: {plan['plan_name']}")
                    return True, f"自动订阅成功: {plan['plan_name']}"

        return False, "余额不足以购买任何套餐"

    def get_subscription_status(self, user_id: int) -> Dict:
        """
        获取用户订阅状态（用于显示）

        Args:
            user_id: 用户 ID

        Returns:
            状态信息
        """
        subscription = self.db.get_user_subscription(user_id)
        balance = self.db.get_user_balance(user_id)
        address = self.get_user_address(user_id)

        if not subscription:
            return {
                'active': False,
                'balance': balance,
                'address': address,
                'message': '未订阅'
            }

        is_valid, reason = self.db.is_subscription_valid(user_id)

        if not is_valid:
            return {
                'active': False,
                'balance': balance,
                'address': address,
                'message': reason or '订阅已过期'
            }

        end_date = datetime.fromisoformat(subscription['end_date'])
        days_left = (end_date - datetime.now()).days

        return {
            'active': True,
            'balance': balance,
            'address': address,
            'plan_name': subscription['plan_name'],
            'max_capital': subscription['max_capital'],
            'end_date': end_date.strftime('%Y-%m-%d %H:%M'),
            'days_left': days_left,
            'message': '订阅有效'
        }

    def check_subscription_for_trading(self, user_id: int) -> Tuple[bool, str]:
        """
        检查是否可以交易（用于启动服务前检查）

        Args:
            user_id: 用户 ID

        Returns:
            (是否可以交易, 原因)
        """
        is_valid, reason = self.db.is_subscription_valid(user_id)

        if not is_valid:
            return False, reason or "订阅无效"

        return True, "订阅有效"

    def get_max_capital_limit(self, user_id: int) -> float:
        """
        获取用户最大资金限制

        Args:
            user_id: 用户 ID

        Returns:
            最大资金限制（USDT）
        """
        subscription = self.db.get_user_subscription(user_id)

        if not subscription:
            return 0

        is_valid, _ = self.db.is_subscription_valid(user_id)

        if not is_valid:
            return 0

        return subscription['max_capital']


def run_payment_system(master_private_key: str = None, trongrid_api_key: str = None, network: str = 'mainnet'):
    """
    运行支付系统

    Args:
        master_private_key: 主私钥
        trongrid_api_key: TronGrid API Key
        network: 网络类型 ('mainnet', 'nile', 'shasta')
    """
    payment_system = PaymentSystem(master_private_key, trongrid_api_key, network)

    try:
        asyncio.run(payment_system.start())
    except KeyboardInterrupt:
        logger.info("[INFO] 服务已停止")


if __name__ == "__main__":
    import os

    MASTER_PRIVATE_KEY = os.getenv("MASTER_PRIVATE_KEY")
    TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY")
    NETWORK = os.getenv("TRON_NETWORK", "nile")  # 默认使用测试网

    if not MASTER_PRIVATE_KEY:
        print("=" * 60)
        print("⚠️  警告: 未设置 MASTER_PRIVATE_KEY")
        print("⚠️  将自动生成新的主私钥")
        print("⚠️  请将生成的私钥保存到环境变量")
        print("=" * 60)
        print("")

    print("=" * 60)
    print(f"💰 Freqtrade 支付系统 - {NETWORK.upper()}")
    print("=" * 60)
    print("")
    print("功能：")
    print("  ✅ 为每个用户生成独立充值地址")
    print("  ✅ 自动监控链上充值")
    print("  ✅ 自动确认并增加余额")
    print("  ✅ 自动订阅合适的套餐")
    print("")
    print(f"当前网络: {NETWORK}")
    print("监控间隔: 30秒")
    print("")
    print("按 Ctrl+C 停止")
    print("=" * 60)
    print("")

    run_payment_system(MASTER_PRIVATE_KEY, TRONGRID_API_KEY, NETWORK)
