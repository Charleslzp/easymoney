# ============================================
# 基于官方镜像的 Dockerfile (无需源码)
# ============================================

FROM freqtradeorg/freqtrade:stable

USER root
WORKDIR /freqtrade

# ============================================
# 安装系统依赖
# ============================================
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ============================================
# 安装 ta-lib
# ============================================
COPY ta-lib_0.6.4_amd64.deb /tmp/
RUN dpkg -i /tmp/ta-lib_0.6.4_amd64.deb || \
    (apt-get update && apt-get install -f -y && rm -rf /var/lib/apt/lists/*) && \
    rm /tmp/ta-lib_0.6.4_amd64.deb

# ============================================
# 安装自定义 Python 包
# ============================================
COPY easymoney-0.1.0-py3-none-any.whl /tmp/
COPY mamba_ssm_cpu-2.2.5-py3-none-any.whl /tmp/

RUN pip install --no-cache-dir \
    /tmp/easymoney-0.1.0-py3-none-any.whl \
    /tmp/mamba_ssm_cpu-2.2.5-py3-none-any.whl && \
    rm /tmp/*.whl

# ============================================
# 复制策略和配置文件
# ============================================
COPY MyStrategy.py /freqtrade/user_data/strategies/
COPY config.json /freqtrade/user_data/
COPY record.py /freqtrade/user_data/
COPY trend_client.py /freqtrade/user_data/
COPY __init__.py /freqtrade/user_data/

# ============================================
# 复制模型文件
# ============================================
RUN mkdir -p /freqtrade/models
COPY best_long.pth /freqtrade/models/
COPY best_short.pth /freqtrade/models/

# ============================================
# 设置权限
# ============================================
RUN chown -R ftuser:ftuser /freqtrade

USER ftuser

# ============================================
# 官方镜像已经设置了 ENTRYPOINT
# 默认会执行: freqtrade trade --config user_data/config.json
# ============================================
