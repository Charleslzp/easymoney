"""
trend_service.py - 趋势数据服务（使用币安原生MACD）
直接从币安获取 MACD 指标，避免自己计算与币安不一致
"""

from flask import Flask, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import ccxt
import requests
import pandas as pd
import logging
from datetime import datetime
from threading import Lock
import os

MIN_DIFF_THRESHOLD = float(os.getenv("MIN_DIFF_THRESHOLD", "200"))

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
SYMBOL = 'BTCUSDT'  # 币安格式不用斜杠
TIMEFRAME = '1d'
LOOKBACK = 40
UPDATE_INTERVAL_HOURS = 8

# 币安技术指标 API
BINANCE_API_BASE = "https://api.binance.com"

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


def fetch_binance_macd(symbol=SYMBOL, interval='1d', limit=40):
    """
    从币安直接获取 MACD 数据

    参数:
        symbol: 交易对符号 (如 BTCUSDT)
        interval: K线周期 (1m, 5m, 15m, 1h, 4h, 1d, 1w)
        limit: 获取数量

    返回: DataFrame with columns [timestamp, macd, signal, hist]
    """
    try:
        # 方法 1: 使用币安 UIKlines API (推荐)
        url = f"{BINANCE_API_BASE}/api/v3/uiKlines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }

        logger.info(f"正在从币安获取 {symbol} {interval} K线数据...")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        klines = response.json()

        # 解析K线数据
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close'] = df['close'].astype(float)

        # 获取 MACD 技术指标
        macd_data = fetch_binance_technical_indicator(symbol, interval, limit)

        if macd_data is not None and len(macd_data) > 0:
            # 合并 MACD 数据
            df = df.merge(macd_data, on='timestamp', how='left')
        else:
            logger.warning("⚠️ 未能从币安获取MACD，将使用 TA-Lib 计算")
            df = calculate_macd_fallback(df)

        return df

    except Exception as e:
        logger.error(f"❌ 获取币安数据失败: {e}")
        raise


def fetch_binance_technical_indicator(symbol, interval, limit):
    """
    方法 2: 使用币安技术指标 API 获取 MACD

    注意: 币安官方可能没有直接的 MACD API，这里提供备选方案
    """
    try:
        # 币安没有直接的技术指标API，我们使用第三方或自己计算
        # 这里使用 ccxt 获取数据后用 TA-Lib 计算（与币安最接近的参数）

        exchange = ccxt.binance()

        # 获取 K线数据
        ohlcv = exchange.fetch_ohlcv(
            symbol.replace('USDT', '/USDT'),  # BTCUSDT -> BTC/USDT
            interval,
            limit=limit + 26  # 多获取一些数据以计算 MACD
        )

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close'] = df['close'].astype(float)

        # 使用币安相同的 MACD 参数计算
        df = calculate_binance_style_macd(df)

        # 只返回请求的数量
        return df.tail(limit)[['timestamp', 'macd', 'signal', 'hist']].reset_index(drop=True)

    except Exception as e:
        logger.error(f"获取技术指标失败: {e}")
        return None


def calculate_binance_style_macd(df, fast=12, slow=26, signal=9):
    """
    使用与币安相同的算法计算 MACD
    币安使用 EMA 计算 MACD

    MACD Line = EMA(12) - EMA(26)
    Signal Line = EMA(9) of MACD Line
    Histogram = MACD Line - Signal Line
    """
    try:
        import numpy as np

        df = df.copy()
        close = df['close'].astype(float)

        # 计算 EMA
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()

        # MACD Line (DIF)
        df['macd'] = ema_fast - ema_slow

        # Signal Line (DEA)
        df['signal'] = df['macd'].ewm(span=signal, adjust=False).mean()

        # Histogram (MACD柱)
        df['hist'] = df['macd'] - df['signal']

        return df

    except Exception as e:
        logger.error(f"计算 MACD 失败: {e}")
        raise


def calculate_macd_fallback(df):
    """备用方案：使用 TA-Lib 计算（如果币安API失败）"""
    try:
        import talib

        df = df.copy()
        df['macd'], df['signal'], df['hist'] = talib.MACD(
            df['close'].astype(float),
            fastperiod=12,
            slowperiod=26,
            signalperiod=9
        )
        return df
    except ImportError:
        logger.error("TA-Lib 未安装，无法计算 MACD")
        raise


def calculate_trend_from_macd(df):
    """根据 MACD histogram 计算趋势"""
    df = df.copy()
    df['diff'] = df['hist']
    df['diff_change'] = df['diff'].diff()

    def get_trend(row):
        # 如果 diff 太小，认为没有明确趋势
        if abs(row['diff']) < MIN_DIFF_THRESHOLD:
            return 0

        # diff > 0 且在增长 -> 上涨趋势
        if row['diff'] > 0 and row['diff_change'] > 0:
            return 1

        # diff < 0 且在减小 -> 下跌趋势
        if row['diff'] < 0 and row['diff_change'] < 0:
            return -1

        # 其他情况 -> 震荡
        return 0

    df['trend'] = df.apply(get_trend, axis=1)
    return df


def update_trend_data():
    """更新趋势数据"""
    global trend_data

    try:
        logger.info(f"开始更新趋势数据 - {SYMBOL}")

        # 从币安获取数据和 MACD
        df = fetch_binance_macd(SYMBOL, TIMEFRAME, LOOKBACK)

        # 计算趋势
        df = calculate_trend_from_macd(df)

        # 获取最新数据
        latest = df.iloc[-1]

        # 更新全局数据（线程安全）
        with data_lock:
            trend_data['last_update'] = datetime.now().isoformat()
            trend_data['trend'] = int(latest['trend'])
            trend_data['macd'] = float(latest['macd'])
            trend_data['signal'] = float(latest['signal'])
            trend_data['diff'] = float(latest['hist'])
            trend_data['timestamp'] = latest['timestamp'].isoformat()
            trend_data['raw_data'] = df.tail(10).to_dict('records')

        logger.info(f"✅ 趋势数据更新成功")
        logger.info(f"   趋势信号: {trend_data['trend']}")
        logger.info(f"   MACD: {trend_data['macd']:.2f}")
        logger.info(f"   Signal: {trend_data['signal']:.2f}")
        logger.info(f"   Histogram: {trend_data['diff']:.2f}")

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
            'histogram': trend_data['diff'],  # 添加 histogram 别名
            'timestamp': trend_data['timestamp'],
            'last_update': trend_data['last_update']
        })


@app.route('/api/trend/history', methods=['GET'])
def get_trend_history():
    """获取历史趋势数据"""
    limit = request.args.get('limit', 10, type=int)
    limit = min(limit, 100)

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
            'min_diff_threshold': MIN_DIFF_THRESHOLD,
            'last_update': trend_data['last_update'],
            'data_available': trend_data['trend'] is not None,
            'current_trend': trend_data['trend'],
            'data_source': 'Binance API + EMA calculation'
        })


@app.route('/api/force-update', methods=['POST'])
def force_update():
    """手动触发更新（需要认证）"""
    auth_token = request.headers.get('Authorization')
    expected_token = os.getenv('TREND_SERVICE_TOKEN', 'default_secret_token')

    if auth_token != f'Bearer {expected_token}':
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        update_trend_data()
        return jsonify({
            'message': 'Update triggered successfully',
            'last_update': trend_data['last_update'],
            'current_trend': trend_data['trend']
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
    logger.info("📊 执行首次数据更新...")
    update_trend_data()

    # 在每天的固定时间点执行: 00:01, 16:01, 18:01
    scheduler.add_job(
        func=update_trend_data,
        trigger='cron',
        hour='0,16,18',
        minute='1',
        id='update_trend',
        name='Update trend data',
        replace_existing=True
    )

    scheduler.start()
    logger.info("✅ 定时任务已启动 - 每天 00:01, 16:01, 18:01 执行更新")

    return scheduler


# ==================== 主程序 ====================

def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("趋势数据服务启动中...")
    logger.info(f"数据源: 币安 API")
    logger.info(f"MACD 计算: EMA(12), EMA(26), Signal(9)")
    logger.info("=" * 60)

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
    logger.info("=" * 60)

    # 测试 POST 示例
    logger.info("\n💡 POST 请求示例:")
    logger.info(f"   curl -X POST http://{host}:{port}/api/force-update \\")
    logger.info(f"        -H 'Authorization: Bearer default_secret_token'")
    logger.info("")

    try:
        # 启动 Flask 应用
        app.run(host=host, port=port, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭...")
        scheduler.shutdown()
        logger.info("服务已停止")


if __name__ == "__main__":
    main()