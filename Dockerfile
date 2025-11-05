# ========================================
# EasyMoney Freqtrade Docker Image
# 基于官方 freqtrade 镜像
# ========================================

FROM freqtradeorg/freqtrade:stable

USER root

# ========== 安装系统依赖 ==========
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ========== 安装 TA-Lib ==========
COPY ta-lib_0.6.4_amd64.deb /tmp/
RUN dpkg -i /tmp/ta-lib_0.6.4_amd64.deb || \
    (apt-get update && apt-get install -f -y && dpkg -i /tmp/ta-lib_0.6.4_amd64.deb) && \
    rm /tmp/ta-lib_0.6.4_amd64.deb

# ========== 安装自定义 Python 包 ==========
COPY mamba_ssm_cpu-2.2.5-py3-none-any.whl /tmp/
COPY easymoney-0.1.0-py3-none-any.whl /tmp/

RUN pip install --no-cache-dir \
    /tmp/mamba_ssm_cpu-2.2.5-py3-none-any.whl \
    /tmp/easymoney-0.1.0-py3-none-any.whl \
    && rm /tmp/*.whl

# 安装其他依赖
RUN pip install --no-cache-dir \
    pandas-ta==0.3.14b \
    scikit-learn==1.3.2 \
    torch --index-url https://download.pytorch.org/whl/cpu \
    ta-lib \
    requests \
    websocket-client

# ========== 创建目录结构 ==========
RUN mkdir -p /freqtrade/user_data/strategies \
             /freqtrade/user_data/models \
             /freqtrade/user_data/config \
             /freqtrade/user_data/logs

# ========== 复制策略文件 ==========
COPY MyStrategy.py /freqtrade/user_data/strategies/
COPY trend_client.py /freqtrade/user_data/strategies/
COPY record.py /freqtrade/user_data/strategies/
COPY DepthBasedPositionManager.py /freqtrade/user_data/strategies/
COPY __init__.py /freqtrade/user_data/strategies/

# ========== 复制模型文件 ==========
COPY best_long.pth /freqtrade/user_data/models/
COPY best_short.pth /freqtrade/user_data/models/

# ========== 设置权限 ==========
RUN chown -R ftuser:ftuser /freqtrade/user_data

# ========== 切换用户 ==========
USER ftuser

WORKDIR /freqtrade

# ========== 健康检查 ==========
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD freqtrade ping || exit 1

# ========== 入口点 ==========
ENTRYPOINT ["freqtrade"]
CMD ["trade", "--config", "/freqtrade/user_data/config/config.json", "--strategy", "MyStrategy"]
