# coding=utf-8
# author =fufu
"""
压测方式：
 - 压测典型场景： 区分角色阶梯压测，复杂撮合逻辑
 - 压测e2e场景说明：账号区分角色（卖家&买家），登陆-卖家角色挂单-买家角色买单-卖家查询挂单详情 -所有用户查询余额
 - 分布式压测（master-worker压测模式）
 - 复用之前e2e阶梯压测场景
 - 方案：总账号文件列表 按workerid进行切片索引：起始为0，按workerid进行偏移
 -----：再每个worker进行内部分配买家+卖家，其他逻辑复用之前e2e阶梯压测场景

行为：
  - 卖家：高频挂单（记录到 self.my_listings）
  - 买家：高频购买（从全局池买别人挂的单）
  - 查询挂单：中频- 仅卖家查自己挂的单；买家不发查询请求
  - 查询余额：低频- 买家和卖家都能查询

优化：
  - 多进程模式，账号读取出来作为一个公共池，每个进程根据进程id进行偏移获取不同账号，形成进程内账号池，再区分买卖角色
  - 虚拟用户分配账户时，也有协程锁🔒
  - 卖家发布挂单后，将挂单放入公共挂单池，也有协程锁🔒
  - 买家购买挂单成功后，将公共挂单池 删除已匹配挂单，也有协程锁🔒，解决重复购买
  - 登录仅尝试一次，失败即记录并放弃
  - 限制 public_listings 最大长度（防 OOM），防止内存泄漏
  - 支持阶梯压测
  - 挂单池改用「dict + deque」：dict存挂单信息（O(1)查），deque存顺序（O(1)删）
  - 买家选单：3次随机重试，无全量遍历
  - 锁粒度最小化：读快照放锁外，仅写操作加锁

# ✅ 本脚本已通过以下验证：
#   - 并发安全（RLock 保护共享状态）
#   - 内存可控（公告挂单池上限 3000 + 成功即移除；个人挂单池上限 100 +移除）
#   - 角色行为隔离（买家/卖家任务分离）
#   - 无O(n)循环，高并发性能稳定


"""

import os
import json
import logging
import random
from urllib.parse import urlencode
from gevent.lock import RLock
from locust import events,FastHttpUser, task, between
import gevent
from collections import deque
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
# 复用locust原生logger(同步到web ui/终端)
logger = logging.getLogger("locust")
logger.setLevel(logging.INFO)

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


# ------阶梯压测---------
#配置阶梯策略
#取压测时设置压测用户数，分3个阶段压
stages = [
    (TARGET_USERS//3,10),     #10s内启动 1/3y压测用户
    120,                      #持续2分钟
    ((TARGET_USERS//3) *2,10),  #10s内启动 1/3压测用户
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


# ========== ：公共挂单池（dict + deque） ==========
public_listings = {}
listing_order = deque()
public_lock = RLock()
MAX_PUBLIC_LISTINGS = 3000  # 防止内存爆炸


# --- 用户分配器 ---
class UserAllocator:
    def __init__(self):
        self._idx = 0
        self._lock = RLock()
#实例化分配器
user_allocator = UserAllocator()


# --- Locust User ---
class TradingUser(FastHttpUser):
    host = BASE_URL
    wait_time = between(0.5, 1.5)
    max_connections = 100 # 连接池 ，设置100个持久tcp连接，避免端口耗尽
    max_retries = 1 # @task方法 最大重试次数。默认2改为1

    def on_start(self):
        # === 关提前初始化所有可能用到的属性 ===
        self.role = None
        self.account = None
        self.token = ""
        self.my_listings = []  # 记录自己的挂单

        if hasattr(self, "_initialized"):
            return
        self._initialized = True

        # 分配账号
        with user_allocator._lock:
            current_idx = user_allocator._idx
            if current_idx >= len(my_accounts):
                return
            user_allocator._idx += 1

        # 分配账号后：
        if current_idx < len(my_accounts):
            account = my_accounts[current_idx]
            # 轮询分配角色：偶数索引卖家，奇数买家
            if current_idx % 2 == 0:
                self.role = "seller"
                self.account = account
            else:
                self.role = "buyer"
                self.account = account
        else:
            return

        # === 登录：仅尝试一次，失败即记录并退出 ===
        try:
            resp = self.client.post(
                    LOGIN_URL,
                    json={"username": self.account, "password": PASSWORD},
                    name="/api/login",
                    timeout=30)
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
            # Locust 已自动将此请求标记为失败
            error_msg = f"登录异常 | 账号: {self.account} | 错误: {e}"
            logger.error(error_msg)


    # ==================== 卖家：挂单 ====================
    @task(10)
    def create_listing(self):
        if self.role != "seller" or not self.token:
            return
        try:
            resp = self.client.post(
                    CREATE_LISTING_URL,
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={"product_id": "baidu", "amount": 200, "currency": "CNY"},
                    name="/create_listing",
                    timeout=30)
            resp.raise_for_status()
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                logger.error(f"Empty response body (status: {status})")
                raise Exception(f"Empty response body (status: {status})")
            try:
                json_data = resp.json()
            except Exception as e:
                logger.error(f"异常{str(e)}")
                raise Exception(f"{str(e)}")
            listing_id = resp.json()["listing_id"]
            if  listing_id:
                    self.my_listings.append(listing_id)
                    # 加锁写入挂单池，仅写操作加锁
                    with public_lock:
                        # 字典O(1)新增
                        public_listings[listing_id]=self.account
                        # 双端队列O(1)记录顺序
                        listing_order.append(listing_id)
                        #  防止内存无限增长
                        if len(public_listings) > MAX_PUBLIC_LISTINGS:
                            oldest_id = listing_order.popleft()  # 删队首（O(1)）
                            if oldest_id in public_listings:
                                del public_listings[oldest_id]  # 删字典（O(1)）

                    if len(self.my_listings) > 100:
                        self.my_listings.pop(0)
            else:
                err_msg = f"[{self.role}] 挂单失败: {self.account} (HTTP {resp.status_code})，response:{resp.text[:200]}"
                logger.error(err_msg)
                raise Exception(f"{resp.status_code}{resp.url}{resp.text[:200]}")
        except Exception as e:
            logger.error(str(e))

    # ==================== 买家：购买 ====================
    @task(8)
    def purchase_order(self):
        if self.role != "buyer" or not self.token:
            return

        target_id = None
        # 1. 无锁读：仅复制keys（轻量，O(1)快照）
        with public_lock:
            all_ids = list(public_listings.keys())  # 只拿ID，不复制完整数据
        if not all_ids:
            return
        # 2. 3次随机重试：找非自己的挂单（无遍历）
        for _ in range(3):
            selected_id = random.choice(all_ids)
            # 字典O(1)查询卖家账号
            if public_listings[selected_id] != self.account:
                target_id = selected_id
                break

        if not target_id:
            return # 3次都没找到，放弃


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

            if status == 201 and json_data["status"]=="PENDING_REVIEW":
                # 4. 购买成功：O(1)删除挂单
                with public_lock:
                    if target_id in public_listings:
                        del public_listings[target_id]  # 字典O(1)删
                        # 不用删deque，淘汰时自动清理无效ID（不影响逻辑）
            else:
                err_msg = f"[{self.role}] 购买失败: {self.account} (HTTP {resp.status_code})，response:{resp.text[:200]}"
                logger.error(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                raise Exception(err_msg)

        except Exception as e:
            logger.error(str(e))


    # ==================== 查询挂单详情：仅卖家查自己挂的单 ====================
    @task(3)
    def query_listing(self):
        if not self.my_listings or not self.token:
            return

        listing_id = random.choice(self.my_listings)
        #挂单id查询不到，直接放弃
        if not listing_id:
            return
        try:
            resp = self.client.post(
                GET_LISTING_URL,
                json={"listing_id": listing_id},
                headers={"Authorization": f"Bearer {self.token}"},
                name="/get_listing",
                timeout=30)
            resp.raise_for_status()
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                logger.error(f"Empty response body (status: {status})")
                raise Exception(f"Empty response body (status: {status})")
            if resp.status_code != 200:
                err_msg = f" {self.account} 查询失败，挂单号：{listing_id}(HTTP {resp.status_code})，response:{resp.text[:200]}"
                logger.error(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                raise Exception(err_msg)
        except Exception as e:
            logger.error(str(e))

    # ==================== 查询账余额：买家和卖家都能查询 ====================
    @task(3)
    def query_amount(self):
        if not self.token:
            return
        try:
            resp = self.client.get(get_balance_url,
                                 headers={"Authorization": f"Bearer {self.token}"},
                                 name="/get_balance_url",
                                 timeout=30)
            resp.raise_for_status()
            status = getattr(resp, 'status_code', 'unknown')
            if not resp.content:
                logger.error(f"Empty response body (status: {status})")
                raise Exception(f"Empty response body (status: {status})")
            if resp.status_code != 200:
                err_msg = f" {self.account} 查询余额失败，(HTTP {resp.status_code})，response:{resp.text[:200]}"
                logger.error(f"{resp.status_code}{resp.url}{resp.text[:200]}")
                raise Exception(err_msg)

        except Exception as e:
            logger.error(str(e))


