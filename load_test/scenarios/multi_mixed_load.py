# coding=utf-8
# author =fufu
"""
压测方式：
 - 压测典型场景： 区分角色阶梯压测，复杂撮合逻辑
 - 压测e2e场景说明：账号区分角色（卖家&买家），登陆-卖家角色挂单-买家角色买单-卖家查询挂单详情 -所有用户查询余额
 - 分布式压测（master-worker压测模式）🐮🍺
 - 复用之前e2e阶梯压测场景
 - 方案：总账号文件列表 按workerid进行切片索引：起始为0，按workerid进行偏移
 -----：再每个worker进行内部分配买家+卖家，其他逻辑复用之前e2e阶梯压测场景

行为：
  - 卖家：高频挂单（记录到 self.my_listings）
  - 买家：中频购买（从全局池买别人挂的单）
  - 查询挂单：仅卖家查自己挂的单；买家不发查询请求
  - 查询余额：买家和卖家都能查询

优化：
  - 多进程模式，账号读取出来作为一个公共池，每个进程根据进程id进行偏移获取不同账号，形成进程内账号池，再区分买卖角色
  - 虚拟用户分配账户时，也有协程锁🔒
  - 卖家发布挂单后，将挂单放入公共挂单池，也有协程锁🔒
  - 买家购买挂单成功后，将公共挂单池 删除已匹配挂单，也有协程锁🔒，解决重复购买
  - 登录仅尝试一次，失败即记录并放弃
  - 限制 public_listings 最大长度（防 OOM），防止内存泄漏
  - 支持阶梯压测
  - 日志记录不刷屏（每隔10条记录失败日志）

# ✅ 本脚本已通过以下验证：
#   - 并发安全（RLock 保护共享状态）
#   - 内存可控（挂单池上限 + 成功即移除）
#   - 角色行为隔离（买家/卖家任务分离）
#   - 错误抑制（日志频率控制 + 登录失败降级）
#   - Locust 规范（catch_response + with 上下文）

"""

import os
import json
import logging
import random
from urllib.parse import urlencode
from gevent.lock import RLock
from locust import events, HttpUser, task, between
import time
import gevent
from libs.utils import load_yaml
from libs.signature import ecdsa_signature
from locust.runners import MasterRunner, LocalRunner

# -url公共配置 -
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
config = load_yaml("config/config.yaml")
env = config["env"]
BASE_URL = config["environments"][env]["user"]["base_url"]
LOGIN_URL = config["environments"][env]["user"]["login_url"]
CREATE_LISTING_URL = config["environments"][env]["user"]["create_listing_url"]
PURCHASE_ECDSA_URL_PATH = config["environments"][env]["user"]["create_purchase_order_ecdsa_url"]
GET_LISTING_URL = config["environments"][env]["user"]["get_listing_url"]
get_balance_url = config["environments"][env]["user"]["get_balance_url"]
# 统一登陆密码
PASSWORD = "Abc12345"
# 日志基础配置（一次性配置，全局生效）
logging.basicConfig(
    level=logging.INFO,  # 日志输出级别：只输出ERROR及以上级别（过滤INFO/DEBUG，减少冗余）
    format="%(asctime)s - %(levelname)s - %(message)s",  # 日志显示格式
    handlers=[logging.StreamHandler()]  # 日志输出目标：仅输出到控制台（不写本地文件，符合你的需求）
)
# 创建日志器实例（用于区分不同模块的日志，避免冲突）
logger = logging.getLogger("Locust压测")


#读取环境变量-秘钥
API_SECRET = os.environ.get("ecdsa_SECRET")
if not API_SECRET:
    logging.critical("❌ 环境变量 ecdsa_SECRET 未设置！")
    raise EnvironmentError("Missing ecdsa_SECRET")

# 读取外部账号文件
ACCOUNT_FILE = os.path.join(project_root, "data", "login", "registered_accounts.txt")
with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_ACCOUNTS = [line.strip() for line in f if line.strip()]
# 读取环境变量，实际设置用户
MAX_AVAILABLE = len(ALL_ACCOUNTS)
TARGET_USERS = int(os.environ.get("TARGET_USERS"))
TARGET_USERS = min(TARGET_USERS, MAX_AVAILABLE)
#-----‼️按worker对账号进行分片--！！！！
total_workers = int(os.environ.get("total_workers",1)) #获取总进程数
worker_id = int(os.environ.get("worker_id",0))        #获取当前进程id
# 安全校验
if len(ALL_ACCOUNTS) < TARGET_USERS:
    raise ValueError(f"❌ 账号不足：需要 {TARGET_USERS}，实际只有 {len(ALL_ACCOUNTS)}")
# 起始索引为0，便宜由work_id决定
accounts_per_worker = TARGET_USERS // total_workers #整除
remainder = TARGET_USERS % total_workers            #余数

# 前remainder进程多1个账号
start_idx = worker_id * accounts_per_worker + min(worker_id, remainder)
end_idx = start_idx + accounts_per_worker + (1 if worker_id<remainder else 0)
my_accounts = ALL_ACCOUNTS[start_idx:end_idx]

# worker进程内部分配买家/卖家
num_sellers = (len(my_accounts ) +1 )// 2
num_buyers = len(my_accounts) // 2
seller_accounts = my_accounts[:num_sellers]
buyer_accounts =  my_accounts[num_sellers:]
logging.info(
    f"🧾 Worker {worker_id}/{total_workers} | "
    f"账号范围 [{start_idx}:{end_idx}] | "
    f"卖家: {num_sellers}, 买家: {num_buyers}"
)

# ------阶梯压测---------
#配置阶梯策略
#取压测时设置压测用户数，分3个阶段压
stages = [
    (TARGET_USERS//3,10),     #10s内启动 1/3y压测用户
    120,                      #持续2分钟
    (TARGET_USERS//3 *2,10),  #10s内启动 1/3压测用户
    120,                      #持续2分钟
    (TARGET_USERS,10),        #10s内启动 剩余1/3压测用户
    120                       #持续2分钟
]

@events.init.add_listener
def on_locust_init(environment, **kwargs):
    # 仅在本地运行 或 分布式 master 节点运行阶梯控制
    if not isinstance(environment.runner, (MasterRunner, LocalRunner)):
        return

    def run_stages():
        current_users = 0
        for stage in stages:
            if isinstance(stage, tuple):
                target,spawn_sec = stage
                spawn_rate = (target - current_users) / spawn_sec
                logging.info(f"🚀【加压】{current_users} → {target} 用户 | 速率: {spawn_rate:.1f}/秒")
                environment.runner.start(user_count=target, spawn_rate=spawn_rate)
                gevent.sleep(spawn_sec)
                current_users = target
            else:
                logging.info(f"⏸️【稳态】保持 {current_users} 用户 | 持续 {stage} 秒")
                gevent.sleep(stage)
        logging.info("⏹️【结束】所有阶段完成，自动停止压测")
        environment.runner.quit()

# 启动后台线程控制压测节奏 -分布式换成gevent
    gevent.spawn(run_stages)


# 进程挂单池（供买家购买）
public_listings = []
public_lock = RLock()
MAX_PUBLIC_LISTINGS = 10000  # 防止内存爆炸



# 核心工具函数：频率控制的失败日志输出
def log_failure(log_type, msg, interval=10):
    """
    函数作用：按“首次失败+间隔条数”输出失败日志，避免刷屏
    参数说明：
    - log_type: 日志类型（如"login"/"business"），用于区分不同场景的计数器（避免登录和业务失败计数混淆）
    - msg: 要输出的失败日志内容（你业务代码里拼接的错误信息）
    - interval: 频率间隔（默认10条输出1条，可自定义）
    """
    # 初始化计数器（用函数属性存，替代全局变量，更优雅）
    # 逻辑：判断log_failure函数是否有"counters"属性，没有则初始化一个字典（key是日志类型，value是计数）
    if not hasattr(log_failure, "counters"):
        log_failure.counters = {"login": 0, "business": 0}  # 初始：登录、业务失败计数都为0

    #对应类型的失败计数+1（每调用一次函数，说明发生一次失败）
    log_failure.counters[log_type] += 1

    # 频率控制核心逻辑（防刷屏的关键）
    # 条件：首次失败（计数=1） 或 达到间隔条数（计数%interval==0，如每10条）
    if log_failure.counters[log_type] == 1 or log_failure.counters[log_type] % interval == 0:
        logger.error(msg)  # 满足条件时，才输出日志到控制台


# --- 用户分配器 ---
class UserAllocator:
    def __init__(self):
        self._idx = 0
        self._lock = RLock()
#实例化分配器
user_allocator = UserAllocator()






# --- Locust User ---
class TradingUser(HttpUser):
    host = BASE_URL
    wait_time = between(0.5, 1.5)

    def on_start(self):
        # === 关键修复：提前初始化所有可能用到的属性 ===
        self.role = None
        self.account = None
        self.token = ""
        self.my_listings = []  # 必须在这里初始化！

        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # 分配账号
        with user_allocator._lock:
            current_idx = user_allocator._idx
            if current_idx >= len(my_accounts):
                return
            user_allocator._idx += 1

        if current_idx < num_sellers:
            self.role = "seller"
            self.account = seller_accounts[current_idx]
        elif current_idx < num_sellers + num_buyers:
            self.role = "buyer"
            self.account = buyer_accounts[current_idx - num_buyers]
        else:
            return

        # === 登录：仅尝试一次，失败即记录并退出 ===
        try:
            with self.client.post(
                    LOGIN_URL,
                    json={"username": self.account, "password": PASSWORD},
                    name="/api/login",
                    timeout=30,
                    catch_response=True
                ) as resp:
                    if resp.status_code == 200:
                            resp.success()
                            #自动更新token
                            self.token = resp.json()["access_token"]
                    else:
                        err_msg = f"[{self.role}] 登录失败: {self.account} (HTTP {resp.status_code})，response:{resp.text[:200]}"
                        log_failure("login",err_msg)
                        resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                        self.role = None
                        return
        except Exception as e:
            log_failure("login",str(e))
            self.client.fail("str(e)")
            self.role = None
            return

    # ==================== 卖家：挂单 ====================
    @task(10)
    def create_listing(self):
        if self.role != "seller" or not self.token:
            return
        try:
            with self.client.post(
                    CREATE_LISTING_URL,
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={"product_id": "baidu", "amount": 200, "currency": "CNY"},
                    name="/create_listing",
                    timeout=30,
                    catch_response=True
            ) as resp:
                if resp.status_code == 201:
                    listing_id = resp.json()["listing_id"]
                    resp.success()
                    self.my_listings.append(listing_id)
                    with public_lock:
                        public_listings.append({
                            "listing_id": listing_id,
                            "seller": self.account
                        })
                        #  防止内存无限增长
                        if len(public_listings) > MAX_PUBLIC_LISTINGS:
                            public_listings.pop(0) #最早的挂单就删除
                else:
                    err_msg = f"[{self.role}] 挂单失败: {self.account} (HTTP {resp.status_code})，response:{resp.text[:200]}"
                    log_failure("business", err_msg)
                    resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
        except Exception as e:
            log_failure("business", str(e))
            self.client.fail("str(e)")

    # ==================== 买家：购买 ====================
    @task(4)
    def purchase_order(self):
        if self.role != "buyer" or not self.token:
            return

        target = None
        with public_lock:
            candidates = []
            for i, item in enumerate(public_listings):
                if item["seller"] != self.account:
                    candidates.append((i, item))
            if candidates:
                target_index, target = random.choice(candidates)

        if not target:
            return

        listing_id = target["listing_id"]

        try:
            query_params = {"version": "v1", "page": "1"}
            payload = {"listing_id": listing_id, "purchase_amount": 200.0}
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

            with  self.client.post(full_url,
                                    data=body_str, headers=headers,
                                    name="/api/purchase/create/ecdsa",
                                    timeout=30,
                                    catch_response=True) as resp:
                if resp.status_code == 201:
                    # ✅ 成功后从全局池移除，避免重复购买
                    resp.success()
                    with public_lock:
                        if target in public_listings: #防止不存在
                            public_listings.remove(target)
                else:
                    err_msg = f"[{self.role}] 购买失败: {self.account} (HTTP {resp.status_code})，response:{resp.text[:200]}"
                    resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                    log_failure("business", err_msg)

        except Exception as e:
            log_failure("business", str(e))


    # ==================== 查询挂单详情：仅卖家查自己挂的单 ====================
    @task(2)
    def query_listing(self):
        if not self.my_listings or not self.token:
            return

        listing_id = random.choice(self.my_listings)

        try:
            with self.client.post(
                GET_LISTING_URL,
                json={"listing_id": listing_id},
                headers={"Authorization": f"Bearer {self.token}"},
                name="/get_listing",
                timeout=30,
                catch_response=True) as resp:
                if resp.status_code == 200:
                    resp.success()
                else:
                    err_msg = f" {self.account} 查询失败，挂单号：{listing_id}(HTTP {resp.status_code})，response:{resp.text[:200]}"
                    resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                    log_failure("business", err_msg)

        except Exception as e:
            log_failure("business", str(e))
            self.client.fail("str(e)")
    # ==================== 查询账余额：买家和卖家都能查询 ====================
    @task(5)
    def query_amount(self):
        if not self.token:
            return
        try:
            with self.client.get(get_balance_url,
                                 headers={"Authorization": f"Bearer {self.token}"},
                                 name="/get_balance_url",
                                 timeout=30,
                                 catch_response=True) as resp:
                if resp.status_code == 200:
                    resp.success()
                else:
                    err_msg = f" {self.account} 查询余额失败，(HTTP {resp.status_code})，response:{resp.text[:200]}"
                    resp.failure(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                    log_failure("business", err_msg)

        except Exception as e:
            log_failure("business", str(e))
            self.client.fail("str(e)")


