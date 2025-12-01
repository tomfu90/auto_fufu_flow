# coding=utf-8
"""
爆冲压测脚本 - 支持 ECDSA 签名买单（兼容新版 Locust 强制 @task 要求）
三阶段：
  1. 所有用户登录
  2. 卖家挂单（预热）
  3. 买家统一爆冲（高并发瞬时）
要求：
  - export ecdsa_SECRET=your_secret_here
  - registered_accounts.txt 每行一个账号
"""

import os
import json
import logging
import time
import random
from urllib.parse import urlencode
from gevent.event import Event
from gevent.lock import RLock
from gevent import sleep as gevent_sleep
from libs.utils import load_yaml
from libs.signature import ecdsa_signature
from locust import events, FastHttpUser, task, constant

# --- 路径 & 配置 ---
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
config = load_yaml("config/config.yaml")
env = config["env"]
BASE_URL = config["environments"][env]["user"]["base_url"]
LOGIN_URL = config["environments"][env]["user"]["login_url"]
CREATE_LISTING_URL = config["environments"][env]["user"]["create_listing_url"]
PURCHASE_ECDSA_URL_PATH = config["environments"][env]["user"]["create_purchase_order_ecdsa_url"]

PASSWORD = "Abc12345"
ACCOUNT_FILE = os.path.join(project_root, "data", "login", "registered_accounts.txt")
API_SECRET = os.environ.get("ecdsa_SECRET")
if not API_SECRET:
    logging.critical("❌ 环境变量 ecdsa_SECRET 未设置！")
    raise EnvironmentError("Missing ecdsa_SECRET")

# --- 账号加载 ---
with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_ACCOUNTS = [line.strip() for line in f if line.strip()]
MAX_AVAILABLE = len(ALL_ACCOUNTS)
TARGET_USERS = int(os.environ.get("TARGET_USERS", min(100, MAX_AVAILABLE)))
TARGET_USERS = min(TARGET_USERS, MAX_AVAILABLE)

NUM_SELLERS = (TARGET_USERS + 1) // 2
NUM_BUYERS = TARGET_USERS // 2
SELLER_ACCOUNTS = ALL_ACCOUNTS[:NUM_SELLERS]
BUYER_ACCOUNTS = ALL_ACCOUNTS[NUM_SELLERS : NUM_SELLERS + NUM_BUYERS]

logging.info(f"🎯 总用户: {TARGET_USERS} | 卖家: {NUM_SELLERS} | 买家: {NUM_BUYERS}")

# --- 共享状态 ---
class SharedState:
    def __init__(self):
        self.sell_orders = []
        self.lock = RLock()
        self.sellers_done_flag = False      # 👈 状态标志
        self.sellers_done_event = Event()   # 事件辅助
        self._idx = 0

shared_state = SharedState()

# --- 请求统计 ---
request_stats = {
    "start_times": [],
    "end_times": [],
    "success_count": 0,
    "failure_count": 0,
    "failures_detail": [],
}
stats_lock = RLock()

def record_success(start_time, end_time):
    with stats_lock:
        request_stats["start_times"].append(start_time)
        request_stats["end_times"].append(end_time)
        request_stats["success_count"] += 1

def record_failure(account, url, status, error_msg, resp_text=""):
    with stats_lock:
        request_stats["failure_count"] += 1
        request_stats["failures_detail"].append({
            "account": account,
            "url": url,
            "status": status,
            "error": str(error_msg),
            "response": resp_text[:500] if resp_text else ""
        })

# --- 日志配置 ---
log_file = os.path.join(project_root, "logs", "locust_error.log")
logger = logging.getLogger("custom_logger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.FileHandler(log_file, mode='w', encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

# --- Locust User（必须包含 @task）---
class TradingUser(FastHttpUser):
    host = BASE_URL
    # 设置超长等待时间（1小时），确保空 task 几乎不会被执行
    wait_time = constant(3600)

    def on_start(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        with shared_state.lock:
            idx = shared_state._idx
            if idx >= TARGET_USERS:
                return
            shared_state._idx += 1

        if idx < NUM_SELLERS:
            self.role = "seller"
            self.account = SELLER_ACCOUNTS[idx]
        elif idx < NUM_SELLERS + NUM_BUYERS:
            self.role = "buyer"
            self.account = BUYER_ACCOUNTS[idx - NUM_SELLERS]
        else:
            return

        # 登录
        resp = self.client.post(
            LOGIN_URL,
            json={"username": self.account, "password": PASSWORD},
            name="/api/login"
        )
        self.token = ""
        if resp.status_code == 200:
            try:
                if resp.text:
                    data = json.loads(resp.text)
                    self.token = data.get("access_token", "")
            except Exception as e:
                logger.debug(f"[{self.role}] Token 解析异常: {e}")
        if not self.token:
            logger.warning(f"[{self.role}] 未获取 token: {self.account}")
            return

        if self.role == "seller":
            self._sell()
        elif self.role == "buyer":
            self._buy_burst()

    def _sell(self):
        """卖家挂单"""
        resp = self.client.post(
            CREATE_LISTING_URL,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"product_id": "baidu", "amount": 200, "currency": "CNY"},
            name="/create_listing"
        )
        listing_id = ""
        if resp.status_code == 201:
            try:
                if resp.text:
                    data = json.loads(resp.text)
                    listing_id = data.get("listing_id", "")
            except:
                pass

        with shared_state.lock:
            shared_state.sell_orders.append({
                "listing_id": listing_id or "dummy",
                "seller": self.account,
                "amount": 200,
                "is_matched": False
            })

            if len(shared_state.sell_orders) == NUM_SELLERS and not shared_state.sellers_done_flag:
                shared_state.sellers_done_flag = True
                logger.info("🔔 所有卖家挂单完成，触发爆冲信号！")
                shared_state.sellers_done_event.set()

    def _buy_burst(self):
        """买家：安全等待 + 一次性下单"""
        if not shared_state.sellers_done_flag:
            ready = shared_state.sellers_done_event.wait(timeout=60)
            if not ready:
                with shared_state.lock:
                    current = len([o for o in shared_state.sell_orders if o["listing_id"] != "dummy"])
                logger.error(
                    f"💥 买家 {self.account} 等待卖家超时！有效挂单数: {current}/{NUM_SELLERS}"
                )
                return

        gevent_sleep(random.uniform(0.0, 0.05))  # 微扰动

        start_time = time.time()
        target_order = None
        listing_id = ""

        try:
            with shared_state.lock:
                candidates = [
                    o for o in shared_state.sell_orders
                    if o["listing_id"] != "dummy"
                    and o["seller"] != self.account
                    and not o["is_matched"]
                ]
                if not candidates:
                    raise Exception("无可用有效卖单")
                target_order = random.choice(candidates)
                target_order["is_matched"] = True
                listing_id = target_order["listing_id"]

            query_params = {"version": "v1", "page": "1"}
            payload = {"listing_id": listing_id, "purchase_amount": float(target_order["amount"])}
            body_str = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
            full_url = self.host.rstrip("/") + PURCHASE_ECDSA_URL_PATH + "?" + urlencode(query_params, safe='')

            headers = ecdsa_signature(
                api_secret=API_SECRET,
                method="POST",
                path=PURCHASE_ECDSA_URL_PATH,
                query_params=query_params,
                body=body_str,
                timestamp="",
                nonce=""
            )
            headers["Content-Type"] = "application/json"
            headers["Authorization"] = f"Bearer {self.token}"

            resp = self.client.post(
                full_url,
                data=body_str,
                headers=headers,
                name="/api/purchase/create/ecdsa"
            )

            end_time = time.time()
            if resp.status_code == 201:
                record_success(start_time, end_time)
            else:
                resp_text = resp.text if resp else ""
                record_failure(
                    self.account, full_url, resp.status_code,
                    f"HTTP {resp.status_code}", resp_text
                )

        except Exception as e:
            end_time = time.time()
            record_failure(self.account, "N/A", -1, e, "")
            if target_order:
                with shared_state.lock:
                    target_order["is_matched"] = False

    # === 必须存在的空 task（满足新版 Locust 要求）===
    @task(1)
    def do_nothing(self):
        """空任务，权重为1，因 wait_time=3600，几乎不会被执行"""
        pass


# --- 测试结束报告 ---
@events.test_stop.add_listener
def report(environment, **kw):
    with stats_lock:
        total = request_stats["success_count"] + request_stats["failure_count"]
        if total == 0:
            print("📊 无任何请求发出")
            return

        duration = max(request_stats["end_times"]) - min(request_stats["start_times"]) if request_stats["start_times"] else 1.0
        duration = max(duration, 0.001)

        rps = total / duration
        tps = request_stats["success_count"] / duration

        msg = (
            f"\n📊 爆冲测试结束\n"
            f"   总请求: {total}\n"
            f"   成功: {request_stats['success_count']} | 失败: {request_stats['failure_count']}\n"
            f"   测试时长: {duration:.3f}s\n"
            f"   总 RPS: {rps:.2f} req/s\n"
            f"   成功 TPS: {tps:.2f} txn/s\n"
        )
        print(msg)

        if request_stats["failures_detail"]:
            logger.info(f"--- 记录 {len(request_stats['failures_detail'])} 条失败详情 ---")
            for i, fail in enumerate(request_stats["failures_detail"], 1):
                logger.info(
                    f"FAIL #{i}: account={fail['account']}, status={fail['status']}, "
                    f"error={fail['error']}, url={fail['url']}"
                )
            logger.info("--- 失败详情记录结束 ---")