# coding = utf-8
# author = fufu

"""
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


import json
import os
import logging
import time
import gevent
import random
from gevent.lock import RLock
from locust import FastHttpUser, task, events,constant
from locust.runners import MasterRunner, LocalRunner
from libs.signature import ecdsa_signature
from urllib.parse import urlencode

# === 路径与配置加载 ===
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from libs.utils import load_yaml

config = load_yaml("config/config.yaml")
env = config["env"]
BASE_URL = config["environments"][env]["user"]["base_url"]
LOGIN_URL = config["environments"][env]["user"]["login_url"]
PURCHASE_ECDSA_URL_PATH = config["environments"][env]["user"]["create_purchase_order_ecdsa_url"]
PASSWORD = "Abc12345"
ACCOUNT_FILE = os.path.join(project_root, "data", "login", "registered_accounts.txt")
listing_file = os.path.join(project_root, "data", "order", "listing.txt")
#日志
logger = logging.getLogger("locust")
logger.setLevel(logging.INFO)

# === 账号加载与目标用户数 ===
with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_ACCOUNTS = [line.strip() for line in f if line.strip()]

with open(listing_file, "r", encoding="utf-8") as f:
    ALL_listing = [line.strip() for line in f if line.strip()]

# 读取环境变量，实际设置用户
MAX_AVAILABLE = len(ALL_ACCOUNTS)
TARGET_USERS = int(os.environ.get("TARGET_USERS"))
TARGET_USERS = min(TARGET_USERS, MAX_AVAILABLE)
#-----‼️按worker对账号进行分片--！！！！
total_workers = int(os.environ.get("total_workers",1)) #获取总进程数
worker_id = int(os.environ.get("worker_id",0))        #获取当前进程id

#读取环境变量-秘钥
API_SECRET = os.environ.get("ecdsa_SECRET")
if not API_SECRET:
    logging.critical("❌ 环境变量 ecdsa_SECRET 未设置！")
    raise EnvironmentError("Missing ecdsa_SECRET")

#安全校验
if len(ALL_ACCOUNTS) < TARGET_USERS:
    raise ValueError(f"❌ 账号不足：需要 {TARGET_USERS}，实际只有 {len(ALL_ACCOUNTS)}")
# 起始索引为0，便宜由work_id决定
accounts_per_worker = TARGET_USERS // total_workers #整除
remainder = TARGET_USERS % total_workers            #余数
# 前remainder进程多1个账号
start_idx = worker_id * accounts_per_worker + min(worker_id, remainder)
end_idx = start_idx + accounts_per_worker + (1 if worker_id<remainder else 0)
my_accounts = ALL_ACCOUNTS[start_idx:end_idx]
#依赖数据偏移
my_listings = ALL_listing[start_idx:end_idx]
logging.warning(f"🎯 Target user count set to: {TARGET_USERS} (available accounts: {len(ALL_ACCOUNTS)})")

# --- 用户分配器 ---
class UserAllocator:
    def __init__(self):
        self._idx = 0
        self._lock = RLock()
#实例化分配器
user_allocator = UserAllocator()

# --- 数据分配器 ---
data_lock= RLock()


#  1. 定义全局时间变量，初始为None
GLOBAL_BASE_TIME = None
GLOBAL_TASK_START = None
GLOBAL_TASK_RUN = None
PRE_WAIT = 15
RUN_TIME = 10
# 2. 压测启动时的钩子：初始化全局时间（点击Start swarming后才执行）
@events.test_start.add_listener
def init_global_time(environment, **kwargs):
    # 1. 初始化全局时间（原有逻辑不变）
    global GLOBAL_BASE_TIME, GLOBAL_TASK_START, GLOBAL_TASK_RUN
    GLOBAL_BASE_TIME = time.time()
    GLOBAL_TASK_START = GLOBAL_BASE_TIME + PRE_WAIT
    GLOBAL_TASK_RUN = GLOBAL_TASK_START + RUN_TIME
    logging.info(f"📌 压测启动，全局时间基准初始化：预热至 {GLOBAL_TASK_START}，运行至 {GLOBAL_TASK_RUN}")
    # # 核心优化：分布式 → 仅Master执行；单机 → 直接执行
    # if isinstance(environment.runner, (LocalRunner, MasterRunner)):
    #     # 2. 核心一行：Master/单机都能触发全局停止，自动适配部署模式
    #     #environment.runner._event_loop.call_later(PRE_WAIT + RUN_TIME, environment.runner.quit)
    #     gevent.spawn_later(PRE_WAIT + RUN_TIME, environment.runner.quit)
# === 用户类 ===
class BurstUser(FastHttpUser):
    host = BASE_URL
    # 防止用户执行完后重启（关键！）
    wait_time = constant(0)  # ⏳尖峰测试
    max_retries = 0 # @task方法 尖峰测试不重试

    def on_start(self):
        self.token = ""
        self.my_listings = []  # 记录自己的挂单
        # 防止同一个用户实例多次初始化（虽然通常不会，但保险）
        if hasattr(self, '_has_run'):
            return
        self._has_run = True

        # 安全分配唯一账号索引
        with user_allocator._lock:
            current_idx = user_allocator._idx
            if current_idx >= len(my_accounts):
                return
            user_allocator._idx += 1
        # 分配账号：
        if current_idx < len(my_accounts):
            self.account = my_accounts[current_idx]
        else:
            return

        # === 登录 ===
        try:
            resp = self.client.post(
                LOGIN_URL,
                json={"username": self.account, "password": PASSWORD},
                name="/api/login"
            )
            resp.raise_for_status()
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                logger.error(f"Empty response body (status: {status})")
                raise Exception(f"Empty response body (status: {status})")
            try:
                json_data = resp.json()
            except Exception as e:
                error_msg = f"JSON 解析失败 | 账号: {self.account} | 异常: {e}"
                logger.error(error_msg)
                raise Exception(f"{error_msg}")

            self.token = json_data.get("access_token")
            if not self.token:
                error_msg = f"登录成功但无 access_token | 账号: {self.account} | JSON: {json_data}"
                logger.error(error_msg)
                raise Exception(f"{error_msg}")
        except Exception as e:
            error_msg = f"登录异常 | 账号: {self.account} | 错误: {e}"
            logger.error(error_msg)

        # 休眠
        if GLOBAL_TASK_START and time.time() < GLOBAL_TASK_START:
            gevent.sleep(GLOBAL_TASK_START - time.time())





    @task
    def PURCHASE_ECDSA(self):
        if not self.token:
            return

        with data_lock:
            if not my_listings:
                return
            selected_id = my_listings.pop()
        target_id = selected_id
        if not target_id:
            return  # 3次都没找到，放弃

        query_params = {"version": "v1", "page": "1"}
        payload = {"listing_id": target_id, "purchase_amount": 200.0}
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
        headers.update({
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        })
        # 3. 发起购买请求
        try:
            resp = self.client.post(full_url,
                                    data=body_str,
                                    headers=headers,
                                    name="/api/purchase/create/ecdsa",
                                    timeout=30)
            resp.raise_for_status()
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                logger.error(f"Empty response body (status: {status})")
                raise Exception(f"Empty response body (status: {status})")
            try:
                json_data = resp.json()
            except Exception as e:
                logger.error(str(e))
                raise Exception(f"{str(e)}")

            if status != 201 :
                err_msg = f" 购买失败: {self.account} (HTTP {resp.status_code})，response:{resp.text[:200]}"
                logger.error(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                raise Exception(err_msg)

        except Exception as e:
            logger.error(str(e))
        self.stop()



