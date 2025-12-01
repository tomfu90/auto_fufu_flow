# coding=utf-8
# author = fufu
"""
压测方式：
 - 压测典型场景： 不区分角色阶梯压测，无撮合逻辑 by_fufu
 - 压测e2e场景：不区分角色阶梯压测：登陆后，发布挂单--查询挂单详情--查询余额
 - 上下文关联：发布挂单后，无不会对挂单进行操作，登陆账号不区分角色
 - 分布式压测（master-worker压测模式）
 - 方案：总账号文件列表 按workerid进行切片索引：起始为0，按workerid进行偏移

行为：
  - 挂单：中频
  - 查询挂单：中频 仅卖家查自己挂的单；买家不发查询请求
  - 查询余额：中频

优化：
  - 移除 catch_response=True
  - 移除 safe_json 补丁
  - 登录失败即跳过后续任务
  - 日志节流（每类错误最多每50次记录一次）
  - 使用 FastHttpUser
"""

import os
import time
import logging
import random
import traceback
from gevent.lock import RLock
from locust import events, FastHttpUser, task, between
import gevent
from libs.utils import load_yaml
from locust.runners import MasterRunner, LocalRunner
from json import JSONDecodeError
from collections import defaultdict


# ====== 全局配置 ======
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
config = load_yaml("config/config.yaml")
env = config["env"]
BASE_URL = config["environments"][env]["user"]["base_url"]
LOGIN_URL = config["environments"][env]["user"]["login_url"]
CREATE_LISTING_URL = config["environments"][env]["user"]["create_listing_url"]
GET_LISTING_URL = config["environments"][env]["user"]["get_listing_url"]
get_balance_url = config["environments"][env]["user"]["get_balance_url"]
PASSWORD = "Abc12345"

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Locust压测")

# 账号加载
ACCOUNT_FILE = os.path.join(project_root, "data", "login", "registered_accounts.txt")
with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_ACCOUNTS = [line.strip() for line in f if line.strip()]

MAX_AVAILABLE = len(ALL_ACCOUNTS)
TARGET_USERS = int(os.environ.get("TARGET_USERS"))
TARGET_USERS = min(TARGET_USERS, MAX_AVAILABLE)

total_workers = int(os.environ.get("total_workers", 1))
worker_id = int(os.environ.get("worker_id", 0))

if len(ALL_ACCOUNTS) < TARGET_USERS:
    raise ValueError(f"❌ 账号不足：需要 {TARGET_USERS}，实际只有 {len(ALL_ACCOUNTS)}")

accounts_per_worker = TARGET_USERS // total_workers
remainder = TARGET_USERS % total_workers
start_idx = worker_id * accounts_per_worker + min(worker_id, remainder)
end_idx = start_idx + accounts_per_worker + (1 if worker_id < remainder else 0)
my_accounts = ALL_ACCOUNTS[start_idx:end_idx]

# 阶梯压测
stages = [
    (TARGET_USERS // 8, 15),
    120,
    (TARGET_USERS // 2, 40),
    120,
]

@events.init.add_listener
def on_locust_init(environment, **kwargs):
    if not isinstance(environment.runner, (MasterRunner, LocalRunner)):
        return

    def run_stages():
        current_users = 0
        for stage in stages:
            if isinstance(stage, tuple):
                target, spawn_sec = stage
                spawn_rate = max(1, (target - current_users) / spawn_sec)
                logger.info(f"🚀【加压】{current_users} → {target} 用户 | 速率: {spawn_rate:.1f}/秒")
                environment.runner.start(user_count=target, spawn_rate=spawn_rate)
                gevent.sleep(spawn_sec)
                current_users = target
            else:
                logger.info(f"⏸️【稳态】保持 {current_users} 用户 | 持续 {stage} 秒")
                gevent.sleep(stage)
        logger.info("⏹️【结束】所有阶段完成，自动停止压测")
        environment.runner.quit()

    gevent.spawn(run_stages)


# ====== 日志节流工具 ======
def log_failure(log_type, msg, interval=50):
    if not hasattr(log_failure, "counters"):
        log_failure.counters = defaultdict(int)
    log_failure.counters[log_type] += 1
    if log_failure.counters[log_type] == 1 or log_failure.counters[log_type] % interval == 0:
        logger.error(msg)


class UserAllocator:
    def __init__(self):
        self._idx = 0
        self._lock = RLock()


user_allocator = UserAllocator()


class ListingUser(FastHttpUser):
    host = BASE_URL
    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.account = None
        self.token = ""
        self.my_listings = []

        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        if not my_accounts:
            logger.error("❌ 当前 worker 未分配到任何账号！")
            return

        with user_allocator._lock:
            current_idx = user_allocator._idx
            if current_idx >= len(my_accounts):
                return
            user_allocator._idx += 1
            self.account = my_accounts[current_idx]

        try:
            resp = self.client.post(
                LOGIN_URL,
                json={"username": self.account, "password": PASSWORD},
                name="/api/login",
                timeout=(3, 10)
            )
            # 如果走到这里，说明 resp.status_code 是 2xx（否则 Locust 已抛异常）
            #防御
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                raise ValueError(f"Empty response body (status: {status})")
            json_data = resp.json()
            self.token = json_data.get("access_token")
            if not self.token:
                error_msg = f"登录成功但无 access_token | 账号: {self.account} | JSON: {json_data}"
                log_failure("login_no_token", error_msg)
                # 注意：HTTP 成功，但业务失败 → 我们无法让 Locust 标记为“请求失败”
                # 所以只记录日志，后续任务因无 token 跳过
        except Exception as e:
            # Locust 已自动将此请求标记为失败
            error_msg = f"登录异常 | 账号: {self.account} | 错误: {e}"
            log_failure("login_exception", error_msg)
            # 不设置 self.token，后续任务自动跳过

    @task(10)
    def create_listing(self):
        if not getattr(self, 'token', None):
            return
        try:
            resp = self.client.post(
                CREATE_LISTING_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"product_id": "baidu", "amount": 200, "currency": "CNY"},
                name="/create_listing",
                timeout=(3, 10)
            )
            #防御
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                raise ValueError(f"Empty response body (status: {status})")
            # HTTP 成功（201）
            json_data = resp.json()
            listing_id = json_data.get("listing_id")
            if listing_id:
                self.my_listings.append(listing_id)
            else:
                error_msg = f"挂单成功但无 listing_id | 账号: {self.account} | JSON: {json_data}"
                log_failure("listing_no_id", error_msg)
        except Exception as e:
            # 包括：5xx、4xx、超时、JSON 解析失败等
            # Locust 已自动标记为失败
            error_msg = f"挂单异常 | 账号: {self.account} | 错误: {e}"
            log_failure("listing_exception", error_msg)

    @task(2)
    def query_listing(self):
        if not getattr(self, 'my_listings', None) or not getattr(self, 'token', None):
            return
        listing_id = random.choice(self.my_listings)
        try:
            self.client.post(
                GET_LISTING_URL,
                json={"listing_id": listing_id},
                headers={"Authorization": f"Bearer {self.token}"},
                name="/get_listing",
                timeout=(3, 10)
            )
        except Exception as e:
            error_msg = f"查询挂单异常 | 账号: {self.account} | 挂单ID: {listing_id} | 错误: {e}"
            log_failure("query_listing_exception", error_msg)

    @task(5)
    def query_amount(self):
        if not getattr(self, 'token', None):
            return
        try:
            self.client.get(
                get_balance_url,
                headers={"Authorization": f"Bearer {self.token}"},
                name="/get_balance_url",
                timeout=(3, 10)
            )
        except Exception as e:
            error_msg = f"查询余额异常 | 账号: {self.account} | 错误: {e}"
            log_failure("query_balance_exception", error_msg)