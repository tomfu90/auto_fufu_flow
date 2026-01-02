#!/bin/bash
# 核心配置
TARGET_USERS=3000
total_workers=4

# 仅打印启动的Worker数量
echo "📌 启动配置：TARGET_USERS=$TARGET_USERS | Worker数量=$total_workers"

# 启动Master：传TARGET_USERS，指定IP和5557端口（注意：一行写完或用反斜杠正确换行）
env TARGET_USERS=$TARGET_USERS locust -f load_test/locustfile.py --master --master-host=localhost --master-port=5557 --web-host=0.0.0.0 --web-port=8089 &
MASTER_PID=$!

# 启动Worker：传worker_id和TARGET_USERS，指定Master地址端口
echo "🚀 开始启动 $total_workers 个Worker进程..."
for ((i=0; i<total_workers; i++)); do
    # 关键：env变量和locust命令在同一行，用空格分隔
    env worker_id=$i TARGET_USERS=$TARGET_USERS locust -f load_test/locustfile.py --worker --master-host=localhost --master-port=5557 &
    # 等待1秒，避免Worker同时启动导致端口冲突（可选，但更稳定）
    sleep 1
    echo "  ✅ Worker $i 已启动"
done

# 等待Master结束，清理Worker
wait $MASTER_PID
echo -e "\n🧹 压测结束，清理所有Worker进程..."
# 更精准的清理：只杀当前脚本启动的Worker（避免误杀其他locust进程）
pkill -f "locust -f load_test/locustfile.py --worker" 2>/dev/null
echo "✅ 所有进程已清理完成"