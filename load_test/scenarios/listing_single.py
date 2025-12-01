# coding = utf-8
import os
import logging
from gevent.event import Event
from gevent.lock import RLock
from locust import FastHttpUser, task, events,constant

# === 路径与配置加载 ===
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import sys
sys.path.insert(0, project_root)
from libs.utils import load_yaml

config = load_yaml("config/config.yaml")
env = config["env"]
BASE_URL = config["environments"][env]["user"]["base_url"]
LOGIN_URL = config["environments"][env]["user"]["login_url"]
CREATE_LISTING_URL = config["environments"][env]["user"]["create_listing_url"]
PASSWORD = "Abc12345"

ACCOUNT_FILE = os.path.join(project_root, "data", "login", "registered_accounts.txt")

# === 日志设置 ===
log_file = os.path.join(project_root, "logs", "locust_burst.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# === 账号加载与目标用户数 ===
with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_ACCOUNTS = [line.strip() for line in f if line.strip()]

TARGET_USERS = int(os.environ.get("TARGET_USERS", min(100, len(ALL_ACCOUNTS))))
ACCOUNTS = ALL_ACCOUNTS[:TARGET_USERS]  # 精确截断

logging.warning(f"🎯 Target user count set to: {TARGET_USERS} (available accounts: {len(ALL_ACCOUNTS)})")

# === 全局状态（gevent-safe）===
burst_event = Event()
account_index = 0
index_lock = RLock()

# === 用户类 ===
class BurstUser(FastHttpUser):
    host = BASE_URL
    # 防止用户执行完后重启（关键！）
    wait_time = constant(3600)  # ⏳ 关键！防止 task 循环 # 1小时，实际不会等待这么久

    def on_start(self):
        # 防止同一个用户实例多次初始化（虽然通常不会，但保险）
        if hasattr(self, '_has_run'):
            return
        self._has_run = True

        global account_index

        # 安全分配唯一账号索引
        with index_lock:
            idx = account_index
            if idx >= len(ACCOUNTS):
                return  # 超出目标数，安静退出
            account_index += 1
            username = ACCOUNTS[idx]

        # === 登录 ===
        resp = self.client.post(
            LOGIN_URL,
            json={"username": username, "password": PASSWORD},
            name="/api/login"
        )
        if resp.status_code != 200:
            logging.warning(f"Login failed for {username}: HTTP {resp.status_code}")
            return

        try:
            token = resp.json()["access_token"]
        except Exception as e:
            logging.warning(f"Failed to extract token for {username}: {e}")
            return

        # === 触发爆冲信号（仅最后一个用户）===
        if idx == len(ACCOUNTS) - 1:
            logging.info(f"✅ All {len(ACCOUNTS)} users logged in. Triggering burst!")
            burst_event.set()

        # === 等待所有用户就绪 ===
        burst_event.wait(timeout=30)
        if not burst_event.is_set():
            logging.warning(f"{username} timed out waiting for burst signal")
            return

        # === 执行并发请求 ===
        self.client.post(
            CREATE_LISTING_URL,
            json={"product_id": "baidu", "amount": 200, "currency": "CNY"},
            headers={"Authorization": f"Bearer {token}"},
            name="/create_listing"
        )

    @task
    def do_nothing(self):
        # 不会执行，因为 wait_time 很长且 on_start 已完成工作
        pass


# === 请求成功计数 ===
_success_count = 0

@events.request.add_listener
def count_success(name, exception,response, **kw):
    global _success_count
    if name == "/create_listing" and exception is None and response.status_code == 201:
        _success_count += 1

# === 测试结束报告 ===
@events.test_stop.add_listener
def report_result(environment, **kw):
    logging.info(f"🎯 Burst test completed. Successful /create_listing calls: {_success_count} / Target: {len(ACCOUNTS)}")