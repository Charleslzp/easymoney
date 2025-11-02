"""
database.py - 数据库管理模块（完整版）
负责用户数据的增删改查操作
包含：用户管理、订阅管理、充值管理、地址管理、邀请系统
"""

import sqlite3
import os
from uuid import uuid4
from typing import Optional, List, Tuple, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

DATABASE_FILE = "user_data/users.db"


class Database:
    """数据库管理类"""

    def __init__(self, db_file: str = DATABASE_FILE):
        self.db_file = db_file
        self._ensure_directory()

    def _ensure_directory(self):
        """确保数据库目录存在"""
        os.makedirs(os.path.dirname(self.db_file), exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(self.db_file)

    def create_tables(self):
        """创建数据库表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. 用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT '停止',
                security TEXT,
                api_key TEXT,
                service_id TEXT,
                service_name TEXT,
                balance REAL DEFAULT 0,
                inviter_user_id INTEGER,
                invite_code TEXT,
                has_used_invite INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 2. 用户配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                config_key TEXT NOT NULL,
                config_value TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, config_key)
            );
        ''')

        # 3. 操作日志表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        ''')

        # 4. 用户充值地址表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_payment_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                address TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        ''')

        # 5. 订阅套餐表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscription_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_name TEXT NOT NULL,
                max_capital REAL NOT NULL,
                price_30days REAL NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 6. 用户订阅表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                max_capital REAL NOT NULL,
                start_date TIMESTAMP NOT NULL,
                end_date TIMESTAMP NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (plan_id) REFERENCES subscription_plans(id)
            );
        ''')

        # 7. 充值记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS recharge_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                tx_hash TEXT,
                payment_address TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                plan_id INTEGER,
                verified_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        ''')

        # 8. 用户余额表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_balance (
                user_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        ''')

        # 9. 邀请码表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                owner_user_id INTEGER,
                max_uses INTEGER DEFAULT 0,
                current_uses INTEGER DEFAULT 0,
                discount_percent REAL DEFAULT 10.0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
            );
        ''')

        # 10. 邀请码使用记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invite_code_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                discount_amount REAL NOT NULL,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (code_id) REFERENCES invite_codes(id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(code_id, user_id)
            );
        ''')

        # 11. 用户邀请关系表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_user_id INTEGER NOT NULL,
                invitee_user_id INTEGER NOT NULL,
                invite_code TEXT NOT NULL,
                inviter_reward_total REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (inviter_user_id) REFERENCES users(user_id),
                FOREIGN KEY (invitee_user_id) REFERENCES users(user_id),
                UNIQUE(invitee_user_id)
            );
        ''')

        # 12. 邀请奖励记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS invite_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_user_id INTEGER NOT NULL,
                invitee_user_id INTEGER NOT NULL,
                recharge_amount REAL NOT NULL,
                reward_amount REAL NOT NULL,
                recharge_record_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (inviter_user_id) REFERENCES users(user_id),
                FOREIGN KEY (invitee_user_id) REFERENCES users(user_id),
                FOREIGN KEY (recharge_record_id) REFERENCES recharge_records(id)
            );
        ''')

        conn.commit()

        # 初始化默认数据
        self._init_subscription_plans(cursor)
        self._init_default_invite_codes(cursor)
        conn.commit()

        conn.close()
        logger.info("数据库表创建完成")

    def _init_subscription_plans(self, cursor):
        """初始化订阅套餐"""
        cursor.execute('SELECT COUNT(*) FROM subscription_plans')
        if cursor.fetchone()[0] > 0:
            return

        plans = [
            ('体验版', 1000, 10, '最大操作资金: 1,000 USDT'),
            ('基础版', 5000, 50, '最大操作资金: 5,000 USDT'),
            ('标准版', 10000, 100, '最大操作资金: 10,000 USDT'),
            ('专业版', 50000, 300, '最大操作资金: 50,000 USDT'),
            ('旗舰版', 100000, 500, '最大操作资金: 100,000 USDT'),
        ]

        cursor.executemany('''
            INSERT INTO subscription_plans (plan_name, max_capital, price_30days, description)
            VALUES (?, ?, ?, ?)
        ''', plans)

        logger.info("订阅套餐初始化完成")

    def _init_default_invite_codes(self, cursor):
        """初始化默认邀请码"""
        cursor.execute('SELECT COUNT(*) FROM invite_codes')
        if cursor.fetchone()[0] > 0:
            return

        default_codes = [
            ('WELCOME10', None, 10, 10.0),
            ('FIRST100', None, 100, 10.0),
            ('VIP20', None, 0, 20.0),
        ]

        for code, owner, max_uses, discount in default_codes:
            cursor.execute('''
                INSERT OR IGNORE INTO invite_codes 
                (code, owner_user_id, max_uses, discount_percent, is_active)
                VALUES (?, ?, ?, ?, 1)
            ''', (code, owner, max_uses, discount))

        logger.info("默认邀请码初始化完成")

    # ========== 用户管理方法 ==========

    def insert_user(self, user_id: int, name: str) -> Optional[str]:
        """插入新用户"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT id FROM users WHERE user_id = ?', (user_id,))
            if cursor.fetchone():
                conn.close()
                return None

            new_user_id = str(uuid4())
            cursor.execute('''
                INSERT INTO users (id, name, user_id, status)
                VALUES (?, ?, ?, 'stopped')
            ''', (new_user_id, name, user_id))

            conn.commit()
            conn.close()

            self.log_operation(user_id, "register", f"用户注册: {name}")
            return new_user_id

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"插入用户失败: {e}")
            return None

    def user_exists(self, user_id: int) -> bool:
        """检查用户是否存在"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM users WHERE user_id = ? LIMIT 1', (user_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def get_user_by_telegram_id(self, user_id: int) -> Optional[Dict]:
        """通过 Telegram ID 获取用户信息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, name, user_id, status, api_key, security, 
                   service_id, service_name, balance, created_at
            FROM users
            WHERE user_id = ?
        ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'id': row[0],
            'name': row[1],
            'user_id': row[2],
            'status': row[3],
            'api_key': row[4],
            'security': row[5],
            'service_id': row[6],
            'service_name': row[7],
            'balance': row[8],
            'created_at': row[9]
        }

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """通过user_id获取用户信息"""
        return self.get_user_by_telegram_id(user_id)

    def update_user_api(self, user_id: int, security: str, api_key: str):
        """更新用户的API密钥"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET security = ?, api_key = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (security, api_key, user_id))
        conn.commit()
        conn.close()
        self.log_operation(user_id, "bind_api", "绑定API密钥")

    def update_user_status(self, user_id: int, status: str):
        """更新用户状态"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (status, user_id))
        conn.commit()
        conn.close()

    def update_service_info(self, user_id: int, service_id: str, service_name: str):
        """更新用户的服务信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET service_id = ?, service_name = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (service_id, service_name, user_id))
        conn.commit()
        conn.close()

    def clear_service_info(self, user_id: int):
        """清除用户的服务信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET service_id = NULL, service_name = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()

    def get_running_users(self) -> List[Dict]:
        """获取所有运行中的用户"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, service_id, service_name 
            FROM users 
            WHERE status = '运行中' AND service_id IS NOT NULL
        """)
        rows = cursor.fetchall()
        conn.close()

        users = []
        for row in rows:
            users.append({
                'user_id': row[0],
                'service_id': row[1],
                'service_name': row[2]
            })
        return users

    def log_operation(self, user_id: int, operation: str, details: str = ""):
        """记录操作日志"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO operation_logs (user_id, operation, details)
            VALUES (?, ?, ?)
        ''', (user_id, operation, details))
        conn.commit()
        conn.close()

    # ========== 充值地址管理 ==========

    def save_user_payment_address(self, user_id: int, address: str) -> bool:
        """保存用户的充值地址"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT OR REPLACE INTO user_payment_addresses (user_id, address)
                VALUES (?, ?)
            ''', (user_id, address))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"保存充值地址失败: {e}")
            return False

    def get_user_payment_address(self, user_id: int) -> Optional[str]:
        """获取用户的充值地址"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT address FROM user_payment_addresses WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def get_all_payment_addresses(self) -> Dict[int, str]:
        """获取所有用户的充值地址映射"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, address FROM user_payment_addresses')
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}

    # ========== 订阅套餐管理 ==========

    def get_all_plans(self) -> List[Dict]:
        """获取所有订阅套餐"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, plan_name, max_capital, price_30days, description
            FROM subscription_plans
            ORDER BY max_capital ASC
        ''')
        rows = cursor.fetchall()
        conn.close()

        plans = []
        for row in rows:
            plans.append({
                'id': row[0],
                'plan_name': row[1],
                'max_capital': row[2],
                'price_30days': row[3],
                'description': row[4]
            })
        return plans

    def get_plan_by_capital(self, capital: float) -> Optional[Dict]:
        """根据资金额度获取合适的套餐"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, plan_name, max_capital, price_30days, description
            FROM subscription_plans
            WHERE max_capital >= ?
            ORDER BY max_capital ASC
            LIMIT 1
        ''', (capital,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'plan_name': row[1],
                'max_capital': row[2],
                'price_30days': row[3],
                'description': row[4]
            }
        return None

    # ========== 用户余额管理 ==========

    def get_user_balance(self, user_id: int) -> float:
        """获取用户余额"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0.0

    def add_balance(self, user_id: int, amount: float) -> bool:
        """
        增加用户余额

        Args:
            user_id: 用户ID
            amount: 增加的金额

        Returns:
            是否成功
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if row:
                new_balance = row[0] + amount
                cursor.execute('''
                    UPDATE user_balance 
                    SET balance = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (new_balance, user_id))
            else:
                cursor.execute('''
                    INSERT INTO user_balance (user_id, balance)
                    VALUES (?, ?)
                ''', (user_id, amount))

            conn.commit()
            conn.close()

            logger.info(f"用户 {user_id} 余额增加: +{amount} USDT")
            return True

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"增加余额失败: {e}")
            return False

    def update_user_balance(self, user_id: int, amount: float, operation: str = "adjust"):
        """更新用户余额（保留原方法兼容性）"""
        return self.add_balance(user_id, amount)

    # ========== 充值记录管理 ==========

    def create_recharge_record(self, user_id: int, amount: float,
                              tx_hash: str = None, payment_address: str = None) -> Optional[int]:
        """创建充值记录"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO recharge_records (user_id, amount, tx_hash, payment_address, status)
                VALUES (?, ?, ?, ?, 'pending')
            ''', (user_id, amount, tx_hash, payment_address))

            record_id = cursor.lastrowid
            conn.commit()
            conn.close()

            logger.info(f"创建充值记录: 用户={user_id}, 金额={amount}")
            return record_id

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"创建充值记录失败: {e}")
            return None

    def verify_recharge(self, user_id: int, amount: float) -> bool:
        """验证并处理充值"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
        balance_row = cursor.fetchone()

        if balance_row:
            new_balance = balance_row[0] + amount
            cursor.execute('''
                UPDATE user_balance 
                SET balance = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (new_balance, user_id))
        else:
            cursor.execute('''
                INSERT INTO user_balance (user_id, balance)
                VALUES (?, ?)
            ''', (user_id, amount))

        conn.commit()
        conn.close()

        self.log_operation(user_id, "verify_recharge", f"充值成功: {amount} USDT")
        return True

    def get_user_recharge_records(self, user_id: int, limit: int = 20) -> List[Dict]:
        """获取用户充值记录"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, amount, tx_hash, status, created_at, verified_at
            FROM recharge_records
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))

        rows = cursor.fetchall()
        conn.close()

        records = []
        for row in rows:
            records.append({
                'id': row[0],
                'amount': row[1],
                'tx_hash': row[2],
                'status': row[3],
                'created_at': row[4],
                'verified_at': row[5]
            })
        return records

    # ========== 订阅管理 ==========

    def create_subscription(self, user_id: int, plan_id: int, days: int = 30) -> bool:
        """创建订阅"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT max_capital, price_30days FROM subscription_plans WHERE id = ?', (plan_id,))
        plan_row = cursor.fetchone()

        if not plan_row:
            conn.close()
            return False

        max_capital, price = plan_row
        total_price = price * (days / 30)

        cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
        balance_row = cursor.fetchone()

        if not balance_row or balance_row[0] < total_price:
            conn.close()
            return False

        new_balance = balance_row[0] - total_price
        cursor.execute('''
            UPDATE user_balance 
            SET balance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (new_balance, user_id))

        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)

        cursor.execute('''
            INSERT INTO user_subscriptions 
            (user_id, plan_id, max_capital, start_date, end_date, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        ''', (user_id, plan_id, max_capital, start_date, end_date))

        conn.commit()
        conn.close()

        self.log_operation(user_id, "create_subscription",
                          f"订阅套餐: plan_id={plan_id}, days={days}")
        return True

    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """获取用户当前订阅"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                us.id, 
                us.plan_id, 
                us.max_capital, 
                us.start_date, 
                us.end_date, 
                us.status,
                sp.plan_name
            FROM user_subscriptions us
            JOIN subscription_plans sp ON us.plan_id = sp.id
            WHERE us.user_id = ? AND us.status = 'active'
            ORDER BY us.end_date DESC
            LIMIT 1
        ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'id': row[0],
            'plan_id': row[1],
            'max_capital': row[2],
            'start_date': row[3],
            'end_date': row[4],
            'status': row[5],
            'plan_name': row[6]
        }

    def check_subscription_status(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """检查订阅状态"""
        subscription = self.get_user_subscription(user_id)

        if not subscription:
            return False, "未订阅"

        end_date = datetime.fromisoformat(subscription['end_date'])

        if datetime.now() > end_date:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE user_subscriptions 
                SET status = 'expired'
                WHERE id = ?
            ''', (subscription['id'],))
            conn.commit()
            conn.close()
            return False, "订阅已过期"

        return True, None

    # ========== 邀请码管理 ==========

    def validate_invite_code(self, code: str, user_id: int) -> tuple:
        """验证邀请码"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT has_used_invite FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()

        if row and row[0] == 1:
            conn.close()
            return False, 0, "您已经使用过邀请码了"

        cursor.execute('''
            SELECT id, discount_percent, max_uses, current_uses, is_active, expires_at
            FROM invite_codes
            WHERE code = ?
        ''', (code.upper(),))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return False, 0, "邀请码不存在"

        code_id, discount, max_uses, current_uses, is_active, expires_at = row

        if not is_active:
            return False, 0, "邀请码已失效"

        if expires_at:
            expire_time = datetime.fromisoformat(expires_at)
            if datetime.now() > expire_time:
                return False, 0, "邀请码已过期"

        if max_uses > 0 and current_uses >= max_uses:
            return False, 0, "邀请码已达到使用上限"

        return True, discount, ""

    def apply_invite_code(self, user_id: int, code: str) -> tuple:
        """应用邀请码"""
        is_valid, discount, error_msg = self.validate_invite_code(code, user_id)

        if not is_valid:
            return False, 0, error_msg, None

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT id, owner_user_id 
                FROM invite_codes 
                WHERE code = ?
            ''', (code.upper(),))

            code_row = cursor.fetchone()
            code_id, inviter_user_id = code_row

            cursor.execute('''
                UPDATE users 
                SET invite_code = ?, 
                    has_used_invite = 1,
                    inviter_user_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (code.upper(), inviter_user_id, user_id))

            cursor.execute('''
                UPDATE invite_codes 
                SET current_uses = current_uses + 1
                WHERE id = ?
            ''', (code_id,))

            if inviter_user_id:
                cursor.execute('''
                    INSERT INTO user_invitations 
                    (inviter_user_id, invitee_user_id, invite_code)
                    VALUES (?, ?, ?)
                ''', (inviter_user_id, user_id, code.upper()))

            user_invite_code = self._generate_user_invite_code(cursor, user_id)

            conn.commit()
            conn.close()

            self.log_operation(user_id, "use_invite_code",
                             f"使用邀请码: {code}, 折扣: {discount}%, 生成邀请码: {user_invite_code}")

            return True, discount, "邀请码应用成功!", user_invite_code

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"应用邀请码失败: {e}")
            return False, 0, "应用邀请码失败", None

    def _generate_user_invite_code(self, cursor, user_id: int) -> str:
        """为用户生成专属邀请码"""
        import random
        import string

        cursor.execute('''
            SELECT code FROM invite_codes 
            WHERE owner_user_id = ?
        ''', (user_id,))

        existing = cursor.fetchone()
        if existing:
            return existing[0]

        max_attempts = 10
        for _ in range(max_attempts):
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            code = f"USER{user_id}{random_part}"

            cursor.execute('SELECT 1 FROM invite_codes WHERE code = ?', (code,))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO invite_codes 
                    (code, owner_user_id, max_uses, discount_percent, is_active)
                    VALUES (?, ?, 0, 10.0, 1)
                ''', (code, user_id))

                logger.info(f"为用户 {user_id} 生成邀请码: {code}")
                return code

        code = f"USER{user_id}"
        cursor.execute('''
            INSERT OR IGNORE INTO invite_codes 
            (code, owner_user_id, max_uses, discount_percent, is_active)
            VALUES (?, ?, 0, 10.0, 1)
        ''', (code, user_id))

        return code

    def get_user_invite_code(self, user_id: int) -> Optional[str]:
        """获取用户的专属邀请码"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT code FROM invite_codes 
            WHERE owner_user_id = ?
        ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        return row[0] if row else None

    def get_user_invite_discount(self, user_id: int) -> float:
        """获取用户的邀请码折扣百分比"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT ic.discount_percent
            FROM users u
            JOIN invite_codes ic ON u.invite_code = ic.code
            WHERE u.user_id = ? AND u.has_used_invite = 1 AND ic.is_active = 1
        ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        return row[0] if row else 0.0

    def get_user_invitees(self, user_id: int, limit: int = 100) -> List[Dict]:
        """获取用户邀请的用户列表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                u.user_id,
                u.name,
                ui.created_at,
                COALESCE(SUM(ir.reward_amount), 0) as reward_contributed
            FROM user_invitations ui
            JOIN users u ON ui.invitee_user_id = u.user_id
            LEFT JOIN invite_rewards ir ON ir.invitee_user_id = u.user_id 
                AND ir.inviter_user_id = ?
            WHERE ui.inviter_user_id = ?
            GROUP BY u.user_id, u.name, ui.created_at
            ORDER BY ui.created_at DESC
            LIMIT ?
        ''', (user_id, user_id, limit))

        rows = cursor.fetchall()
        conn.close()

        invitees = []
        for row in rows:
            invitees.append({
                'invitee_user_id': row[0],
                'invitee_name': row[1],
                'created_at': row[2],
                'reward_contributed': row[3]
            })

        return invitees

    def create_invite_code(self, code: str, discount_percent: float = 10.0,
                          max_uses: int = 0, owner_user_id: int = None,
                          expires_at: str = None) -> tuple:
        """创建新的邀请码"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO invite_codes 
                (code, owner_user_id, max_uses, discount_percent, expires_at, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (code.upper(), owner_user_id, max_uses, discount_percent, expires_at))

            conn.commit()
            conn.close()

            logger.info(f"创建邀请码: {code}, 折扣: {discount_percent}%")
            return True, f"邀请码 {code} 创建成功"

        except sqlite3.IntegrityError:
            conn.close()
            return False, "邀请码已存在"
        except Exception as e:
            conn.close()
            logger.error(f"创建邀请码失败: {e}")
            return False, "创建邀请码失败"

    def get_all_invite_codes(self) -> List[Dict]:
        """获取所有邀请码列表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT code, discount_percent, max_uses, current_uses, is_active, created_at
            FROM invite_codes
            ORDER BY created_at DESC
        ''')

        rows = cursor.fetchall()
        conn.close()

        codes = []
        for row in rows:
            codes.append({
                'code': row[0],
                'discount_percent': row[1],
                'max_uses': row[2],
                'current_uses': row[3],
                'is_active': bool(row[4]),
                'created_at': row[5]
            })

        return codes

    # ========== 🆕 邀请系统新方法 ==========

    def get_user_inviter(self, user_id: int) -> Optional[int]:
        """获取用户的邀请人ID"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT inviter_user_id 
            FROM users 
            WHERE user_id = ?
        ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        return row[0] if row and row[0] else None

    def record_invite_reward(
        self,
        inviter_user_id: int,
        invitee_user_id: int,
        recharge_amount: float,
        reward_amount: float,
        recharge_record_id: int = None
    ) -> bool:
        """记录邀请奖励"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO invite_rewards 
                (inviter_user_id, invitee_user_id, recharge_amount, 
                 reward_amount, recharge_record_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (inviter_user_id, invitee_user_id, recharge_amount,
                  reward_amount, recharge_record_id))

            conn.commit()
            conn.close()

            logger.info(
                f"记录邀请奖励: 邀请人={inviter_user_id}, "
                f"被邀请人={invitee_user_id}, 奖励={reward_amount} USDT"
            )

            return True

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"记录邀请奖励失败: {e}")
            return False

    def get_invite_leaderboard(self, limit: int = 10) -> List[Dict]:
        """获取邀请排行榜"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                u.user_id,
                u.name as user_name,
                COUNT(DISTINCT ui.invitee_user_id) as invite_count,
                COALESCE(SUM(ir.reward_amount), 0) as total_rewards
            FROM users u
            LEFT JOIN user_invitations ui ON u.user_id = ui.inviter_user_id
            LEFT JOIN invite_rewards ir ON u.user_id = ir.inviter_user_id
            GROUP BY u.user_id
            HAVING invite_count > 0
            ORDER BY invite_count DESC, total_rewards DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            result.append({
                'user_id': row[0],
                'user_name': row[1],
                'invite_count': row[2],
                'total_rewards': row[3]
            })

        return result

    def get_user_invite_rewards(self, user_id: int) -> List[Dict]:
        """获取用户的邀请奖励记录"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                ir.invitee_user_id,
                u.name as invitee_name,
                ir.recharge_amount,
                ir.reward_amount,
                ir.created_at
            FROM invite_rewards ir
            JOIN users u ON ir.invitee_user_id = u.user_id
            WHERE ir.inviter_user_id = ?
            ORDER BY ir.created_at DESC
        ''', (user_id,))

        rows = cursor.fetchall()
        conn.close()

        result = []
        for row in rows:
            result.append({
                'invitee_user_id': row[0],
                'invitee_name': row[1],
                'recharge_amount': row[2],
                'reward_amount': row[3],
                'created_at': row[4]
            })

        return result

    def record_user_invitation(
        self,
        inviter_user_id: int,
        invitee_user_id: int,
        invite_code: str
    ) -> bool:
        """记录用户邀请关系"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT 1 FROM user_invitations 
                WHERE inviter_user_id = ? AND invitee_user_id = ?
            ''', (inviter_user_id, invitee_user_id))

            if cursor.fetchone():
                conn.close()
                return True

            cursor.execute('''
                INSERT INTO user_invitations 
                (inviter_user_id, invitee_user_id, invite_code)
                VALUES (?, ?, ?)
            ''', (inviter_user_id, invitee_user_id, invite_code.upper()))

            conn.commit()
            conn.close()

            logger.info(f"记录邀请关系: {inviter_user_id} -> {invitee_user_id}")
            return True

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"记录邀请关系失败: {e}")
            return False

    def record_user_invitation(
        self,
        inviter_user_id: int,
        invitee_user_id: int,
        invite_code: str
    ) -> bool:
        """记录用户邀请关系"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                SELECT 1 FROM user_invitations 
                WHERE inviter_user_id = ? AND invitee_user_id = ?
            ''', (inviter_user_id, invitee_user_id))

            if cursor.fetchone():
                conn.close()
                return True

            cursor.execute('''
                INSERT INTO user_invitations 
                (inviter_user_id, invitee_user_id, invite_code)
                VALUES (?, ?, ?)
            ''', (inviter_user_id, invitee_user_id, invite_code.upper()))

            conn.commit()
            conn.close()

            logger.info(f"记录邀请关系: {inviter_user_id} -> {invitee_user_id}")
            return True

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"记录邀请关系失败: {e}")
            return False

    def get_invite_stats(self, user_id: int) -> Dict:
        """
        获取用户的邀请统计（用于显示）

        Returns:
            {
                'my_code': '我的邀请码',
                'invitee_count': 邀请人数,
                'total_reward': 累计奖励,
                'inviter_info': 我的邀请人信息
            }
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. 获取我的邀请码
        cursor.execute('''
            SELECT code FROM invite_codes 
            WHERE owner_user_id = ? AND is_active = 1
        ''', (user_id,))

        my_code_row = cursor.fetchone()
        my_code = my_code_row[0] if my_code_row else None

        # 2. 统计我邀请的人数
        cursor.execute('''
            SELECT COUNT(*) FROM user_invitations 
            WHERE inviter_user_id = ?
        ''', (user_id,))

        invitee_count = cursor.fetchone()[0]

        # 3. 统计累计奖励
        cursor.execute('''
            SELECT SUM(reward_amount) FROM invite_rewards 
            WHERE inviter_user_id = ?
        ''', (user_id,))

        total_reward = cursor.fetchone()[0] or 0

        # 4. 获取我的邀请人信息
        cursor.execute('''
            SELECT u.name, ui.invite_code, ui.inviter_reward_total, ui.created_at
            FROM user_invitations ui
            JOIN users u ON ui.inviter_user_id = u.user_id
            WHERE ui.invitee_user_id = ?
        ''', (user_id,))

        inviter_row = cursor.fetchone()
        inviter_info = None

        if inviter_row:
            inviter_info = {
                'name': inviter_row[0],
                'code': inviter_row[1],
                'contributed_reward': inviter_row[2],
                'invited_at': inviter_row[3]
            }

        conn.close()

        return {
            'my_code': my_code,
            'invitee_count': invitee_count,
            'total_reward': total_reward,
            'inviter_info': inviter_info
        }

    def get_my_invitees(self, user_id: int, limit: int = 50) -> List[Dict]:
        """
        获取我邀请的用户列表

        Args:
            user_id: 邀请人ID
            limit: 返回数量限制

        Returns:
            [{
                'invitee_user_id': 用户ID,
                'invitee_name': 用户名,
                'created_at': 邀请时间,
                'reward_contributed': 贡献的奖励金额
            }]
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                u.user_id,
                u.name,
                ui.created_at,
                COALESCE(SUM(ir.reward_amount), 0) as reward_contributed
            FROM user_invitations ui
            JOIN users u ON ui.invitee_user_id = u.user_id
            LEFT JOIN invite_rewards ir ON ir.invitee_user_id = u.user_id 
                AND ir.inviter_user_id = ?
            WHERE ui.inviter_user_id = ?
            GROUP BY u.user_id, u.name, ui.created_at
            ORDER BY ui.created_at DESC
            LIMIT ?
        ''', (user_id, user_id, limit))

        rows = cursor.fetchall()
        conn.close()

        invitees = []
        for row in rows:
            invitees.append({
                'invitee_user_id': row[0],
                'invitee_name': row[1],
                'created_at': row[2],
                'reward_contributed': row[3]
            })

        return invitees

    def get_user_address(self, user_id: int) -> Optional[str]:
        """获取用户充值地址（别名方法）"""
        return self.get_user_payment_address(user_id)

    def is_subscription_valid(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """检查订阅是否有效（返回元组以保持兼容性）"""
        return self.check_subscription_status(user_id)


# ========== 便捷函数（保持向后兼容）==========

def create_db():
    """创建数据库"""
    db = Database()
    db.create_tables()

def insert_user(user_id: int, name: str) -> Optional[str]:
    db = Database()
    return db.insert_user(user_id, name)

def user_exists(user_id: int) -> bool:
    db = Database()
    return db.user_exists(user_id)

def update_user_api(user_id: int, security: str, api_key: str):
    db = Database()
    db.update_user_api(user_id, security, api_key)

def update_user_status(user_id: int, status: str):
    db = Database()
    db.update_user_status(user_id, status)

def get_user_by_telegram_id(user_id: int) -> Optional[Dict]:
    db = Database()
    return db.get_user_by_telegram_id(user_id)


# ========== 测试代码 ==========

if __name__ == "__main__":
    print("=" * 50)
    print("测试数据库模块")
    print("=" * 50)

    # 创建数据库
    db = Database()
    db.create_tables()

    print("\n✅ 数据库表创建成功")

    # 测试新方法
    print("\n测试新增的邀请系统方法:")

    # 1. 测试获取邀请人
    print("\n1. 测试 get_user_inviter()")
    inviter = db.get_user_inviter(123456)
    print(f"   结果: {inviter}")

    # 2. 测试排行榜
    print("\n2. 测试 get_invite_leaderboard()")
    leaderboard = db.get_invite_leaderboard(5)
    print(f"   结果: {leaderboard}")

    # 3. 测试增加余额
    print("\n3. 测试 add_balance()")
    success = db.add_balance(123456, 100.0)
    print(f"   结果: {success}")

    # 4. 测试获取用户信息
    print("\n4. 测试 get_user_by_id()")
    user_info = db.get_user_by_id(123456)
    print(f"   结果: {user_info}")

    # 5. 测试邀请奖励记录
    print("\n5. 测试 get_user_invite_rewards()")
    rewards = db.get_user_invite_rewards(123456)
    print(f"   结果: {rewards}")

    print("\n" + "=" * 50)
    print("所有测试完成!")
    print("=" * 50)