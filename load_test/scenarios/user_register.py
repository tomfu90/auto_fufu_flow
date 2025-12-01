# user_register.py
# coding = utf-8
# author =fufu

from locust import HttpUser,task,between,constant
# 将系统跟目录导入到python查询路径中
from  libs.random_utils import  generate_random_username,generate_random_email,generate_random_phone
from libs.utils import load_yaml

#获取url，不硬编码
config = load_yaml("config/config.yaml")
env = config["env"]
base_url = config["environments"][env]["user"]["base_url"]
register_url = config["environments"][env]["user"]["register_url"]


class RegisterUser(HttpUser):
    host = base_url
    wait_time = constant(3600)  # 关键：远大于 run-time

    @task
    def register_once(self):
        payload = {
            "username": generate_random_username(),
            "password": "Abc12345",
            "confirm_password": "Abc12345",
            "email": generate_random_email(),
            "phone": generate_random_phone()
        }

        with self.client.post(
                register_url,
                json=payload,
                catch_response=True,
                timeout=10
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                status = response.status_code
                reason = getattr(response, 'reason', 'Unknown')
                try:
                    content = str(response.json())
                except Exception:
                    content = response.text[:200] or 'NO_RESPONSE_BODY'

                error_detail = (
                    "Network error (可能: 超时/拒绝连接/SSL错误)"
                    if status == 0 else
                    f"HTTP {status} {reason} | Body: {content}"
                )
                response.failure(f"注册失败{status}-{error_detail}")