"""
trend_service.py - 趋势数据服务
提供 MACD 趋势计算和 HTTP API 接口
每8小时自动更新一次数据
"""

from flask import Flask, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import ccxt
import pandas as pd
import talib
import logging
from datetime import datetime
from threading import Lock
import os

# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler('trend_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask 应用
app = Flask(__name__)

# 全局配置
EXCHANGE_ID = 'binance'
SYMBOL = 'BTC/USDT'
TIMEFRAME = '1d'
LOOKBACK = 40
UPDATE_INTERVAL_HOURS = 8

# 数据存储（线程安全）
trend_data = {
    'last_update': None,
    'trend': None,
    'macd': None,
    'signal': None,
    'diff': None,
    'timestamp': None,
    'raw_data': None
}
data_lock = Lock()


def calculate_macd_and_trend(df, short=12, long=26, signal=9):
    """计算 MACD，并根据 diff 变化生成趋势信号"""
    df = df.copy()
    df['macd'], df['signal'], df['hist'] = talib.MACD(
        df['close'].astype(float),
        fastperiod=short,
        slowperiod=long,
        signalperiod=signal
    )
    df['diff'] = df['hist']
    df['trend'] = df['diff'].diff().apply(lambda x: 1 if x > 0 else -1)
    return df


def fetch_recent_ohlcv(exchange, symbol=SYMBOL, timeframe=TIMEFRAME, limit=LOOKBACK):
    """拉取最近 limit 根 K 线"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.error(f"获取 OHLCV 数据失败: {e}")
        raise


def update_trend_data():
    """更新趋势数据"""
    global trend_data

    try:
        logger.info(f"开始更新趋势数据 - {SYMBOL}")

        # 创建交易所实例
        exchange = getattr(ccxt, EXCHANGE_ID)()

        # 获取数据
        df = fetch_recent_ohlcv(exchange, limit=LOOKBACK)
        df = calculate_macd_and_trend(df)

        # 获取最新数据
        latest = df.iloc[-1]

        # 更新全局数据（线程安全）
        with data_lock:
            trend_data['last_update'] = datetime.now().isoformat()
            trend_data['trend'] = int(latest['trend'])
            trend_data['macd'] = float(latest['macd'])
            trend_data['signal'] = float(latest['signal'])
            trend_data['diff'] = float(latest['diff'])
            trend_data['timestamp'] = latest['timestamp'].isoformat()
            trend_data['raw_data'] = df.tail(10).to_dict('records')  # 保存最近10条

        logger.info(f"✅ 趋势数据更新成功 - 趋势信号: {trend_data['trend']}")

    except Exception as e:
        logger.error(f"❌ 更新趋势数据失败: {e}")
        import traceback
        traceback.print_exc()


# ==================== API 端点 ====================

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'service': 'trend_service',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/trend', methods=['GET'])
def get_trend():
    """获取当前趋势信号"""
    with data_lock:
        if trend_data['trend'] is None:
            return jsonify({
                'error': 'Data not available yet',
                'message': 'Please wait for the first update'
            }), 503

        return jsonify({
            'trend': trend_data['trend'],
            'macd': trend_data['macd'],
            'signal': trend_data['signal'],
            'diff': trend_data['diff'],
            'timestamp': trend_data['timestamp'],
            'last_update': trend_data['last_update']
        })


@app.route('/api/trend/history', methods=['GET'])
def get_trend_history():
    """获取历史趋势数据"""
    limit = request.args.get('limit', 10, type=int)
    limit = min(limit, 100)  # 最多返回100条

    with data_lock:
        if trend_data['raw_data'] is None:
            return jsonify({
                'error': 'Data not available yet'
            }), 503

        history = trend_data['raw_data'][-limit:]
        return jsonify({
            'data': history,
            'count': len(history),
            'last_update': trend_data['last_update']
        })


@app.route('/api/status', methods=['GET'])
def get_status():
    """获取服务状态"""
    with data_lock:
        return jsonify({
            'service': 'trend_service',
            'exchange': EXCHANGE_ID,
            'symbol': SYMBOL,
            'timeframe': TIMEFRAME,
            'lookback': LOOKBACK,
            'update_interval_hours': UPDATE_INTERVAL_HOURS,
            'last_update': trend_data['last_update'],
            'data_available': trend_data['trend'] is not None,
            'current_trend': trend_data['trend']
        })


@app.route('/api/force-update', methods=['POST'])
def force_update():
    """手动触发更新（需要认证）"""
    # 可以添加简单的认证
    auth_token = request.headers.get('Authorization')
    expected_token = os.getenv('TREND_SERVICE_TOKEN', 'default_secret_token')

    if auth_token != f'Bearer {expected_token}':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        update_trend_data()
        return jsonify({
            'message': 'Update triggered successfully',
            'last_update': trend_data['last_update']
        })
    except Exception as e:
        return jsonify({
            'error': 'Update failed',
            'message': str(e)
        }), 500


# ==================== 定时任务 ====================

def init_scheduler():
    """初始化定时任务"""
    scheduler = BackgroundScheduler()

    # 立即执行一次更新
    update_trend_data()

    # 每8小时更新一次
    scheduler.add_job(
        func=update_trend_data,
        trigger='interval',
        hours=UPDATE_INTERVAL_HOURS,
        id='update_trend',
        name='Update trend data',
        replace_existing=True
    )

    scheduler.start()
    logger.info(f"✅ 定时任务已启动 - 每 {UPDATE_INTERVAL_HOURS} 小时更新一次")

    return scheduler


# ==================== 主程序 ====================

def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("趋势数据服务启动中...")
    logger.info("=" * 50)

    # 初始化定时任务
    scheduler = init_scheduler()

    # 获取配置
    host = os.getenv('TREND_SERVICE_HOST', '0.0.0.0')
    port = int(os.getenv('TREND_SERVICE_PORT', 5000))

    logger.info(f"服务地址: http://{host}:{port}")
    logger.info(f"API 端点:")
    logger.info(f"  - GET  /health              - 健康检查")
    logger.info(f"  - GET  /api/trend           - 获取当前趋势")
    logger.info(f"  - GET  /api/trend/history   - 获取历史数据")
    logger.info(f"  - GET  /api/status          - 获取服务状态")
    logger.info(f"  - POST /api/force-update    - 手动触发更新")
    logger.info("=" * 50)

    try:
        # 启动 Flask 应用
        app.run(host=host, port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
        scheduler.shutdown()
        logger.info("服务已停止")


if __name__ == "__main__":
    main()