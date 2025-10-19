"""
database.py - 数据库管理模块
负责用户数据的增删改查操作
包含：用户管理、订阅管理、充值管理、地址管理
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

        # 4. ⭐ 用户充值地址表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_payment_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                address TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        ''')

        # 5. ⭐ 订阅套餐表
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

        # 6. ⭐ 用户订阅表
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

        # 7. ⭐ 充值记录表
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

        # 8. ⭐ 用户余额表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_balance (
                user_id INTEGER PRIMARY KEY,
                balance REAL NOT NULL DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        ''')

        conn.commit()

        # 初始化订阅套餐
        self._init_subscription_plans(cursor)
        conn.commit()

        conn.close()
        print("[INFO] 数据库表创建完成")

    def _init_subscription_plans(self, cursor):
        """初始化订阅套餐"""
        cursor.execute('SELECT COUNT(*) FROM subscription_plans')
        if cursor.fetchone()[0] > 0:
            return  # 已有套餐，不重复初始化

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

        print("[INFO] 订阅套餐初始化完成")

    # ========== 用户管理方法 ==========

    def insert_user(self, user_id: int, name: str) -> Optional[str]:
        """插入新用户"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT id FROM users WHERE user_id = ?', (user_id,))
            if cursor.fetchone():
                return None

            new_user_id = str(uuid4())
            cursor.execute('''
                INSERT INTO users (id, name, user_id, status)
                VALUES (?, ?, ?, ?);
            ''', (new_user_id, name, user_id, '停止'))

            # 初始化余额
            cursor.execute('''
                INSERT INTO user_balance (user_id, balance)
                VALUES (?, 0)
            ''', (user_id,))

            conn.commit()
            self.log_operation(user_id, "register", f"用户 {name} 注册成功")
            return new_user_id
        finally:
            conn.close()

    def get_user_by_telegram_id(self, user_id: int) -> Optional[Dict]:
        """通过Telegram ID获取用户信息"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'name': row[1],
                'user_id': row[2],
                'status': row[3],
                'security': row[4],
                'api_key': row[5],
                'service_id': row[6],
                'service_name': row[7],
                'created_at': row[8],
                'updated_at': row[9]
            }
        return None

    def get_all_users(self) -> List[Dict]:
        """获取所有用户"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users')
        rows = cursor.fetchall()
        conn.close()

        users = []
        for row in rows:
            users.append({
                'id': row[0],
                'name': row[1],
                'user_id': row[2],
                'status': row[3],
                'service_name': row[7]
            })
        return users

    def user_exists(self, user_id: int) -> bool:
        """检查用户是否存在"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

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

    def get_user_logs(self, user_id: int, limit: int = 50) -> List[Dict]:
        """获取用户操作日志"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT operation, details, timestamp 
            FROM operation_logs 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, limit))
        rows = cursor.fetchall()
        conn.close()

        logs = []
        for row in rows:
            logs.append({
                'operation': row[0],
                'details': row[1],
                'timestamp': row[2]
            })
        return logs

    # ========== ⭐ 充值地址管理 ==========

    def save_user_address(self, user_id: int, address: str) -> bool:
        """保存用户充值地址"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO user_payment_addresses (user_id, address)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET address = excluded.address
            ''', (user_id, address))

            conn.commit()
            conn.close()
            self.log_operation(user_id, "generate_address", f"生成充值地址: {address}")
            return True
        except Exception as e:
            conn.close()
            logger.error(f"[ERROR] 保存地址失败: {e}")
            return False

    def get_user_address(self, user_id: int) -> Optional[str]:
        """获取用户充值地址"""
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

    # ========== ⭐ 订阅套餐管理 ==========

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

    # ========== ⭐ 用户余额管理 ==========

    def get_user_balance(self, user_id: int) -> float:
        """获取用户余额"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0.0

    def update_user_balance(self, user_id: int, amount: float, operation: str = "adjust"):
        """更新用户余额"""
        conn = self._get_connection()
        cursor = conn.cursor()

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
        self.log_operation(user_id, operation, f"余额变动: {amount:+.2f} USDT")

    # ========== ⭐ 充值记录管理 ==========

    def create_recharge_record(self, user_id: int, amount: float, tx_hash: str = None,
                               payment_address: str = None) -> int:
        """创建充值记录"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO recharge_records 
            (user_id, amount, tx_hash, payment_address, status)
            VALUES (?, ?, ?, ?, 'pending')
        ''', (user_id, amount, tx_hash, payment_address))

        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.log_operation(user_id, "create_recharge", f"创建充值记录: {amount} USDT")
        return record_id

    def verify_recharge(self, record_id: int, plan_id: int = None) -> bool:
        """验证充值记录"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT user_id, amount, status FROM recharge_records WHERE id = ?', (record_id,))
        row = cursor.fetchone()

        if not row or row[2] != 'pending':
            conn.close()
            return False

        user_id, amount, _ = row

        # 更新充值记录状态
        cursor.execute('''
            UPDATE recharge_records 
            SET status = 'verified', plan_id = ?, verified_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (plan_id, record_id))

        # 更新用户余额
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

    # ========== ⭐ 订阅管理 ==========

    def create_subscription(self, user_id: int, plan_id: int, days: int = 30) -> bool:
        """创建订阅"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 获取套餐信息
        cursor.execute('SELECT max_capital, price_30days FROM subscription_plans WHERE id = ?', (plan_id,))
        plan_row = cursor.fetchone()

        if not plan_row:
            conn.close()
            return False

        max_capital, price = plan_row
        total_price = price * (days / 30)

        # 检查余额
        cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
        balance_row = cursor.fetchone()

        if not balance_row or balance_row[0] < total_price:
            conn.close()
            return False

        # 扣除余额
        new_balance = balance_row[0] - total_price
        cursor.execute('''
            UPDATE user_balance 
            SET balance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (new_balance, user_id))

        # 创建订阅
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)

        cursor.execute('''
            INSERT INTO user_subscriptions 
            (user_id, plan_id, max_capital, start_date, end_date, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        ''', (user_id, plan_id, max_capital, start_date, end_date))

        conn.commit()
        conn.close()

        self.log_operation(user_id, "subscribe", f"订阅套餐: {max_capital} USDT, {days}天")
        return True

    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """获取用户当前订阅"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT s.id, s.plan_id, s.max_capital, s.start_date, s.end_date, 
                   s.status, p.plan_name, p.price_30days
            FROM user_subscriptions s
            JOIN subscription_plans p ON s.plan_id = p.id
            WHERE s.user_id = ? AND s.status = 'active'
            ORDER BY s.end_date DESC
            LIMIT 1
        ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'plan_id': row[1],
                'max_capital': row[2],
                'start_date': row[3],
                'end_date': row[4],
                'status': row[5],
                'plan_name': row[6],
                'price_30days': row[7]
            }
        return None

    def is_subscription_valid(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """检查订阅是否有效"""
        subscription = self.get_user_subscription(user_id)

        if not subscription:
            return False, "未订阅"

        end_date = datetime.fromisoformat(subscription['end_date'])

        if datetime.now() > end_date:
            # 订阅已过期，更新状态
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


# 便捷函数（保持向后兼容）
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