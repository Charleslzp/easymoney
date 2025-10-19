#!/bin/bash

echo "========================================="
echo "  Docker Swarm + Portainer 安装配置"
echo "========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为root或有sudo权限
if [ "$EUID" -eq 0 ]; then 
    echo -e "${YELLOW}⚠ 检测到root用户，建议使用普通用户运行${NC}"
fi

# 1. 检查Docker
echo "步骤 1/5: 检查Docker安装..."
if command -v docker &> /dev/null; then
    docker_version=$(docker --version)
    echo -e "${GREEN}✓${NC} $docker_version"
else
    echo -e "${RED}✗${NC} Docker未安装"
    echo ""
    read -p "是否立即安装Docker？(y/n): " install_docker
    if [ "$install_docker" = "y" ]; then
        echo "正在安装Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
        echo -e "${GREEN}✓${NC} Docker安装完成"
        echo -e "${YELLOW}⚠ 请注销并重新登录以使Docker组权限生效${NC}"
        echo ""
        read -p "是否继续配置？(y/n): " continue_setup
        if [ "$continue_setup" != "y" ]; then
            exit 0
        fi
    else
        echo "请先安装Docker后再运行此脚本"
        exit 1
    fi
fi

# 2. 初始化Docker Swarm
echo ""
echo "步骤 2/5: 初始化Docker Swarm..."
if docker info 2>/dev/null | grep -q "Swarm: active"; then
    echo -e "${GREEN}✓${NC} Swarm已经初始化"
else
    echo "正在初始化Swarm..."
    docker swarm init
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Swarm初始化成功"
    else
        echo -e "${RED}✗${NC} Swarm初始化失败"
        exit 1
    fi
fi

# 3. 创建Portainer数据卷
echo ""
echo "步骤 3/5: 创建Portainer数据卷..."
if docker volume ls | grep -q "portainer_data"; then
    echo -e "${GREEN}✓${NC} Portainer数据卷已存在"
else
    docker volume create portainer_data
    echo -e "${GREEN}✓${NC} Portainer数据卷创建成功"
fi

# 4. 部署Portainer
echo ""
echo "步骤 4/5: 部署Portainer..."
if docker service ls | grep -q "portainer"; then
    echo -e "${GREEN}✓${NC} Portainer服务已存在"
    echo ""
    read -p "是否重新部署Portainer？(y/n): " redeploy
    if [ "$redeploy" = "y" ]; then
        echo "正在删除旧服务..."
        docker service rm portainer
        sleep 2
    else
        echo "跳过Portainer部署"
    fi
fi

if ! docker service ls | grep -q "portainer"; then
    echo "正在部署Portainer..."
    docker service create \
        --name portainer \
        --publish published=9000,target=9000 \
        --publish published=8000,target=8000 \
        --replicas=1 \
        --constraint 'node.role == manager' \
        --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock \
        --mount type=volume,src=portainer_data,dst=/data \
        portainer/portainer-ce:latest
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Portainer部署成功"
        echo ""
        echo "Portainer访问地址："
        echo "  http://localhost:9000"
        echo "  http://$(hostname -I | awk '{print $1}'):9000"
        echo ""
        echo -e "${YELLOW}⚠ 首次访问需要设置管理员密码${NC}"
    else
        echo -e "${RED}✗${NC} Portainer部署失败"
        exit 1
    fi
fi

# 5. 创建Freqtrade网络
echo ""
echo "步骤 5/5: 创建Docker网络..."
if docker network ls | grep -q "freqtrade_network"; then
    echo -e "${GREEN}✓${NC} freqtrade_network已存在"
else
    docker network create --driver overlay freqtrade_network
    echo -e "${GREEN}✓${NC} freqtrade_network创建成功"
fi

# 显示Swarm信息
echo ""
echo "========================================="
echo "  配置完成"
echo "========================================="
echo ""
echo "Swarm信息："
docker node ls
echo ""
echo "服务列表："
docker service ls
echo ""
echo "========================================="
echo ""
echo -e "${GREEN}✓${NC} Docker Swarm + Portainer 配置完成！"
echo ""
echo "下一步操作："
echo "1. 访问 Portainer：http://localhost:9000"
echo "2. 设置管理员账户（首次访问）"
echo "3. 运行 ./start.sh 启动Telegram机器人"
echo ""
echo "Portainer默认账户建议："
echo "  用户名: admin"
echo "  密码: 至少12个字符（首次设置）"
echo ""
echo "========================================="
