# prepare_accounts.py
# coding =utf-8
# author = fufu
import os,sys,time
import requests
project_root= os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from libs.utils import load_yaml
from libs.api_client import  Apiclient
#获取url，不硬编码
config = load_yaml("config/config.yaml")
env = config["env"]
base_url = config["environments"][env]["user"]["base_url"]
register_url = config["environments"][env]["user"]["register_url"]

total_count = 20000  # 总注册目标数
password = "Abc12345"  # 固定密码（简化逻辑）
output_file = os.path.join(project_root, "data", "login", "registered_accounts.txt") # 成功账号保存路径

delay = 0.01
def ensure_dir():
    """确保文件存在，文件存在不创建，不存在创建"""
    output_dir = os.path.dirname(output_file)
    os.makedirs(output_dir, exist_ok=True)

def load_existing_count():
    """文件计数"""
    if not os.path.exists(output_file):
        return 0
    try:
        with open(output_file,'r',encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())
    except Exception as e:
        print(f"文件{output_file}读取失败{e}")
        return 0

def generate_user_data(user_id):
    """用自增长生成账号，防止重复生成：user_id 序号"""
    username = f"fu{user_id:05d}"
    email = f"{username}@xixi.com"
    phone = f"138000{user_id:05d}"
    return {
            "username": username,
            "password":password,
            "confirm_password": password,
            "email": email,
            "phone": phone
        }



def main():
    """主程序"""
    ensure_dir()  # 先确保输出目录存在
    start_id = load_existing_count() + 1  # 下次注册的起始ID（已注册数+1）
    end_id = total_count  # 本次注册的结束ID（总目标数）
    # 检查是否已完成总目标
    if start_id > end_id:
        print(f"✅ 目标注册总数 {total_count} 已完成！")
        return

    # 打印启动信息（用户可见）
    print(f"📊 已注册 {start_id - 1} 个账号，目标 {total_count} 个。")
    print(f"📁 成功注册的账号将保存至: {output_file}")
    print(f"🚀 开始从 ID {start_id} 注册...")

    try:
        # 以“追加模式”打开输出文件（避免覆盖已注册的用户名）
        with open(output_file, "a", encoding="utf-8") as f:
            # 循环遍历从 start_id 到 end_id 的所有ID（每个ID对应一个用户）
            for user_id in range(start_id, end_id + 1):
                user_data = generate_user_data(user_id)
                username = user_data["username"]  # 提取用户名（用于后续打印和保存）
                try:
                    # 2. 发送注册请求（核心网络操作）
                    client = Apiclient(base_url)
                    resp = client.post(register_url, json=user_data, timeout=10)
                    if resp.status_code == 200:
                        # 成功：写入用户名到文件，立即刷新到磁盘（避免内存缓存丢失）
                        f.write(username + "\n")  # 每行一个用户名，方便后续读取
                        f.flush()  # 强制写入磁盘（重要：防止脚本中断时数据没保存）
                        print(f"[{user_id}/{end_id}] ✅ 成功: {username}")  # 打印成功信息
                    else:
                        # 失败：仅打印状态码（不保存数据）
                        print(f"[{user_id}/{end_id}] ❌ 失败: {username} - 状态码: {resp.status_code}")
                except Exception as e:
                    print(f"[{user_id}/{end_id}] ⚠️  错误: {username} - 异常: {e}")

                time.sleep(delay)

    except Exception as e:
        print(f"写入脚本异常{e}")

    finally:
        # 无论脚本是正常结束还是异常中断，都执行（保证最终统计信息一定打印）
        final_count = load_existing_count()
        print(f"\n📊 任务结束。当前共 {final_count} 个有效账号。")


if __name__ == "__main__":
    main()