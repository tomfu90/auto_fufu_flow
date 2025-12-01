#!/bin/bash

# 配置参数
export TARGET_USERS=3000
export total_workers=4

echo "🎯 TARGET_USERS=$TARGET_USERS, total_workers=$total_workers"

# 启动 Master
echo "🚀 启动 Locust Master..."
locust -f load_test/locustfile.py --master --web-host=0.0.0.0 &
MASTER_PID=$!

# 启动 Workers
echo "👷 启动 $total_workers 个 Workers..."
worker_pids=()  # 创建空数组存储 PID

for ((i=0; i<total_workers; i++)); do
    env worker_id=$i locust -f load_test/locustfile.py --worker &
    worker_pids+=($!)  # 将最新后台进程 PID 加入数组
done

# 等待 Master 结束（例如压测完成或 Ctrl+C）
wait $MASTER_PID

# 清理所有 Workers
echo "🧹 清理所有 Worker 进程 (${#worker_pids[@]} 个)..."
for pid in "${worker_pids[@]}"; do
    kill "$pid" 2>/dev/null
done

# 可选：等待所有 Worker 退出（避免僵尸进程）
for pid in "${worker_pids[@]}"; do
    wait "$pid" 2>/dev/null
done

echo "✅ 所有进程已退出。"