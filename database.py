"""
database.py - 数据库管理模块（灵活订阅优化版）

优化内容：
1. 分档折扣体系：5个档位，费率从1%到0.5%递减
2. 自由订阅金额：用户可选择支付金额，系统计算对应的最大资金额度
3. 动态资金上限：max_capital = payment_amount × 100 ÷ rate

订阅档位说明：
- 入门档: 费率1.0%，最低100 USDT/月，可获10,000 USDT额度
- 进阶档: 费率0.8%，最低400 USDT/月，可获50,000 USDT额度
- 专业档: 费率0.7%，最低700 USDT/月，可获100,000 USDT额度
- 企业档: 费率0.6%，最低1,200 USDT/月，可获200,000 USDT额度
- 旗舰档: 费率0.5%，最低2,500 USDT/月，可获500,000 USDT额度

用户可以支付更多金额获得更高额度，例如：
- 进阶档支付600 USDT → 获得 600÷0.008 = 75,000 USDT额度
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

    def _init_subscription_plans(self, cursor):
        """
        初始化订阅套餐（灵活定价版）

        套餐结构：
        - plan_name: 套餐名称
        - tier_level: 档位等级 (1-5)
        - monthly_rate: 月费率 (%)
        - min_payment: 最低订阅费 (USDT/30天)
        - standard_capital: 标准资金额度 (USDT)
        - description: 描述

        计算公式：
        实际可用资金 = (用户支付金额 / 月费率) × 100
        """
        cursor.execute('SELECT COUNT(*) FROM subscription_plans')
        if cursor.fetchone()[0] > 0:
            return

        plans = [
            # (套餐名称, 档位, 月费率%, 最低费用, 标准额度, 描述)
            ('入门档', 1, 1.0, 100, 10000, '费率1.0% | 最低100 USDT/月 | 标准额度10,000 USDT'),
            ('进阶档', 2, 0.8, 400, 50000, '费率0.8% | 最低400 USDT/月 | 标准额度50,000 USDT'),
            ('专业档', 3, 0.7, 700, 100000, '费率0.7% | 最低700 USDT/月 | 标准额度100,000 USDT'),
            ('企业档', 4, 0.6, 1200, 200000, '费率0.6% | 最低1,200 USDT/月 | 标准额度200,000 USDT'),
            ('旗舰档', 5, 0.5, 2500, 500000, '费率0.5% | 最低2,500 USDT/月 | 标准额度500,000 USDT'),
        ]

        cursor.executemany('''
            INSERT INTO subscription_plans 
            (plan_name, tier_level, monthly_rate, min_payment_30days, standard_capital, description)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', plans)

        logger.info("订阅套餐初始化完成（灵活定价版）")
        logger.info("=" * 60)
        for plan in plans:
            logger.info(f"{plan[0]}: 费率{plan[2]}% | 最低{plan[3]} USDT/月 | 标准{plan[4]:,} USDT")
        logger.info("=" * 60)

    def create_tables(self):
        """创建数据库表"""
        conn = self._get_connection()
        cursor = conn.cursor()

        self._create_invite_code_usage_table(cursor)

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

        # 5. 订阅套餐表（优化版）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscription_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_name TEXT NOT NULL,
                tier_level INTEGER NOT NULL,
                monthly_rate REAL NOT NULL,
                min_payment_30days REAL NOT NULL,
                standard_capital REAL NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 6. 用户订阅表（优化版）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                tier_level INTEGER NOT NULL,
                monthly_rate REAL NOT NULL,
                payment_amount REAL NOT NULL,
                actual_capital REAL NOT NULL,
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
                discount_percent REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_user_id) REFERENCES users(user_id)
            );
        ''')

        # 10. 用户邀请关系表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_invitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_user_id INTEGER NOT NULL,
                invitee_user_id INTEGER NOT NULL UNIQUE,
                invite_code TEXT NOT NULL,
                inviter_reward_total REAL DEFAULT 0.0,  -- ⭐ 新增字段: 累计给邀请人的奖励

                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (inviter_user_id) REFERENCES users(user_id),
                FOREIGN KEY (invitee_user_id) REFERENCES users(user_id)
            );
        ''')

        # 11. 邀请奖励记录表
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

    # ========== 核心功能：计算实际可用资金 ==========

    def calculate_actual_capital(self, monthly_rate: float, payment_amount: float) -> float:
        """
        计算实际可用资金额度

        公式: actual_capital = (payment_amount / monthly_rate) × 100

        例如：
        - 进阶档费率0.8%，支付600 USDT → 600 / 0.008 = 75,000 USDT
        - 旗舰档费率0.5%，支付3000 USDT → 3000 / 0.005 = 600,000 USDT
        """
        rate_decimal = monthly_rate / 100
        actual_capital = payment_amount / rate_decimal
        return actual_capital

    def get_tier_by_payment(self, payment_amount: float) -> Optional[Dict]:
        """
        根据支付金额自动匹配最佳档位

        规则：找到支付金额>=最低费用的最高档位
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, plan_name, tier_level, monthly_rate, min_payment_30days, standard_capital
            FROM subscription_plans
            WHERE min_payment_30days <= ?
            ORDER BY tier_level DESC
            LIMIT 1
        ''', (payment_amount,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        actual_capital = self.calculate_actual_capital(row[3], payment_amount)

        return {
            'id': row[0],
            'plan_name': row[1],
            'tier_level': row[2],
            'monthly_rate': row[3],
            'min_payment': row[4],
            'standard_capital': row[5],
            'payment_amount': payment_amount,
            'actual_capital': actual_capital
        }

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

            user_uuid = str(uuid4())
            cursor.execute('''
                INSERT INTO users (id, name, user_id)
                VALUES (?, ?, ?)
            ''', (user_uuid, name, user_id))

            # 初始化用户余额
            cursor.execute('''
                INSERT INTO user_balance (user_id, balance)
                VALUES (?, 0)
            ''', (user_id,))

            conn.commit()
            conn.close()
            self.log_operation(user_id, "register", "用户注册")
            return user_uuid

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"插入用户失败: {e}")
            return None

    def get_user_node_info(self, user_id: int) -> Optional[Dict]:
        """
        获取用户服务的节点信息

        Args:
            user_id: 用户ID

        Returns:
            包含 node_ip 和 api_port 的字典
        """
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute('''
                SELECT node_ip, api_port 
                FROM users 
                WHERE user_id = ?
            ''', (user_id,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    'node_ip': row['node_ip'],
                    'api_port': row['api_port']
                }

            return None

        except Exception as e:
            print(f"[ERROR] 获取节点信息失败: {e}")
            return None

    def update_service_info(self, user_id: int, service_id: str, service_name: str,
                            node_ip: str = None, api_port: int = None):
        """
        更新用户服务信息

        Args:
            user_id: 用户ID
            service_id: Docker服务ID
            service_name: 服务名称
            node_ip: 节点IP地址
            api_port: API端口
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 检查表是否有 node_ip 和 api_port 列,如果没有则添加
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'node_ip' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN node_ip TEXT")
                print("[INFO] 添加 node_ip 列到数据库")

            if 'api_port' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN api_port INTEGER")
                print("[INFO] 添加 api_port 列到数据库")

            # 更新服务信息
            cursor.execute('''
                UPDATE users 
                SET service_id = ?, 
                    service_name = ?,
                    node_ip = ?,
                    api_port = ?
                WHERE telegram_id = ?
            ''', (service_id, service_name, node_ip, api_port, user_id))

            conn.commit()
            conn.close()

            print(f"[INFO] 用户 {user_id} 服务信息已更新")
            print(f"       - 服务ID: {service_id}")
            print(f"       - 服务名: {service_name}")
            print(f"       - 节点IP: {node_ip}")
            print(f"       - API端口: {api_port}")

        except Exception as e:
            print(f"[ERROR] 更新服务信息失败: {e}")
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
    def user_exists(self, user_id: int) -> bool:
        """检查用户是否存在"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def update_user_api(self, user_id: int, security: str, api_key: str):
        """更新用户API信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET security = ?, api_key = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (security, api_key, user_id))
        conn.commit()
        conn.close()
        self.log_operation(user_id, "update_api", "更新API")

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
        self.log_operation(user_id, "update_status", f"状态: {status}")

    def get_user_by_telegram_id(self, user_id: int) -> Optional[Dict]:
        """根据Telegram ID获取用户信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'id': row[0],
            'name': row[1],
            'user_id': row[2],
            'status': row[3],
            'security': row[4],
            'api_key': row[5],
            'service_id': row[6],
            'service_name': row[7],
            'balance': row[8],
            'inviter_user_id': row[9],
            'invite_code': row[10],
            'has_used_invite': row[11],
            'created_at': row[12],
            'updated_at': row[13]
        }

    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """获取用户详细信息"""
        return self.get_user_by_telegram_id(user_id)

    def log_operation(self, user_id: int, operation: str, details: str = ""):
        """记录用户操作"""
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

    # ========== 订阅套餐管理（优化版）==========

    def get_all_plans(self) -> List[Dict]:
        """获取所有订阅套餐"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, plan_name, tier_level, monthly_rate, min_payment_30days, standard_capital, description
            FROM subscription_plans
            ORDER BY tier_level ASC
        ''')
        rows = cursor.fetchall()
        conn.close()

        plans = []
        for row in rows:
            plans.append({
                'id': row[0],
                'plan_name': row[1],
                'tier_level': row[2],
                'monthly_rate': row[3],
                'min_payment': row[4],
                'standard_capital': row[5],
                'description': row[6]
            })
        return plans

    def get_plan_by_id(self, plan_id: int) -> Optional[Dict]:
        """根据ID获取套餐信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, plan_name, tier_level, monthly_rate, min_payment_30days, standard_capital
            FROM subscription_plans
            WHERE id = ?
        ''', (plan_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            'id': row[0],
            'plan_name': row[1],
            'tier_level': row[2],
            'monthly_rate': row[3],
            'min_payment': row[4],
            'standard_capital': row[5]
        }

    # ========== 订阅管理（优化版）==========

    def create_subscription_flexible(self, user_id: int, payment_amount: float, days: int = 30) -> Tuple[bool, str]:
        """
        创建灵活订阅

        Args:
            user_id: 用户ID
            payment_amount: 用户支付金额
            days: 订阅天数（默认30天）

        Returns:
            (是否成功, 消息)
        """
        # 1. 根据支付金额匹配档位
        tier_info = self.get_tier_by_payment(payment_amount)
        if not tier_info:
            return False, f"支付金额{payment_amount} USDT不足最低要求"

        # 2. 检查用户余额
        balance = self.get_user_balance(user_id)
        total_price = payment_amount * (days / 30)

        if balance < total_price:
            return False, f"余额不足。需要{total_price:.2f} USDT，当前余额{balance:.2f} USDT"

        # 3. 扣除余额
        conn = self._get_connection()
        cursor = conn.cursor()

        new_balance = balance - total_price
        cursor.execute('''
            UPDATE user_balance 
            SET balance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (new_balance, user_id))

        # 4. 创建订阅记录
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days)
        actual_capital = tier_info['actual_capital']

        cursor.execute('''
            INSERT INTO user_subscriptions 
            (user_id, plan_id, tier_level, monthly_rate, payment_amount, actual_capital, start_date, end_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
        ''', (user_id, tier_info['id'], tier_info['tier_level'], tier_info['monthly_rate'],
              payment_amount, actual_capital, start_date, end_date))

        conn.commit()
        conn.close()

        self.log_operation(user_id, "create_subscription_flexible",
                          f"档位:{tier_info['plan_name']}, 支付:{payment_amount}, 额度:{actual_capital:.2f}, 天数:{days}")

        return True, f"订阅成功！{tier_info['plan_name']} | 可用额度: {actual_capital:,.2f} USDT"

    def create_subscription(self, user_id: int, plan_id: int, days: int = 30) -> bool:
        """
        创建标准订阅（使用套餐的最低费用）

        兼容旧版本接口
        """
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return False

        payment_amount = plan['min_payment'] * (days / 30)
        success, _ = self.create_subscription_flexible(user_id, payment_amount, days)
        return success

    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """获取用户当前订阅"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                us.id, 
                us.plan_id, 
                us.tier_level,
                us.monthly_rate,
                us.payment_amount,
                us.actual_capital, 
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
            'tier_level': row[2],
            'monthly_rate': row[3],
            'payment_amount': row[4],
            'max_capital': row[5],  # 实际可用资金额度
            'start_date': row[6],
            'end_date': row[7],
            'status': row[8],
            'plan_name': row[9]
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

    def is_subscription_valid(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """检查订阅是否有效"""
        return self.check_subscription_status(user_id)

    # ========== 余额管理 ==========

    def get_user_balance(self, user_id: int) -> float:
        """获取用户余额"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0.0

    def add_balance(self, user_id: int, amount: float) -> bool:
        """增加用户余额"""
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
        return True

    def deduct_balance(self, user_id: int, amount: float) -> bool:
        """扣除用户余额"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT balance FROM user_balance WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()

        if not row or row[0] < amount:
            conn.close()
            return False

        new_balance = row[0] - amount
        cursor.execute('''
            UPDATE user_balance 
            SET balance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (new_balance, user_id))

        conn.commit()
        conn.close()
        return True

    # ========== 充值记录 ==========

    def create_recharge_record(self, user_id: int, amount: float, tx_hash: str = None,
                              payment_address: str = None) -> int:
        """创建充值记录"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO recharge_records (user_id, amount, tx_hash, payment_address, status)
            VALUES (?, ?, ?, ?, 'pending')
        ''', (user_id, amount, tx_hash, payment_address))

        record_id = cursor.lastrowid
        conn.commit()
        conn.close()

        self.log_operation(user_id, "create_recharge", f"创建充值记录: {amount} USDT")
        return record_id

    def verify_recharge(self, record_id: int) -> bool:
        """验证并确认充值"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT user_id, amount, status
            FROM recharge_records
            WHERE id = ?
        ''', (record_id,))

        row = cursor.fetchone()
        if not row or row[2] == 'completed':
            conn.close()
            return False

        user_id, amount, _ = row

        cursor.execute('''
            UPDATE recharge_records
            SET status = 'completed', verified_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (record_id,))

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

    # ========== 邀请码管理 ==========

    def validate_invite_code(self, code: str, user_id: int) -> tuple:
        """验证邀请码"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT has_used_invite FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row and row[0] == 1:
            conn.close()
            return False, "您已使用过邀请码"

        cursor.execute('''
            SELECT owner_user_id, max_uses, current_uses, is_active
            FROM invite_codes
            WHERE code = ?
        ''', (code,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return False, "邀请码不存在"

        owner, max_uses, current_uses, is_active = row

        if not is_active:
            return False, "邀请码已失效"

        if max_uses > 0 and current_uses >= max_uses:
            return False, "邀请码使用次数已达上限"

        if owner == user_id:
            return False, "不能使用自己的邀请码"

        return True, owner

    def use_invite_code(self, code: str, user_id: int) -> bool:
        """使用邀请码"""
        is_valid, result = self.validate_invite_code(code, user_id)
        if not is_valid:
            return False

        owner_user_id = result
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE invite_codes
            SET current_uses = current_uses + 1
            WHERE code = ?
        ''', (code,))

        cursor.execute('''
            UPDATE users
            SET has_used_invite = 1
            WHERE user_id = ?
        ''', (user_id,))

        if owner_user_id:
            cursor.execute('''
                INSERT INTO user_invitations (inviter_user_id, invitee_user_id, invite_code)
                VALUES (?, ?, ?)
            ''', (owner_user_id, user_id, code))

        conn.commit()
        conn.close()

        self.log_operation(user_id, "use_invite_code", f"使用邀请码: {code}")
        return True

    def create_user_invite_code(self, user_id: int) -> str:
        """为用户创建邀请码"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT invite_code FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()

        if row and row[0]:
            conn.close()
            return row[0]

        invite_code = f"USER{user_id}{uuid4().hex[:6].upper()}"

        cursor.execute('''
            INSERT INTO invite_codes (code, owner_user_id, max_uses, discount_percent)
            VALUES (?, ?, 0, 10.0)
        ''', (invite_code, user_id))

        cursor.execute('''
            UPDATE users
            SET invite_code = ?
            WHERE user_id = ?
        ''', (invite_code, user_id))

        conn.commit()
        conn.close()

        self.log_operation(user_id, "create_invite_code", f"创建邀请码: {invite_code}")
        return invite_code


    def get_user_inviter(self, user_id: int) -> Optional[int]:
        """获取邀请人ID"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT inviter_user_id
            FROM user_invitations
            WHERE invitee_user_id = ?
        ''', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def record_invite_reward(self, inviter_user_id: int, invitee_user_id: int,
                           recharge_amount: float, reward_amount: float,
                           recharge_record_id: int = None) -> bool:
        """记录邀请奖励"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO invite_rewards 
            (inviter_user_id, invitee_user_id, recharge_amount, reward_amount, recharge_record_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (inviter_user_id, invitee_user_id, recharge_amount, reward_amount, recharge_record_id))

        self.add_balance(inviter_user_id, reward_amount)

        conn.commit()
        conn.close()

        self.log_operation(inviter_user_id, "invite_reward",
                          f"邀请奖励: {reward_amount} USDT from user {invitee_user_id}")
        return True

    def get_user_invite_rewards(self, user_id: int, limit: int = 20) -> List[Dict]:
        """获取用户邀请奖励记录"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT invitee_user_id, recharge_amount, reward_amount, created_at
            FROM invite_rewards
            WHERE inviter_user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))

        rows = cursor.fetchall()
        conn.close()

        rewards = []
        for row in rows:
            rewards.append({
                'invitee_user_id': row[0],
                'recharge_amount': row[1],
                'reward_amount': row[2],
                'created_at': row[3]
            })
        return rewards

    def get_user_address(self, user_id: int) -> Optional[str]:
        """获取用户地址（别名）"""
        return self.get_user_payment_address(user_id)

    def get_invite_leaderboard(self, limit: int = 10) -> List[Dict]:
        """获取邀请排行榜"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT 
                u.user_id,
                u.name,
                COUNT(ui.id) as invite_count,
                COALESCE(SUM(ir.reward_amount), 0) as total_rewards
            FROM users u
            LEFT JOIN user_invitations ui ON u.user_id = ui.inviter_user_id
            LEFT JOIN invite_rewards ir ON u.user_id = ir.inviter_user_id
            GROUP BY u.user_id, u.name
            HAVING invite_count > 0
            ORDER BY invite_count DESC, total_rewards DESC
            LIMIT ?
        ''', (limit,))

        rows = cursor.fetchall()
        conn.close()

        leaderboard = []
        for row in rows:
            leaderboard.append({
                'user_id': row[0],
                'name': row[1],
                'invite_count': row[2],
                'total_rewards': row[3]
            })
        return leaderboard

    def get_user_invitees(self, user_id: int, limit: int = 50) -> List[Dict]:
        """获取用户邀请的人员列表"""
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
            LEFT JOIN invite_rewards ir ON ui.invitee_user_id = ir.invitee_user_id AND ui.inviter_user_id = ir.inviter_user_id
            WHERE ui.inviter_user_id = ?
            GROUP BY u.user_id, u.name, ui.created_at
            ORDER BY ui.created_at DESC
            LIMIT ?
        ''', (user_id, limit))

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

    # 补充方法 - 添加到database_optimized.py中

    """
    这些方法需要添加到 Database 类中
    位置：在 get_user_invitees() 方法之后，便捷函数之前
    """

    # ========== 邀请码高级功能 ==========

    def apply_invite_code(self, user_id: int, code: str) -> Tuple[bool, float, str, Optional[str]]:
        """
        应用邀请码（完整版）

        Returns:
            (是否成功, 折扣百分比, 消息, 用户邀请码)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 检查用户是否已使用过邀请码
            cursor.execute('SELECT has_used_invite FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if row and row[0] == 1:
                conn.close()
                return False, 0, "您已使用过邀请码", None

            # 验证邀请码
            cursor.execute('''
                    SELECT id, owner_user_id, max_uses, current_uses, discount_percent, is_active
                    FROM invite_codes
                    WHERE code = ?
                ''', (code.upper(),))

            code_row = cursor.fetchone()

            if not code_row:
                conn.close()
                return False, 0, "邀请码不存在", None

            code_id, inviter_user_id, max_uses, current_uses, discount, is_active = code_row

            if not is_active:
                conn.close()
                return False, 0, "邀请码已失效", None

            if max_uses > 0 and current_uses >= max_uses:
                conn.close()
                return False, 0, "邀请码使用次数已达上限", None

            if inviter_user_id == user_id:
                conn.close()
                return False, 0, "不能使用自己的邀请码", None

            # 标记用户已使用邀请码
            cursor.execute('''
                    UPDATE users
                    SET has_used_invite = 1
                    WHERE user_id = ?
                ''', (user_id,))

            # 记录邀请码使用
            cursor.execute('''
                    INSERT INTO invite_code_usage (code_id, user_id, discount_amount)
                    VALUES (?, ?, 0)
                ''', (code_id, user_id))

            # 更新邀请码使用次数
            cursor.execute('''
                    UPDATE invite_codes 
                    SET current_uses = current_uses + 1
                    WHERE id = ?
                ''', (code_id,))

            # 如果有邀请人，记录邀请关系
            if inviter_user_id:
                cursor.execute('''
                        INSERT INTO user_invitations 
                        (inviter_user_id, invitee_user_id, invite_code)
                        VALUES (?, ?, ?)
                    ''', (inviter_user_id, user_id, code.upper()))

            # 为用户生成专属邀请码
            user_invite_code = self._generate_user_invite_code(cursor, user_id)

            conn.commit()
            conn.close()

            self.log_operation(user_id, "apply_invite_code",
                               f"使用邀请码: {code}, 折扣: {discount}%, 生成邀请码: {user_invite_code}")

            return True, discount, "邀请码应用成功!", user_invite_code

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"应用邀请码失败: {e}")
            return False, 0, f"应用邀请码失败: {str(e)}", None

    def _generate_user_invite_code(self, cursor, user_id: int) -> str:
        """为用户生成专属邀请码（内部方法）"""
        import random
        import string

        # 检查是否已有邀请码
        cursor.execute('''
                SELECT code FROM invite_codes 
                WHERE owner_user_id = ?
            ''', (user_id,))

        existing = cursor.fetchone()
        if existing:
            return existing[0]

        # 生成新邀请码
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

        # 如果随机生成失败，使用基础格式
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
                WHERE owner_user_id = ? AND is_active = 1
                LIMIT 1
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
                FROM invite_code_usage icu
                JOIN invite_codes ic ON icu.code_id = ic.id
                WHERE icu.user_id = ?
                ORDER BY icu.used_at DESC
                LIMIT 1
            ''', (user_id,))

        row = cursor.fetchone()
        conn.close()

        return row[0] if row else 0.0

    def record_invite_code_usage(self, user_id: int, original_amount: float, bonus_amount: float) -> bool:
        """记录邀请码使用产生的赠送金额"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                    UPDATE invite_code_usage
                    SET discount_amount = ?
                    WHERE user_id = ?
                ''', (bonus_amount, user_id))

            conn.commit()
            conn.close()

            logger.info(f"记录邀请码使用: 用户={user_id}, 原始={original_amount}, 赠送={bonus_amount}")
            return True

        except Exception as e:
            conn.rollback()
            conn.close()
            logger.error(f"记录邀请码使用失败: {e}")
            return False

    def process_invite_reward(
            self,
            invitee_user_id: int,
            recharge_amount: float,
            recharge_record_id: int = None
    ) -> Tuple[bool, Optional[int], float]:
        """
        处理邀请奖励（自动发放给邀请人）

        Args:
            invitee_user_id: 被邀请人（充值人）ID
            recharge_amount: 充值金额
            recharge_record_id: 充值记录ID

        Returns:
            (是否有邀请人, 邀请人ID, 奖励金额)
        """
        # 获取邀请人
        inviter_id = self.get_user_inviter(invitee_user_id)

        if not inviter_id:
            return False, None, 0.0

        # 计算奖励（10%）
        reward_amount = recharge_amount * 0.10

        # 发放奖励
        self.add_balance(inviter_id, reward_amount)

        # 记录奖励
        self.record_invite_reward(
            inviter_user_id=inviter_id,
            invitee_user_id=invitee_user_id,
            recharge_amount=recharge_amount,
            reward_amount=reward_amount,
            recharge_record_id=recharge_record_id
        )

        # 更新邀请关系表中的累计奖励
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
                UPDATE user_invitations
                SET inviter_reward_total = inviter_reward_total + ?
                WHERE inviter_user_id = ? AND invitee_user_id = ?
            ''', (reward_amount, inviter_id, invitee_user_id))
        conn.commit()
        conn.close()

        logger.info(
            f"邀请奖励已发放: 邀请人={inviter_id}, "
            f"被邀请人={invitee_user_id}, "
            f"充值={recharge_amount}, 奖励={reward_amount}"
        )

        return True, inviter_id, reward_amount

    def get_invite_stats(self, user_id: int) -> Dict:
        """
        获取用户的完整邀请统计

        Returns:
            {
                'my_code': '我的邀请码',
                'invitee_count': 邀请人数,
                'total_reward': 累计奖励,
                'inviter_info': 我的邀请人信息,
                'has_used_invite': 是否使用过邀请码,
                'my_discount': 我的折扣百分比
            }
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. 获取我的邀请码
        my_code = self.get_user_invite_code(user_id)

        # 2. 统计我邀请的人数
        cursor.execute('''
                SELECT COUNT(*) FROM user_invitations 
                WHERE inviter_user_id = ?
            ''', (user_id,))
        invitee_count = cursor.fetchone()[0]

        # 3. 统计累计奖励
        cursor.execute('''
                SELECT COALESCE(SUM(reward_amount), 0) FROM invite_rewards 
                WHERE inviter_user_id = ?
            ''', (user_id,))
        total_reward = cursor.fetchone()[0]

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
                'reward_contributed': inviter_row[2],
                'joined_at': inviter_row[3]
            }

        # 5. 检查是否使用过邀请码
        cursor.execute('SELECT has_used_invite FROM users WHERE user_id = ?', (user_id,))
        has_used_row = cursor.fetchone()
        has_used_invite = bool(has_used_row[0]) if has_used_row else False

        # 6. 获取我的折扣
        my_discount = self.get_user_invite_discount(user_id)

        conn.close()

        return {
            'my_code': my_code,
            'invitee_count': invitee_count,
            'total_reward': total_reward,
            'inviter_info': inviter_info,
            'has_used_invite': has_used_invite,
            'my_discount': my_discount
        }

    def create_invite_code(
            self,
            code: str,
            discount_percent: float = 10.0,
            max_uses: int = 0,
            owner_user_id: int = None,
            expires_at: str = None
    ) -> Tuple[bool, str]:
        """创建新的邀请码（管理员功能）"""
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
            return False, f"创建邀请码失败: {str(e)}"

    def get_all_invite_codes(self) -> List[Dict]:
        """获取所有邀请码列表（管理员功能）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
                SELECT code, discount_percent, max_uses, current_uses, 
                       is_active, owner_user_id, created_at
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
                'owner_user_id': row[5],
                'created_at': row[6]
            })

        return codes

    # ========== 补充：订阅相关表的创建 ==========
    # 注意：这部分需要添加到 create_tables() 方法中

    def _create_invite_code_usage_table(self, cursor):
        """创建邀请码使用记录表"""
        cursor.execute('''
                CREATE TABLE IF NOT EXISTS invite_code_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    discount_amount REAL NOT NULL DEFAULT 0,
                    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (code_id) REFERENCES invite_codes(id),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    UNIQUE(code_id, user_id)
                );
            ''')


# ========== 使用说明 ==========
"""
这些方法需要添加到 database_optimized.py 的 Database 类中。

添加位置：
---------
在 get_user_invitees() 方法之后
在 # ========== 便捷函数（保持向后兼容）========== 之前

同时需要在 create_tables() 方法中添加邀请码使用记录表：
在创建 invite_rewards 表之后，调用：
    # 12. 邀请码使用记录表
    self._create_invite_code_usage_table(cursor)

完整的行数应该达到 1400 行左右。

主要新增方法：
1. apply_invite_code() - 应用邀请码
2. _generate_user_invite_code() - 生成用户邀请码
3. get_user_invite_code() - 获取用户邀请码
4. get_user_invite_discount() - 获取折扣
5. record_invite_code_usage() - 记录使用
6. process_invite_reward() - 处理奖励
7. get_invite_stats() - 获取统计
8. create_invite_code() - 创建邀请码（管理）
9. get_all_invite_codes() - 获取所有邀请码（管理）
"""


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
    print("=" * 70)
    print("测试灵活订阅系统")
    print("=" * 70)

    # 创建数据库
    db = Database()
    db.create_tables()

    print("\n✅ 数据库表创建成功\n")

    # 测试计算实际资金额度
    print("=" * 70)
    print("测试: 计算实际可用资金额度")
    print("=" * 70)

    test_cases = [
        (1.0, 100, "入门档标准"),
        (1.0, 150, "入门档增强"),
        (0.8, 400, "进阶档标准"),
        (0.8, 600, "进阶档增强"),
        (0.7, 700, "专业档标准"),
        (0.7, 1000, "专业档增强"),
        (0.6, 1200, "企业档标准"),
        (0.6, 1500, "企业档增强"),
        (0.5, 2500, "旗舰档标准"),
        (0.5, 3000, "旗舰档增强"),
    ]

    for rate, payment, desc in test_cases:
        actual = db.calculate_actual_capital(rate, payment)
        print(f"{desc:15s} | 费率{rate}% | 支付{payment:5.0f} USDT → 额度 {actual:10,.2f} USDT")

    # 测试根据支付金额匹配档位
    print("\n" + "=" * 70)
    print("测试: 根据支付金额自动匹配档位")
    print("=" * 70)

    test_payments = [50, 100, 200, 400, 600, 700, 1000, 1200, 1500, 2500, 3000]

    for payment in test_payments:
        tier = db.get_tier_by_payment(payment)
        if tier:
            print(f"支付{payment:5.0f} USDT → {tier['plan_name']:6s} | "
                  f"费率{tier['monthly_rate']}% | 获得额度 {tier['actual_capital']:10,.2f} USDT")
        else:
            print(f"支付{payment:5.0f} USDT → ❌ 不足最低要求")

    # 测试订阅套餐列表
    print("\n" + "=" * 70)
    print("测试: 获取所有订阅套餐")
    print("=" * 70)

    plans = db.get_all_plans()
    for plan in plans:
        print(f"\n📦 {plan['plan_name']}")
        print(f"   档位: {plan['tier_level']}")
        print(f"   费率: {plan['monthly_rate']}%")
        print(f"   最低: {plan['min_payment']} USDT/月")
        print(f"   标准额度: {plan['standard_capital']:,} USDT")
        print(f"   {plan['description']}")

    print("\n" + "=" * 70)
    print("所有测试完成!")
    print("=" * 70)