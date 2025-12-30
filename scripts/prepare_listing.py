#coding = utf-8
#author =fufu
import os,sys,time
project_root= os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
import requests
from libs.utils import load_yaml
from libs.api_client import  Apiclient
#获取url，不硬编码
config = load_yaml("config/config.yaml")
env = config["env"]
base_url = config["environments"][env]["user"]["base_url"]
login_url = config["environments"][env]["user"]["login_url"]
CREATE_LISTING_URL = config["environments"][env]["user"]["create_listing_url"]
# 统一登陆密码
PASSWORD = "Abc12345"
# 读取外部账号文件
ACCOUNT_FILE = os.path.join(project_root, "data", "login", "registered_accounts.txt")
with open(ACCOUNT_FILE, "r", encoding="utf-8") as f:
    ALL_ACCOUNTS = [line.strip() for line in f if line.strip()]
user_file = os.path.join(project_root, "data", "login", "registered_accounts.txt")
listing_file = os.path.join(project_root, "data", "order", "listing.txt") # 成功账号保存路径
#先取账号

accounts_500 = ALL_ACCOUNTS[-500:]
print(accounts_500)
#先登陆
for account in accounts_500:
    resp = requests.post(
                        base_url+login_url,
                        json={"username": account, "password": PASSWORD},
                        timeout=30)
    if resp.status_code == 200:
        #再挂单
        token = resp.json()["access_token"]
        print(token)
        for x in range(10):
            resp1 = requests.post(
                base_url+CREATE_LISTING_URL,
                headers={"Authorization": f"Bearer {token}"},
                json={"product_id": "baidu", "amount": 200, "currency": "CNY"},
                timeout=30)
            print(resp1.status_code)
            if resp1.status_code == 201:
                listing_id = resp1.json()["listing_id"]
                with open(listing_file, "a", encoding="utf-8") as f:
                        f.write(f"{listing_id}\n")
    else:
        print(resp.content)


