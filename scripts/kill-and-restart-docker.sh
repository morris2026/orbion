#!/bin/bash
# 清理 Docker 残留进程并重启 Docker 服务（WSL2 环境）
set -e

echo "=== 步骤1: 停止所有 Docker 容器 ==="
docker stop $(docker ps -q) 2>/dev/null || echo "无运行容器"

echo "=== 步骤2: 杀死所有 Docker 相关进程 ==="
# 先杀PID文件里记录的daemon进程，再按进程名杀
for pidfile in /var/run/docker.pid /run/docker.pid /run/docker/containerd/containerd.pid /var/run/containerd.pid; do
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile")
        echo "  从 $pidfile 读取 PID=$pid，kill -9"
        kill -9 "$pid" 2>/dev/null || true
    fi
done
pkill -9 dockerd 2>/dev/null || true
pkill -9 containerd 2>/dev/null || true
pkill -9 containerd-shim 2>/dev/null || true
pkill -9 docker-proxy 2>/dev/null || true
sleep 1

echo "=== 步骤3: 清理残留 PID 文件 ==="
rm -f /var/run/docker.pid /run/docker.pid /var/run/containerd.pid /run/docker/containerd/containerd.pid 2>/dev/null || true

echo "=== 步骤4: 重置失败状态并启动 Docker 服务 ==="
sudo systemctl reset-failed docker.service 2>/dev/null || true
sudo service docker restart

echo "=== 步骤5: 等待 Docker 就绪 ==="
for i in $(seq 1 10); do
    if docker info >/dev/null 2>&1; then
        echo "Docker 已就绪！"
        docker ps
        exit 0
    fi
    echo "等待 Docker 启动... ($i/10)"
    sleep 2
done

echo "Docker 启动失败，请手动检查"
exit 1