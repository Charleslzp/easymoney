FROM python:3.12-slim AS base
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONFAULTHANDLER=1
ENV PATH=/home/ftuser/.local/bin:$PATH
ENV FT_APP_ENV="docker"

COPY ta-lib_0.6.4_amd64.deb /tmp/

# ⭐ 第一步：安装基础依赖 + CUDA 11 仓库
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libatlas3-base \
    libgomp1 \
    curl \
    sqlite3 \
    sudo \
    wget \
    gnupg2 \
    ca-certificates \
    && dpkg -i /tmp/ta-lib_0.6.4_amd64.deb || true \
    && apt-get install -f -y \
    && rm /tmp/ta-lib_0.6.4_amd64.deb

RUN apt-get update && apt-get install -y jq && apt-get clean


# ⭐ 第二步：添加 NVIDIA CUDA 仓库并安装 CUDA 11.0 运行时（与 mamba-ssm wheel 匹配）
# 注意：cu11 通常指 CUDA 11.x，我们尝试安装多个版本的库
RUN wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb \
    && dpkg -i cuda-keyring_1.1-1_all.deb \
    && rm cuda-keyring_1.1-1_all.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        cuda-cudart-11-0 \
        cuda-cudart-11-8 \
        cuda-compat-11-0 \
        libcublas-11-0 \
        libcublas-11-8 \
        libcusparse-11-0 \
        libcusparse-11-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    || echo "⚠️ 部分 CUDA 包安装失败，继续..."

# ⭐ 第三步：设置 CUDA 环境变量（同时支持 11.0 和 11.8）
ENV LD_LIBRARY_PATH=/usr/local/cuda-11.0/lib64:/usr/local/cuda-11.8/lib64:/usr/local/lib:/usr/lib:$LD_LIBRARY_PATH
ENV C_INCLUDE_PATH=/usr/local/include:/usr/include:$C_INCLUDE_PATH
ENV CUDA_HOME=/usr/local/cuda-11.8
ENV PATH=/usr/local/cuda-11.8/bin:$PATH

# ⭐ 重要：禁用 CUDA 设备（强制 CPU 推理，但保留 CUDA 库）
ENV CUDA_VISIBLE_DEVICES=""

RUN mkdir /freqtrade \
  && useradd -u 1000 -G sudo -U -m -s /bin/bash ftuser \
  && chown ftuser:ftuser /freqtrade \
  && echo "ftuser ALL=(ALL) NOPASSWD: /bin/chown" >> /etc/sudoers

WORKDIR /freqtrade

# ===== Python 依赖阶段 =====
FROM base AS python-deps
RUN apt-get update \
  && apt-get -y install build-essential libssl-dev git libffi-dev libgfortran5 pkg-config cmake gcc \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --upgrade pip wheel

COPY --chown=ftuser:ftuser requirements.txt requirements-hyperopt.txt /freqtrade/
USER ftuser

# ⭐ 分步安装依赖
# 使用 NumPy 2.x（Freqtrade 需要）
RUN pip install --user --no-cache-dir "numpy>=2.0,<3.0"

# ⭐ 安装 PyTorch 2.2（与 mamba-ssm wheel 匹配）
RUN pip install --user --no-cache-dir \
    torch==2.2.0 \
    torchvision==0.17.0 \
    torchaudio==2.2.0 \
    --index-url https://download.pytorch.org/whl/cu118 && \
    echo "✅ PyTorch 2.2.0 安装成功" || echo "⚠️ PyTorch 安装失败，继续..."

# ⭐ 安装 triton（PyTorch 的依赖）
RUN pip install --user --no-cache-dir triton==2.2.0 || echo "⚠️ triton 安装失败，继续..."
RUN pip install --user --no-cache-dir einops
RUN pip install --user --no-cache-dir huggingface-hub packaging filelock tqdm safetensors transformers
# 安装 TA-Lib
RUN pip install --user --no-cache-dir TA-Lib==0.6.4

# 安装 hyperopt 依赖
RUN pip install --user --no-cache-dir -r requirements-hyperopt.txt

# ⭐ 关键：设置 NumPy 兼容模式环境变量
ENV NPY_PROMOTION_STATE=weak

# ⭐ 安装 mamba-ssm（即使 NumPy 2.x，也强制安装）
COPY /mamba_ssm_cpu-2.2.5-py3-none-any.whl /tmp/
RUN pip install --user --no-cache-dir --no-deps /tmp/mamba_ssm_cpu-2.2.5-py3-none-any.whl && \
    echo "✅ mamba-ssm 2.2.4 安装成功（强制，忽略 NumPy 版本）" || \
    echo "⚠️ mamba-ssm 安装失败"

# ===== 运行时镜像 =====
FROM base AS runtime-image
COPY --from=python-deps --chown=ftuser:ftuser /home/ftuser/.local /home/ftuser/.local

USER ftuser

# 创建策略目录
RUN mkdir -p /freqtrade/user_data/strategies/

# 先复制策略文件
COPY --chown=ftuser:ftuser MyStrategy.py /freqtrade/user_data/strategies/
COPY --chown=ftuser:ftuser best_long.pth /freqtrade/user_data/strategies/
COPY --chown=ftuser:ftuser best_short.pth /freqtrade/user_data/strategies/
COPY --chown=ftuser:ftuser __init__.py /freqtrade/user_data/strategies/
COPY --chown=ftuser:ftuser record.py /freqtrade/user_data/strategies/
COPY --chown=ftuser:ftuser trend_client.py /freqtrade/user_data/strategies/
# 然后复制其他文件
COPY --chown=ftuser:ftuser . /freqtrade/

# 安装 freqtrade
RUN pip install -e . --user --no-cache-dir --no-build-isolation

# 安装 easymoney
COPY easymoney-0.1.0-py3-none-any.whl /freqtrade/
RUN pip install --user --no-cache-dir /freqtrade/easymoney-0.1.0-py3-none-any.whl

# ⭐ 最后检查并锁定 NumPy 版本（如果被升级了）
RUN pip list | grep -i numpy && \
    (pip show numpy | grep "Version: 2" && pip install --user --force-reinstall "numpy>=1.26,<2.0" || echo "✅ NumPy 1.x")

# ⭐ 验证 CUDA 库和安装
RUN echo "=== 验证 CUDA 库 ===" \
  && ls -la /usr/local/cuda-*/lib64/libcudart.so* 2>/dev/null || echo "⚠️ CUDA 库路径检查" \
  && find /usr -name "libcudart.so*" 2>/dev/null || echo "⚠️ 搜索 CUDA 库" \
  && echo "=== 验证 Python 包 ===" \
  && pip show numpy freqtrade mamba-ssm torch || true \
  && python -c "import numpy; import sys; print(f'✅ Python: {sys.version.split()[0]}, NumPy: {numpy.__version__}')" || true \
  && python -c "import torch; print(f'✅ PyTorch: {torch.__version__}, CUDA: {torch.version.cuda}')" || true \
  && python -c "import freqtrade; print(f'✅ Freqtrade installed')" || true \
  && python -c "import easymoney; print(f'✅ Easymoney installed')" || true \
  && python -c "try:\n    import mamba_ssm\n    print(f'✅ mamba-ssm installed')\nexcept Exception as e:\n    print(f'⚠️ mamba-ssm error: {e}')" || true

# 验证策略文件
RUN echo "=== 验证策略文件 ===" \
  && ls -la /freqtrade/user_data/strategies/ || true \
  && python3 -c "import sys; sys.path.insert(0, '/freqtrade/user_data/strategies'); import MyStrategy; print('✅ 策略验证成功')" || echo "⚠️ 策略验证失败，但继续..."

ENTRYPOINT ["freqtrade"]
CMD ["trade"]
