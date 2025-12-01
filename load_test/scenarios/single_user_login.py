# single_user_login.py
# coding =utf-8
# author = fufu
import os,sys,random
from locust import FastHttpUser, task, constant
from locust.exception import StopUser
from libs.utils import load_yaml
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import threading
# --- 路径和配置 ---
config = load_yaml("config/config.yaml")
env = config["env"]
BASE_URL = config["environments"][env]["user"]["base_url"]
LOGIN_URL = config["environments"][env]["user"]["login_url"]
PASSWORD = "Abc12345"

ACCOUNT_FILE = os.path.join(project_root, "data", "login", "registered_accounts.txt")


with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_USERS = [line.strip() for line in f if line.strip()]

if not ALL_USERS:
    raise SystemExit("❌ 账号文件为空！")

class HighRPSUser(FastHttpUser):
    host = BASE_URL  # ← 替换为你的实际地址
    wait_time = constant(1000)
    _counter = 0
    _lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with self._lock:
            HighRPSUser._counter += 1
            if HighRPSUser._counter % 5000 == 0:
                print(f"✅ 已创建 {HighRPSUser._counter} 个用户")

    def on_start(self):
        # 每个用户随机绑定一个账号（也可每次 task 随机）
        # ... rest of login logic
        try:
            self.username = random.choice(ALL_USERS)
            data = {"username": self.username, "password": PASSWORD}
            with self.client.post(
                LOGIN_URL,
                name="/login",
                json=data,
                headers={"Connection": "close"},
                catch_response=True,
                timeout=10
            ) as res:
                if res.status_code == 200:
                    res.success()
                else:
                    try:
                        # 安全截断：避免大响应体
                        error_snippet = res.text[:200] if res.text else ""
                    except Exception:
                        error_snippet = "(no response body)"
                    res.failure(f"{res.status_code}: {error_snippet}")

        except Exception as e:
            # 捕获所有异常（包括网络层），避免用户崩溃
            self.environment.stats.log_error("POST", "/login", str(e))
            # 不抛出异常 → 用户不会崩溃 → 不会被替换
        # 无论成功失败，都不再做任何事
    @task
    def stop_user_after_login(self):
        """只执行一次任务，然后优雅退出当前用户"""
        pass




