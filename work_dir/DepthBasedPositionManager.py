"""
基于盘口深度的动态仓位管理器
核心理念：根据订单簿深度动态调整开仓金额，确保止损时能快速离场
"""

from typing import Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class OrderBookAnalyzer:
    """订单簿深度分析器"""
    
    def __init__(self):
        # 深度分析配置
        self.depth_levels = 10  # 分析10档深度
        self.safe_liquidity_ratio = 0.3  # 安全流动性比例：你的仓位不超过盘口的30%
        self.emergency_liquidity_ratio = 0.5  # 紧急情况可承受50%
        
    def analyze_orderbook(self, orderbook: Dict, side: str = 'sell') -> Dict:
        """
        分析订单簿深度
        
        Args:
            orderbook: 订单簿数据
            side: 'buy' 或 'sell' (开多仓看卖盘，开空仓看买盘)
        
        Returns:
            深度分析结果
        """
        try:
            # 选择对应的盘口
            if side == 'buy':
                # 买入时看卖盘（asks）
                orders = orderbook.get('asks', [])
            else:
                # 卖出时看买盘（bids）
                orders = orderbook.get('bids', [])
            
            if not orders:
                return self._empty_analysis()
            
            # 提取价格和数量
            levels = []
            cumulative_volume = 0
            cumulative_value = 0
            
            for i, order in enumerate(orders[:self.depth_levels]):
                price = float(order[0])
                volume = float(order[1])
                value = price * volume
                
                cumulative_volume += volume
                cumulative_value += value
                
                levels.append({
                    'level': i + 1,
                    'price': price,
                    'volume': volume,
                    'value': value,
                    'cumulative_volume': cumulative_volume,
                    'cumulative_value': cumulative_value
                })
            
            # 计算关键指标
            top_price = levels[0]['price']
            total_volume = cumulative_volume
            total_value = cumulative_value
            avg_price = total_value / total_volume if total_volume > 0 else top_price
            
            # 计算不同价格偏离下的可用流动性
            liquidity_1pct = self._calculate_liquidity(levels, top_price, 0.01)  # 1%偏离
            liquidity_2pct = self._calculate_liquidity(levels, top_price, 0.02)  # 2%偏离
            liquidity_5pct = self._calculate_liquidity(levels, top_price, 0.05)  # 5%偏离
            
            return {
                'valid': True,
                'side': side,
                'top_price': top_price,
                'top_volume': levels[0]['volume'],
                'top_value': levels[0]['value'],
                'total_volume': total_volume,
                'total_value': total_value,
                'avg_price': avg_price,
                'levels_count': len(levels),
                'liquidity_1pct': liquidity_1pct,
                'liquidity_2pct': liquidity_2pct,
                'liquidity_5pct': liquidity_5pct,
                'levels': levels
            }
            
        except Exception as e:
            logger.error(f"订单簿分析失败: {e}")
            return self._empty_analysis()
    
    def _calculate_liquidity(self, levels: list, base_price: float, 
                            deviation: float) -> float:
        """
        计算特定价格偏离范围内的流动性
        
        Args:
            levels: 订单簿层级数据
            base_price: 基准价格
            deviation: 价格偏离百分比
        
        Returns:
            可用流动性（USDT价值）
        """
        threshold_price = base_price * (1 + deviation)
        liquidity = 0
        
        for level in levels:
            if level['price'] <= threshold_price:
                liquidity += level['value']
            else:
                break
        
        return liquidity
    
    def _empty_analysis(self) -> Dict:
        """返回空分析结果"""
        return {
            'valid': False,
            'side': None,
            'top_price': 0,
            'top_volume': 0,
            'top_value': 0,
            'total_volume': 0,
            'total_value': 0,
            'avg_price': 0,
            'levels_count': 0,
            'liquidity_1pct': 0,
            'liquidity_2pct': 0,
            'liquidity_5pct': 0,
            'levels': []
        }


class DepthBasedPositionManager:
    """
    基于深度的仓位管理器
    核心：确保你的仓位在紧急止损时能被市场吸收
    """
    
    def __init__(self):
        self.analyzer = OrderBookAnalyzer()
        
        # 仓位管理配置
        self.max_position_ratio = 0.3  # 最大仓位不超过盘口流动性的30%
        self.safe_position_ratio = 0.2  # 安全仓位为20%
        self.min_position_value = 100  # 最小开仓金额100 USDT
        
        # 止损场景配置
        self.stop_loss_slippage = 0.03  # 止损预期滑点3%
        self.emergency_exit_depth = 5  # 紧急止损会吃掉5档深度
        
    def calculate_safe_position_size(
        self,
        pair: str,
        orderbook: Dict,
        proposed_amount: float,
        current_price: float,
        is_short: bool = False
    ) -> Tuple[float, Dict]:
        """
        计算安全的开仓金额
        
        Args:
            pair: 交易对
            orderbook: 订单簿数据
            proposed_amount: 策略建议的开仓金额
            current_price: 当前价格
            is_short: 是否做空
        
        Returns:
            (调整后的金额, 分析详情)
        """
        # 分析订单簿
        # 开多仓需要看卖盘（止损时卖出）
        # 开空仓需要看买盘（止损时买入）
        side = 'sell' if not is_short else 'buy'
        depth_analysis = self.analyzer.analyze_orderbook(orderbook, side)
        
        if not depth_analysis['valid']:
            logger.warning(f"{pair} 订单簿数据无效，使用保守仓位")
            return self._conservative_position(proposed_amount), depth_analysis
        
        # 计算止损场景下需要的流动性
        # 假设止损会造成3%的额外滑点，需要在5%价格偏离内完成
        required_liquidity = depth_analysis['liquidity_5pct']
        
        # 计算安全仓位上限
        safe_position = required_liquidity * self.safe_position_ratio
        max_position = required_liquidity * self.max_position_ratio
        
        # 决策逻辑
        if proposed_amount <= safe_position:
            # 在安全范围内，全部开仓
            final_amount = proposed_amount
            decision = "SAFE"
            reason = f"仓位在安全范围内 ({proposed_amount:.0f} <= {safe_position:.0f})"
            
        elif proposed_amount <= max_position:
            # 在可接受范围内，全部开仓但标记为警告
            final_amount = proposed_amount
            decision = "ACCEPTABLE"
            reason = f"仓位可接受但需谨慎 ({proposed_amount:.0f} <= {max_position:.0f})"
            
        else:
            # 超出安全范围，削减到最大限度
            final_amount = max_position
            decision = "REDUCED"
            reason = f"仓位过大，削减 {proposed_amount:.0f} -> {final_amount:.0f}"
        
        # 确保不低于最小金额
        if final_amount < self.min_position_value:
            if proposed_amount >= self.min_position_value:
                # 原计划开仓，但流动性不足
                final_amount = 0
                decision = "REJECTED"
                reason = f"流动性不足，放弃开仓（需要{self.min_position_value}，可用{safe_position:.0f}）"
            else:
                # 本来就是小仓位
                final_amount = proposed_amount
                decision = "SMALL"
                reason = "小额仓位，忽略流动性检查"
        
        # 构建详细信息
        details = {
            'pair': pair,
            'decision': decision,
            'reason': reason,
            'proposed_amount': proposed_amount,
            'final_amount': final_amount,
            'adjustment': final_amount - proposed_amount,
            'adjustment_pct': (final_amount / proposed_amount - 1) * 100 if proposed_amount > 0 else 0,
            'depth_analysis': depth_analysis,
            'liquidity': {
                'available_1pct': depth_analysis['liquidity_1pct'],
                'available_2pct': depth_analysis['liquidity_2pct'],
                'available_5pct': depth_analysis['liquidity_5pct'],
                'safe_limit': safe_position,
                'max_limit': max_position,
                'usage_ratio': (final_amount / required_liquidity * 100) if required_liquidity > 0 else 0
            }
        }
        
        # 打印日志
        self._log_decision(details)
        
        return final_amount, details
    
    def _conservative_position(self, proposed_amount: float) -> float:
        """
        保守的仓位策略（当无法获取订单簿时）
        削减到原计划的50%
        """
        return proposed_amount * 0.5
    
    def _log_decision(self, details: Dict):
        """记录决策日志"""
        pair = details['pair']
        decision = details['decision']
        proposed = details['proposed_amount']
        final = details['final_amount']
        reason = details['reason']
        
        if decision == "SAFE":
            logger.info(f"[{pair}] ✅ {reason}")
        elif decision == "ACCEPTABLE":
            logger.warning(f"[{pair}] ⚠️  {reason}")
        elif decision == "REDUCED":
            logger.warning(f"[{pair}] ⬇️  {reason}")
        elif decision == "REJECTED":
            logger.error(f"[{pair}] ❌ {reason}")
        else:
            logger.info(f"[{pair}] ℹ️  {reason}")
        
        # 打印流动性信息
        liq = details['liquidity']
        logger.info(
            f"[{pair}] 流动性: 1%内={liq['available_1pct']:.0f}, "
            f"2%内={liq['available_2pct']:.0f}, "
            f"5%内={liq['available_5pct']:.0f} USDT"
        )
        logger.info(
            f"[{pair}] 仓位限制: 安全={liq['safe_limit']:.0f}, "
            f"最大={liq['max_limit']:.0f}, "
            f"使用率={liq['usage_ratio']:.1f}%"
        )
    
    def estimate_stop_loss_impact(
        self,
        orderbook: Dict,
        position_size: float,
        entry_price: float,
        stop_loss_pct: float = -0.03,
        is_short: bool = False
    ) -> Dict:
        """
        估算止损时的市场冲击
        
        Args:
            orderbook: 订单簿
            position_size: 持仓金额（USDT）
            entry_price: 开仓价格
            stop_loss_pct: 止损百分比（如-3%）
            is_short: 是否做空
        
        Returns:
            止损影响分析
        """
        # 止损时的操作方向
        side = 'sell' if not is_short else 'buy'
        depth_analysis = self.analyzer.analyze_orderbook(orderbook, side)
        
        if not depth_analysis['valid']:
            return {'valid': False, 'warning': '无法获取订单簿数据'}
        
        # 计算需要吃掉多少档深度
        position_value = position_size
        remaining_value = position_value
        levels_consumed = 0
        total_slippage = 0
        
        for level in depth_analysis['levels']:
            if remaining_value <= 0:
                break
            
            level_value = level['value']
            consumed = min(remaining_value, level_value)
            remaining_value -= consumed
            levels_consumed += 1
            
            # 计算滑点
            price_diff = abs(level['price'] - entry_price)
            slippage = price_diff / entry_price
            total_slippage += slippage * (consumed / position_value)
        
        # 判断风险等级
        if levels_consumed <= 2:
            risk = "LOW"
            risk_text = "低风险：止损可在前2档完成"
        elif levels_consumed <= 5:
            risk = "MEDIUM"
            risk_text = "中风险：止损需要5档内"
        elif levels_consumed <= 10:
            risk = "HIGH"
            risk_text = "高风险：止损需要10档"
        else:
            risk = "CRITICAL"
            risk_text = "极高风险：止损可能无法完全成交"
        
        return {
            'valid': True,
            'risk_level': risk,
            'risk_description': risk_text,
            'levels_consumed': levels_consumed,
            'estimated_slippage': total_slippage * 100,  # 转为百分比
            'total_slippage_cost': position_value * total_slippage,
            'can_exit_completely': remaining_value <= 0,
            'remaining_value': remaining_value
        }


# 使用示例和测试
def example_usage():
    """使用示例"""
    
    # 模拟订单簿数据
    mock_orderbook = {
        'bids': [
            [50000.0, 1.5],   # 价格, 数量
            [49990.0, 2.0],
            [49980.0, 1.8],
            [49970.0, 2.5],
            [49960.0, 3.0],
            [49950.0, 2.2],
            [49940.0, 1.9],
            [49930.0, 2.8],
            [49920.0, 2.1],
            [49910.0, 3.5],
        ],
        'asks': [
            [50010.0, 1.2],
            [50020.0, 1.8],
            [50030.0, 2.1],
            [50040.0, 1.5],
            [50050.0, 2.4],
            [50060.0, 1.9],
            [50070.0, 2.2],
            [50080.0, 1.7],
            [50090.0, 2.6],
            [50100.0, 2.0],
        ]
    }
    
    # 初始化管理器
    manager = DepthBasedPositionManager()
    
    print("\n" + "="*80)
    print("基于盘口深度的仓位管理示例".center(80))
    print("="*80 + "\n")
    
    # 测试场景1：正常仓位
    print("📊 场景1：正常仓位（5000 USDT）")
    print("-"*80)
    final_amount, details = manager.calculate_safe_position_size(
        pair="BTC/USDT",
        orderbook=mock_orderbook,
        proposed_amount=5000,
        current_price=50000,
        is_short=False
    )
    print(f"建议金额: 5000 USDT")
    print(f"最终金额: {final_amount:.0f} USDT")
    print(f"决策: {details['decision']} - {details['reason']}")
    print()
    
    # 测试场景2：大仓位
    print("📊 场景2：大仓位（50000 USDT）")
    print("-"*80)
    final_amount, details = manager.calculate_safe_position_size(
        pair="BTC/USDT",
        orderbook=mock_orderbook,
        proposed_amount=50000,
        current_price=50000,
        is_short=False
    )
    print(f"建议金额: 50000 USDT")
    print(f"最终金额: {final_amount:.0f} USDT")
    print(f"调整幅度: {details['adjustment_pct']:.1f}%")
    print(f"决策: {details['decision']} - {details['reason']}")
    print()
    
    # 测试场景3：止损影响分析
    print("📊 场景3：止损影响分析（10000 USDT 仓位）")
    print("-"*80)
    impact = manager.estimate_stop_loss_impact(
        orderbook=mock_orderbook,
        position_size=10000,
        entry_price=50000,
        stop_loss_pct=-0.03,
        is_short=False
    )
    print(f"风险等级: {impact['risk_level']}")
    print(f"风险描述: {impact['risk_description']}")
    print(f"需要档位: {impact['levels_consumed']}")
    print(f"预估滑点: {impact['estimated_slippage']:.2f}%")
    print(f"滑点成本: ${impact['total_slippage_cost']:.2f}")
    print(f"能否完全成交: {'是' if impact['can_exit_completely'] else '否'}")
    print()
    
    print("="*80)


if __name__ == '__main__':
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 运行示例
    example_usage()
