"""
invite_system_enhancement.py - 增强的邀请激励系统
包含阶梯奖励、排行榜、成就系统

功能:
1. 多级邀请奖励(10%-20%)
2. 邀请排行榜
3. 邀请等级系统
4. 自动发放奖励
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class InviteIncentiveSystem:
    """邀请激励系统 - 管理邀请奖励和等级"""

    def __init__(self, db):
        """
        初始化邀请激励系统

        Args:
            db: Database 实例
        """
        self.db = db

        # 阶梯奖励配置
        self.tier_rewards = {
            1: {'invites': 1, 'reward_pct': 10, 'badge': '🥉', 'name': '青铜'},
            2: {'invites': 3, 'reward_pct': 12, 'badge': '🥈', 'name': '白银'},
            3: {'invites': 5, 'reward_pct': 15, 'badge': '🥇', 'name': '黄金'},
            4: {'invites': 10, 'reward_pct': 18, 'badge': '💎', 'name': '铂金'},
            5: {'invites': 20, 'reward_pct': 20, 'badge': '👑', 'name': '王者'}
        }

    def get_user_tier(self, user_id: int) -> Dict:
        """
        获取用户的邀请等级

        Returns:
            {
                'tier': 等级(0-5),
                'tier_name': 等级名称,
                'reward_pct': 奖励百分比,
                'badge': 徽章emoji,
                'invites_count': 已邀请人数,
                'next_tier': 下一等级信息(如果有)
            }
        """
        # 获取用户邀请人数
        invitees = self.db.get_user_invitees(user_id)
        invite_count = len(invitees)

        # 确定当前等级
        current_tier = 0
        current_reward_pct = 10  # 默认10%
        current_badge = '🌟'
        current_name = '新手'

        for tier, config in self.tier_rewards.items():
            if invite_count >= config['invites']:
                current_tier = tier
                current_reward_pct = config['reward_pct']
                current_badge = config['badge']
                current_name = config['name']

        # 计算下一等级信息
        next_tier_info = None
        if current_tier < max(self.tier_rewards.keys()):
            next_tier = current_tier + 1
            next_config = self.tier_rewards[next_tier]
            next_tier_info = {
                'tier': next_tier,
                'tier_name': next_config['name'],
                'required_invites': next_config['invites'],
                'remaining': next_config['invites'] - invite_count,
                'reward_pct': next_config['reward_pct'],
                'badge': next_config['badge']
            }

        return {
            'tier': current_tier,
            'tier_name': current_name,
            'reward_pct': current_reward_pct,
            'badge': current_badge,
            'invites_count': invite_count,
            'next_tier': next_tier_info
        }

    def calculate_invite_reward(self, user_id: int, recharge_amount: float) -> float:
        """
        计算邀请奖励金额

        Args:
            user_id: 邀请人ID
            recharge_amount: 被邀请人充值金额

        Returns:
            奖励金额(USDT)
        """
        tier_info = self.get_user_tier(user_id)
        reward_pct = tier_info['reward_pct']
        reward_amount = recharge_amount * (reward_pct / 100)
        return reward_amount

    def format_user_invite_stats(self, user_id: int) -> str:
        """
        格式化用户邀请统计信息

        Returns:
            格式化的邀请统计文本
        """
        # 获取等级信息
        tier_info = self.get_user_tier(user_id)

        # 获取邀请码
        invite_code = self.db.get_user_invite_code(user_id)

        if not invite_code:
            return "❌ 您还没有邀请码,请先使用邀请码完成首次充值"

        # 获取邀请的用户列表
        invitees = self.db.get_user_invitees(user_id)

        # 获取累计奖励
        rewards = self.db.get_user_invite_rewards(user_id)
        total_rewards = sum(r['reward_amount'] for r in rewards)

        report = "🎁 <b>我的邀请统计</b>\n"
        report += "=" * 30 + "\n\n"

        # 等级徽章和信息
        if tier_info['tier'] > 0:
            report += f"{tier_info['badge']} <b>{tier_info['tier_name']} (等级{tier_info['tier']})</b>\n"
        else:
            report += f"{tier_info['badge']} <b>{tier_info['tier_name']}</b>\n"

        report += f"当前奖励比例: <b>{tier_info['reward_pct']}%</b>\n\n"

        # 邀请码信息
        report += f"📋 我的邀请码: <code>{invite_code}</code>\n"
        report += f"👥 已邀请人数: <b>{tier_info['invites_count']}</b>人\n"
        report += f"💰 累计奖励: <b>{total_rewards:.2f} USDT</b>\n\n"

        # 升级进度
        if tier_info['next_tier']:
            next_tier = tier_info['next_tier']
            report += f"📈 <b>升级进度</b>\n"
            report += f"下一等级: {next_tier['badge']} {next_tier['tier_name']} (等级{next_tier['tier']})\n"
            report += f"还需邀请: <b>{next_tier['remaining']}</b>人\n"
            report += f"升级后奖励: <b>{next_tier['reward_pct']}%</b>\n\n"
        else:
            report += f"🎉 恭喜!您已达到最高等级!\n\n"

        # 奖励说明
        report += "💡 <b>奖励说明</b>\n"
        report += f"好友使用您的邀请码充值后:\n"
        report += f"• 您获得充值金额的 <b>{tier_info['reward_pct']}%</b> 作为奖励\n"
        report += f"• 好友获得额外 <b>10%</b> 充值赠送\n"
        report += f"• 双赢模式,永久有效!\n\n"

        # 最近邀请
        if invitees:
            recent_count = min(3, len(invitees))
            report += f"📋 <b>最近邀请的用户</b>\n"
            for invitee in invitees[:recent_count]:
                report += f"• {invitee['invitee_name']} - {invitee['created_at'][:10]}\n"

            if len(invitees) > recent_count:
                report += f"...还有 {len(invitees) - recent_count} 人\n"

        return report

    def format_invite_leaderboard(self, limit: int = 10) -> str:
        """
        格式化邀请排行榜

        Args:
            limit: 显示前N名

        Returns:
            格式化的排行榜文本
        """
        leaderboard = self.db.get_invite_leaderboard(limit)

        report = "🏆 <b>邀请排行榜</b>\n"
        report += "=" * 30 + "\n\n"

        if not leaderboard:
            report += "暂无排行数据\n"
            return report

        for idx, entry in enumerate(leaderboard, 1):
            user_name = entry['user_name']
            invite_count = entry['invite_count']
            total_rewards = entry['total_rewards']

            # 获取等级信息
            tier_info = self.get_user_tier(entry['user_id'])

            # 前三名特殊标记
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            else:
                medal = f"{idx}."

            report += f"{medal} <b>{user_name}</b> {tier_info['badge']}\n"
            report += f"   邀请: {invite_count}人 | 奖励: {total_rewards:.2f} USDT\n\n"

        report += "💡 邀请更多好友,登上排行榜!\n"

        return report

    def format_tier_system_info(self) -> str:
        """
        格式化等级系统说明

        Returns:
            等级系统说明文本
        """
        report = "⭐ <b>邀请等级系统</b>\n"
        report += "=" * 30 + "\n\n"

        report += "邀请越多,奖励越高!\n\n"

        for tier, config in sorted(self.tier_rewards.items()):
            report += f"{config['badge']} <b>{config['name']} (等级{tier})</b>\n"
            report += f"   需要邀请: {config['invites']}人\n"
            report += f"   奖励比例: <b>{config['reward_pct']}%</b>\n\n"

        report += "💡 <b>收益示例</b>\n"
        report += "达到等级3 (邀请5人):\n"
        report += "• 好友充值 1000 USDT\n"
        report += "• 您获得: <b>150 USDT</b> 奖励!\n"
        report += "• 好友获得: <b>1100 USDT</b> 到账!\n\n"

        report += "达到等级5 (邀请20人):\n"
        report += "• 好友充值 1000 USDT\n"
        report += "• 您获得: <b>200 USDT</b> 奖励!\n"

        return report

    def format_invitee_list(self, user_id: int) -> str:
        """
        格式化邀请的用户列表

        Args:
            user_id: 邀请人ID

        Returns:
            格式化的邀请列表
        """
        invitees = self.db.get_user_invitees(user_id)

        if not invitees:
            return "👥 您还没有邀请任何用户\n\n快去分享您的邀请码吧!"

        report = f"👥 <b>我的邀请列表 (共{len(invitees)}人)</b>\n"
        report += "=" * 30 + "\n\n"

        for invitee in invitees:
            report += f"• <b>{invitee['invitee_name']}</b>\n"
            report += f"  邀请时间: {invitee['created_at'][:10]}\n"

            # 如果有奖励记录
            rewards = [r for r in self.db.get_user_invite_rewards(user_id)
                       if r['invitee_user_id'] == invitee['invitee_user_id']]

            if rewards:
                total_reward = sum(r['reward_amount'] for r in rewards)
                report += f"  已获奖励: {total_reward:.2f} USDT\n"

            report += "\n"

        return report

    def process_recharge_reward(
            self,
            invitee_user_id: int,
            recharge_amount: float
    ) -> Optional[Dict]:
        """
        处理充值并发放邀请奖励

        Args:
            invitee_user_id: 被邀请人(充值人)ID
            recharge_amount: 充值金额

        Returns:
            奖励信息字典,如果没有邀请人返回None
        """
        # 获取邀请人
        inviter_id = self.db.get_user_inviter(invitee_user_id)

        if not inviter_id:
            logger.info(f"用户 {invitee_user_id} 没有邀请人")
            return None

        # 计算奖励
        reward_amount = self.calculate_invite_reward(inviter_id, recharge_amount)

        # 发放奖励到邀请人账户
        self.db.add_balance(inviter_id, reward_amount)

        # 记录奖励
        self.db.record_invite_reward(
            inviter_user_id=inviter_id,
            invitee_user_id=invitee_user_id,
            recharge_amount=recharge_amount,
            reward_amount=reward_amount
        )

        # 获取等级信息
        tier_info = self.get_user_tier(inviter_id)

        logger.info(
            f"邀请奖励已发放: 邀请人={inviter_id}, "
            f"被邀请人={invitee_user_id}, "
            f"充值={recharge_amount}, 奖励={reward_amount}"
        )

        return {
            'inviter_id': inviter_id,
            'reward_amount': reward_amount,
            'reward_pct': tier_info['reward_pct'],
            'tier': tier_info['tier'],
            'tier_name': tier_info['tier_name']
        }


# 测试代码
if __name__ == "__main__":
    print("=" * 50)
    print("邀请激励系统测试")
    print("=" * 50)

    # 需要Database实例才能运行
    print("\n此模块需要配合 Database 类使用")
    print("使用示例:")
    print("""
from database import Database
from invite_system_enhancement import InviteIncentiveSystem

# 初始化
db = Database()
invite_system = InviteIncentiveSystem(db)

# 获取用户等级
tier_info = invite_system.get_user_tier(user_id)
print(f"用户等级: {tier_info['tier_name']}")
print(f"奖励比例: {tier_info['reward_pct']}%")

# 格式化统计信息
stats = invite_system.format_user_invite_stats(user_id)
print(stats)

# 处理充值奖励
reward_info = invite_system.process_recharge_reward(
    invitee_user_id=123456,
    recharge_amount=1000.0
)
if reward_info:
    print(f"奖励已发放: {reward_info['reward_amount']} USDT")
    """)