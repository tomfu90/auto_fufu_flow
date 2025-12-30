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
  - 登录失败即跳过后续任务
  - 使用 FastHttpUser
  - 优化40x和50x resp.raise_for_status()  # 4xx/5xx 自动抛异常，标记失败
  - 优化压测机性能：修改默认连接池，默认0 改为300
  - 优化压测机性能：修改@task 失败重试次数，默认2 改为1
  - 优化压测机 的 OSError (49) 端口耗尽：
  ============ =========
    linxu 优化端口
    # 1. 扩大临时端口范围（1024-65535，可用端口数最大化）
    sudo sysctl -w net.ipv4.ip_local_port_range="1024 65535"
    # 2. 允许复用 TIME_WAIT 端口（Linux 核心优化，必开）
    sudo sysctl -w net.ipv4.tcp_tw_reuse=1
    # 3. 缩短 TIME_WAIT 超时（60秒→10秒，1秒太短易出问题）
    sudo sysctl -w net.ipv4.tcp_fin_timeout=10
    mac 优化端口
    # 1. 扩大临时端口范围（Mac 没有 net.ipv4.ip_local_port_range，用这个！）
    sudo sysctl -w net.inet.ip.portrange.first=1024
    sudo sysctl -w net.inet.ip.portrange.last=65535
    # 2. 缩短 TIME_WAIT 超时（MSL=1000毫秒，TIME_WAIT=2×MSL=2秒，回收超快）
    sudo sysctl -w net.inet.tcp.msl=1000
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


# 账号加载，分布式多进程，跟据workerid进行索引偏移分片
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


# 1复用locust原生logger(同步到web ui/终端)
logger = logging.getLogger("locust")
logger.setLevel(logging.INFO)



# 阶梯压测
stages = [
    (TARGET_USERS // 8, 15),
    120,
    (TARGET_USERS // 2, 40),
    120,
    (TARGET_USERS , 40),
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


class UserAllocator:
    def __init__(self):
        self._idx = 0
        self._lock = RLock()


user_allocator = UserAllocator()


class ListingUser(FastHttpUser):
    host = BASE_URL
    wait_time = between(0.5, 1.5)
    max_connections = 100  # 连接池 ，设置100个持久tcp连接，避免端口耗尽
    max_retries = 1 # @task方法 最大重试次数。默认2改为1

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
            resp.raise_for_status()
            # 如果走到这里，说明 resp.status_code 是 2xx（否则 Locust 已抛异常）
            #防御
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                logger.error(f"Empty response body (status: {status})")
                raise Exception(f"Empty response body (status: {status})")
            try:
                json_data = resp.json()
            except Exception as e:
                # 捕获 JSON 解析失败
                error_msg = f"JSON 解析失败 | 账号: {self.account} | 异常: {e}"
                logger.error(error_msg)
                raise Exception(f"{error_msg}")
            self.token = json_data.get("access_token")
            if not self.token:
                error_msg = f"登录成功但无 access_token | 账号: {self.account} | JSON: {json_data}"
                logger.error(error_msg)
                raise Exception(f"{error_msg}")
        except Exception as e:
            # Locust 已自动将此请求标记为失败
            error_msg = f"登录异常 | 账号: {self.account} | 错误: {e}"
            logger.error(error_msg)



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
            resp.raise_for_status()
            #防御
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                logger.error(f"Empty response body (status: {status})")
                raise Exception(f"Empty response body (status: {status})")
            try:
                json_data = resp.json()
            except Exception as e:
                logger.error(f"异常{str(e)}")
                raise Exception(f"{str(e)}")
            listing_id = json_data.get("listing_id")
            if listing_id:
                self.my_listings.append(listing_id)
            else:
                error_msg = f"挂单成功但无 listing_id | 账号: {self.account} | JSON: {json_data}"
                logger.error(error_msg)
                raise Exception(f"{error_msg}")
        except Exception as e:
            error_msg = f"挂单异常 | 账号: {self.account} | 错误: {e}"
            logger.error(error_msg)


    @task(2)
    def query_listing(self):
        if not getattr(self, 'my_listings', None) or not getattr(self, 'token', None):
            return
        listing_id = random.choice(self.my_listings)
        try:
            resp = self.client.post(
                GET_LISTING_URL,
                json={"listing_id": listing_id},
                headers={"Authorization": f"Bearer {self.token}"},
                name="/get_listing",
                timeout=(3, 10)
            )
            resp.raise_for_status()
        except Exception as e:
            error_msg = f"查询挂单异常 | 账号: {self.account} | 挂单ID: {listing_id} | 错误: {e}"
            logger.error(error_msg)


    @task(5)
    def query_amount(self):
        if not getattr(self, 'token', None):
            return
        try:
            resp = self.client.get(
                get_balance_url,
                headers={"Authorization": f"Bearer {self.token}"},
                name="/get_balance_url",
                timeout=(3, 10)
            )
            resp.raise_for_status()
        except Exception as e:
            error_msg = f"查询余额异常 | 账号: {self.account} | 错误: {e}"
            logger.error(error_msg)
