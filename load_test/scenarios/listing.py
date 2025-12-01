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

11.30优化：
  - 多进程模式，账号读取出来，先获取到压测用户，每个进程根据进程id进行偏移获取不同账号，形成进程内账号池，不区分角色
  - 登录仅尝试一次，失败即记录并放弃
  - 支持阶梯压测
  - 日志记录不刷屏（每隔10条记录失败日志）
  - 使用fasthttpuser 高性能模式
  - 环境变量压测用户，阶梯压测只取小数，不取整数倍数
  - fasthttpuser 不支持 self.client.fail ，改为self.environment.events.request.fire 手动触发异常日志，标记为失败
12.01优化：
  - 修复 大量并发时'NoneType' object is not subscriptable，避免直接使用resp.json()[""]
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

# ====== 【关键修复】安全封装 resp.json()，防止返回 None 导致崩溃 ======
from locust.contrib.fasthttp import FastResponse

_original_json = FastResponse.json

def safe_json(self):
    try:
        data = _original_json(self)
        if data is None:
            logger.debug(f"⚠️ safe_json: response is JSON null | URL: {getattr(self, 'url', 'unknown')} | Text: {repr(self.text[:200])}")
            return {}
        return data
    except Exception as e:
        logger.warning(f"⚠️ safe_json failed for {getattr(self, 'url', 'unknown')}: {e} | Text: {repr(self.text[:200])}")
        return {}

FastResponse.json = safe_json
# ===================================================================

# -url公共配置 -
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
config = load_yaml("config/config.yaml")
env = config["env"]
BASE_URL = config["environments"][env]["user"]["base_url"]
LOGIN_URL = config["environments"][env]["user"]["login_url"]
CREATE_LISTING_URL = config["environments"][env]["user"]["create_listing_url"]
GET_LISTING_URL = config["environments"][env]["user"]["get_listing_url"]
get_balance_url = config["environments"][env]["user"]["get_balance_url"]
# 统一登陆密码
PASSWORD = "Abc12345"

# 日志基础配置（一次性配置，全局生效）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Locust压测")


# 读取外部账号文件
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


# ------阶梯压测---------
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


# ====== 【关键修复】使用 defaultdict 避免 KeyError ======
def log_failure(log_type, msg, interval=50):
    if not hasattr(log_failure, "counters"):
        log_failure.counters = defaultdict(int)
    log_failure.counters[log_type] += 1
    if log_failure.counters[log_type] == 1 or log_failure.counters[log_type] % interval == 0:
        logger.error(msg)
# ======================================================


class UserAllocator:
    def __init__(self):
        self._idx = 0
        self._lock = RLock()


user_allocator = UserAllocator()


class ListingUser(FastHttpUser):
    host = BASE_URL
    wait_time = between(0.5, 1.5)

    def _handle_network_failure(self, request_type, name, start_time):
        """处理 resp is None 的网络层失败"""
        err_msg = f"【网络失败】账号: {getattr(self, 'account', 'unknown')} | 请求: {name}"
        logger.error(err_msg)
        log_failure("network", err_msg)
        self.environment.events.request.fire(
            request_type=request_type,
            name=name,
            response_time=(time.time() - start_time) * 1000,
            response_length=0,
            status_code=0,
            success=False,
            exception=Exception("No response from server (resp is None)"),
        )

    def on_start(self):
        start_time = time.time()
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
            with self.client.post(
                LOGIN_URL,
                json={"username": self.account, "password": PASSWORD},
                name="/api/login",
                timeout=(3, 10),
                catch_response=True
            ) as resp:
                # ========== 关键：第一行判空 ==========
                if resp is None:
                    self._handle_network_failure("POST", "/api/login", start_time)
                    return

                if resp.status_code == 200:
                    try:
                        json_data = resp.json()
                    except (JSONDecodeError, TypeError) as e:
                        raw = resp.text[:300]
                        error_msg = f"登录 JSON 解析失败 | 账号: {self.account} | 响应: {repr(raw)} | 错误: {e}"
                        logger.error(error_msg)
                        log_failure("login_json_error", error_msg)
                        resp.failure("JSON decode failed")
                        return

                    self.token = json_data.get("access_token")
                    if not self.token:
                        error_msg = f"登录成功但无 access_token | 账号: {self.account} | JSON: {json_data}"
                        logger.error(error_msg)
                        log_failure("login_no_token", error_msg)
                        resp.failure("Missing access_token")
                        return
                    resp.success()
                else:
                    err_msg = f"登录失败: {self.account} (HTTP {resp.status_code})，response:{resp.text[:200]}"
                    log_failure("login", err_msg)
                    resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                    return

        except Exception as outer_e:
            full_tb = "".join(traceback.format_exception(type(outer_e), outer_e, outer_e.__traceback__))
            logger.error(f"【CRITICAL】on_start 异常 | 账号: {self.account} | 错误:\n{full_tb}")
            log_failure("exception", str(outer_e))
            self.environment.events.request.fire(
                request_type="POST",
                name="/api/login",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                status_code=0,
                success=False,
                exception=outer_e,
            )
            return

    @task(10)
    def create_listing(self):
        start_time = time.time()
        if not self.token:
            return
        try:
            with self.client.post(
                CREATE_LISTING_URL,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"product_id": "baidu", "amount": 200, "currency": "CNY"},
                name="/create_listing",
                timeout=(3, 10),
                catch_response=True
            ) as resp:
                # ========== 关键：第一行判空 ==========
                if resp is None:
                    self._handle_network_failure("POST", "/create_listing", start_time)
                    return

                if resp.status_code == 201:
                    try:
                        json_data = resp.json()
                    except (JSONDecodeError, TypeError) as e:
                        raw = resp.text[:300]
                        error_msg = f"挂单 JSON 解析失败 | 账号: {self.account} | 响应: {repr(raw)} | 错误: {e}"
                        logger.error(error_msg)
                        log_failure("listing_json_error", error_msg)
                        resp.failure("JSON decode failed")
                        return

                    listing_id = json_data.get("listing_id")
                    if not listing_id:
                        error_msg = f"挂单成功但无 listing_id | 账号: {self.account} | JSON: {json_data}"
                        logger.error(error_msg)
                        log_failure("listing_no_id", error_msg)
                        resp.failure("Missing listing_id")
                        return
                    self.my_listings.append(listing_id)
                    resp.success()
                else:
                    err_msg = f"挂单失败: {self.account} (HTTP {resp.status_code})，response:{resp.text[:200]}"
                    log_failure("business", err_msg)
                    resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
        except Exception as outer_e:
            full_tb = "".join(traceback.format_exception(type(outer_e), outer_e, outer_e.__traceback__))
            logger.error(f"【CRITICAL】create_listing 异常 | 账号: {self.account} | 错误:\n{full_tb}")
            log_failure("exception", str(outer_e))
            self.environment.events.request.fire(
                request_type="POST",
                name="/create_listing",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                status_code=0,
                success=False,
                exception=outer_e,
            )

    @task(2)
    def query_listing(self):
        start_time = time.time()
        if not self.my_listings or not self.token:
            return

        listing_id = random.choice(self.my_listings)

        try:
            with self.client.post(
                GET_LISTING_URL,
                json={"listing_id": listing_id},
                headers={"Authorization": f"Bearer {self.token}"},
                name="/get_listing",
                timeout=(3, 10),
                catch_response=True
            ) as resp:
                # ========== 关键：第一行判空 ==========
                if resp is None:
                    self._handle_network_failure("POST", "/get_listing", start_time)
                    return

                if resp.status_code == 200:
                    resp.success()
                else:
                    err_msg = f"{self.account} 查询失败，挂单号：{listing_id}(HTTP {resp.status_code})，response:{resp.text[:200]}"
                    log_failure("business", err_msg)
                    resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
        except Exception as e:
            full_tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error(f"【CRITICAL】query_listing 异常 | 账号: {self.account} | 错误:\n{full_tb}")
            log_failure("exception", str(e))
            self.environment.events.request.fire(
                request_type="POST",
                name="/get_listing",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                status_code=0,
                success=False,
                exception=e,
            )

    @task(5)
    def query_amount(self):
        start_time = time.time()
        if not self.token:
            return
        try:
            with self.client.get(
                get_balance_url,
                headers={"Authorization": f"Bearer {self.token}"},
                name="/get_balance_url",
                timeout=(3, 10),
                catch_response=True
            ) as resp:
                # ========== 关键：第一行判空 ==========
                if resp is None:
                    self._handle_network_failure("GET", "/get_balance_url", start_time)
                    return

                if resp.status_code == 200:
                    resp.success()
                else:
                    err_msg = f"{self.account} 查询余额失败，(HTTP {resp.status_code})，response:{resp.text[:200]}"
                    log_failure("business", err_msg)
                    resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
        except Exception as e:
            full_tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error(f"【CRITICAL】query_amount 异常 | 账号: {self.account} | 错误:\n{full_tb}")
            log_failure("exception", str(e))
            self.environment.events.request.fire(
                request_type="GET",
                name="/get_balance_url",
                response_time=(time.time() - start_time) * 1000,
                response_length=0,
                status_code=0,
                success=False,
                exception=e,
            )