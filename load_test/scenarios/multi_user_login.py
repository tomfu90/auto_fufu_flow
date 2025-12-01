# locustfile.py
# coding =utf-8
# author = fufu
import os,sys,random
import math
import shutil
from queue import Queue, Empty
from locust import FastHttpUser, task, constant, events
from locust.runners import MasterRunner, WorkerRunner
from libs.utils import load_yaml
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.insert(0,project_root)
# --- 路径和配置 ---
config = load_yaml("config/config.yaml")
env = config["env"]
BASE_URL = config["environments"][env]["user"]["base_url"]
LOGIN_URL = config["environments"][env]["user"]["login_url"]
PASSWORD = "Abc12345"

ACCOUNT_FILE = os.path.join(project_root, "data", "login", "registered_accounts.txt")
SHARD_DIR = os.path.join(project_root, "data", "login", "shards")

# # 全局队列（每个进程独立）
# user_queue = None
#
# # === 1. 初始化事件：Master 分片，Worker 加载分片 ===
# @events.init.add_listener
# def on_locust_init(environment, **kwargs):
#     global user_queue
#     user_queue = Queue()
#
#     if isinstance(environment.runner, MasterRunner):
#         # --- Master: 分片账号 ---
#         num_processes = environment.parsed_options.processes or 1
#         print(f"🔧 Master 正在分片：{num_processes} 个进程")
#
#         if os.path.exists(SHARD_DIR):
#             shutil.rmtree(SHARD_DIR)
#         os.makedirs(SHARD_DIR, exist_ok=True)
#
#         if not os.path.exists(ACCOUNT_FILE):
#             raise SystemExit(f"❌ 账号文件不存在: {ACCOUNT_FILE}")
#
#         with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
#             accounts = [line.strip() for line in f if line.strip()]
#         if not accounts:
#             raise SystemExit("❌ 账号文件为空！")
#
#         chunk_size = math.ceil(len(accounts) / num_processes)
#         for i in range(num_processes):
#             shard_path = os.path.join(SHARD_DIR, f"shard_{i}.txt")
#             start = i * chunk_size
#             end = start + chunk_size
#             shard_accounts = accounts[start:end]
#             with open(shard_path, "w", encoding="utf-8") as f:
#                 f.write("\n".join(shard_accounts))
#             print(f"✅ 分片 {i}: {len(shard_accounts)} 个账号")
#
#     elif isinstance(environment.runner, WorkerRunner):
#         # --- Worker: 加载自己的分片 ---
#         worker_index = environment.runner.worker_index
#         shard_file = os.path.join(SHARD_DIR, f"shard_{worker_index}.txt")
#
#         if not os.path.exists(shard_file):
#             print(f"⚠️ Worker {worker_index}: 分片文件不存在！跳过加载。")
#             return
#
#         with open(shard_file, "r", encoding="utf-8") as f:
#             accounts = [line.strip() for line in f if line.strip()]
#
#         for acc in accounts:
#             user_queue.put(acc)
#         print(f"✅ Worker {worker_index} 加载 {user_queue.qsize()} 个账号")
#
#
# # === 2. 用户行为定义 ===
# class LoginOnceUser(FastHttpUser):
#     host = BASE_URL
#     wait_time = constant(0)
#
#     @task
#     def login_once(self):
#         global user_queue
#         try:
#             username = user_queue.get_nowait()
#         except Empty:
#             return
#
#         with self.client.post(
#             LOGIN_URL,
#             json={"username": username, "password": PASSWORD},
#             name="/login",
#             catch_response=True,
#             timeout=0.2,          # ← 关键：极短超时
#         ) as resp:
#             if resp.status_code != 200:
#                 resp.failure(f"HTTP {resp.status_code}")  # 不读 text！


# 使用固定账号池（避免任何 I/O 或锁）

# === 一次性加载所有账号（每个进程独立加载，无锁）===
with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_USERS = [line.strip() for line in f if line.strip()]

if not ALL_USERS:
    raise SystemExit("❌ 账号文件为空！")

class HighRPSUser(FastHttpUser):
    host = BASE_URL  # ← 替换为你的实际地址
    wait_time = constant(0)  # 不等待，立即循环

    def on_start(self):
        # 每个用户随机绑定一个账号（也可每次 task 随机）
        self.username = random.choice(ALL_USERS)



    @task
    def login(self):
        # 极简请求，超时设短（避免卡住）
        data = {"username": self.username, "password": PASSWORD}
        headers = {"Content-Type": "application/json"}
        self.client.post(
            LOGIN_URL,
            name="/login",
            json=data,
            headers=headers,
            timeout=0.1  # 100ms 超时，快速失败
        )