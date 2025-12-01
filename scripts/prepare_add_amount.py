# prepare_add_amount.py
# coding =utf-8
# author = fufu
import os,sys,time
project_root= os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from libs.utils import load_yaml
from libs.api_client import  Apiclient
#获取url，不硬编码
config = load_yaml("config/config.yaml")
env = config["env"]
base_url = config["environments"][env]["back"]["base_url"]
login_url = config["environments"][env]["back"]["login_url"]
admin_update_balance_url = config["environments"][env]["back"]["admin_update_balance_url"]
# 获取后台预置的admin账户 信息
users = load_yaml('data/login/test_users.yaml')['valid_back_users']
admin_user =next(user for user in users if user['role']=='ADMIN')
# 获取需要充钱的用户文档
output_file = os.path.join(project_root, "data", "login", "registered_accounts.txt")
def prepare_add_amount():
    """    后台admin 批量给新注册用户加钱;
          充值20000，确保用户可以出售多笔100的挂单
    """
    client = Apiclient(base_url)
    #admin 管理员登录
    resp = client.post(login_url,json=admin_user)
    assert resp.status_code == 200,f"{admin_user}登陆异常： {resp.text} "
    #登陆后传递token
    client.session.headers.update({"Authorization": f"Bearer {resp.json()['access_token']}"})
    # 用于记录失败的用户
    failed_users = []
    success_count = 0
    #读取用户文档
    try:
        with open(output_file,"r",encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    username = line.strip()
                else:
                    continue
                #加钱重试2次
                print("开始加钱，请等待===")
                for attempt in range(2):
                    data = {"username":username,"amount":20000}
                    #发起请求，每读到一个数据，发起一次加钱
                    resp = client.post(admin_update_balance_url,json=data)
                    if resp.status_code == 200:
                        success_count += 1
                        break # 加钱成功，不在重试
                    else:
                        time.sleep(0.5) #失败休息0.5s
                else:
                    failed_users.append(username) #记录失败用户
                time.sleep(0.01)     #每次循环完一次，休息0.01s
    except Exception as e:
        print(f"异常：{e}")


    finally:
        print(f"成功: {success_count} 个用户")
        print(f"失败: {len(failed_users)} 个用户")
        print("本次加钱结束")



if __name__ == "__main__":
    prepare_add_amount()