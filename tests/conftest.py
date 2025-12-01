#coding = utf-8
#author = fufu
import pytest
import requests
import yaml
from pathlib import Path
import sys,time,os
import subprocess
#获取项目根目录
root_dir = Path(__file__).parent.parent
#如果根目录不存在 sys.path，就插在最前面
if str(root_dir) not in sys.path:
    sys.path.insert(0,str(root_dir))
#导入项目内部模块
from libs.api_client import Apiclient
from libs.utils import load_yaml
from libs.database import get_db_connection
from libs.mail import send_test_report

# Path(__file__) 返回当前文件绝对路径；ath(__file__).parent 返回父目录
# Path(__file__) 通过斜杆/ 拼接文件路径
CONFIG_PATH = Path(__file__).parent.parent / 'config' / 'config.yaml'
DATA_PATH = Path(__file__).parent.parent / 'data' / 'login'/'test_users.yaml'


@pytest.fixture()
def db_conn():
    conn = get_db_connection()
    yield conn
    conn.close()



# mock_app 服务是否启动 检查，检查/health接口
mock_server_process = None
@pytest.fixture(scope='session',autouse=True)
def start_mock_server():
    global mock_server_process
    #拼接路径,找出mock_app路径，防止相对路径报错
    project_dir= os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(project_dir, 'mock_server','app.py')
    mock_server_process = subprocess.Popen(
        ['python', app_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    #等待/health 返回200，最多等待10s
    timeout = 10
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(url="http://127.0.0.1:5000/health", timeout=1)
            if response.status_code == 200:
                print(" mock server is up")
                break
        except  requests.ConnectionError:
            time.sleep(1)
    else:
        raise RuntimeError("mock server did not start")

    yield
    #测试结束后关闭服务
    mock_server_process.terminate()
    mock_server_process.wait()




@pytest.fixture(scope='session')
def config():
    '''读取全局配置文件，只读取一次'''
    return load_yaml(CONFIG_PATH)

@pytest.fixture(scope='session')
def test_users():
    '''读取登陆用户测试数据，只读取一次'''
    return load_yaml(DATA_PATH)



@pytest.fixture(scope='session')
def default_user(test_users):
    """
    封装默认的客户端用户，role:default
     获取有效用户,第一个默认角色用户
    """
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    return username

@pytest.fixture(scope='session')
def sell_user(test_users):
    """
    封装默认的sell用户，role:sell
    获取有效用户,第一个默认角色用户
    """
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "sell")
    username = user_cred['username']
    return username


@pytest.fixture(scope='session')
def back_normal_user(test_users):
    """
    封装普通后台用户，role:normal
    获取有效用户,第一个默认角色用户
    """
    user_creds = test_users['valid_back_users']
    user_cred = next(user for user in user_creds if user['role'] == "NORMAL")
    username = user_cred['username']
    return username

@pytest.fixture(scope='session')
def back_admin_user(test_users):
    """
    封装默认的后台管理员用户，role:admin
    获取有效用户,第一个默认角色用户
    """
    user_creds = test_users['valid_back_users']
    user_cred = next(user for user in user_creds if user['role'] == "ADMIN")
    username = user_cred['username']
    return username


@pytest.fixture(scope='module')
def logged_user_client(config,test_users):
    """创建已登陆的前端用户客户端"""
    env = config['env']
    base_url = config['environments'][env]['user']['base_url']
    login_url = config['environments'][env]['user']['login_url']
    #保存多个已登陆用户客户端client
    clients ={}
    #读取用户
    users = test_users['valid_user_users']
    for user in users:
        username = user['username']
        # 创建客户端
        client = Apiclient(base_url=base_url)
        response = client.post(login_url, json=user)
        assert response.status_code == 200, f"{username}登陆失败：{response.text}"
        resp = response.json()
        token = resp['access_token']
        # 设置全局认证头
        client.session.headers.update({"Authorization": f"Bearer {token}"})
        client._username = username
        clients[username] = client

    return clients

@pytest.fixture(scope='module')
def logged_back_client(config,test_users):
    """创建已登陆的后台管理系统客户端"""
    env = config['env']
    base_url = config['environments'][env]['back']['base_url']
    login_url = config['environments'][env]['back']['login_url']
    #保存多个已登陆用户客户端client
    clients ={}
    #读取用户
    users = test_users['valid_back_users']
    for user in users:
        username = user['username']
        # 创建客户端
        client = Apiclient(base_url=base_url)
        response = client.post(login_url, json=user)
        assert response.status_code == 200, f"{username}登陆失败：{response.text}"
        resp = response.json()
        token = resp['access_token']
        # 设置全局认证头
        client.session.headers.update({"Authorization": f"Bearer {token}"})
        client._username = username
        clients[username] = client

    return clients

_start_time = None
def pytest_sessionstart(session):
    global _start_time
    _start_time = time.time()

def pytest_terminal_summary(terminalreporter,exitstatus,config):
    duration = time.time() - _start_time

    passed_list = terminalreporter.stats.get('passed', [])
    failed_list = terminalreporter.stats.get('failed', [])
    errors_list = terminalreporter.stats.get('errors', [])
    skipped_list = terminalreporter.stats.get('skipped', [])

    # 统计 xfail 和 xpass
    xfail = 0
    xpass = 0

    #检查failed哪些是xfail
    for rep in failed_list:
        if hasattr(rep,'wasxfail'):
            xfail += 1
    # 检查passed哪些是xpass
    for rep in passed_list:
        if hasattr(rep,'wasxfail'):
            xpass += 1

    #真正的失败
    real_failed = len(failed_list) - xfail
    #真正的成功
    real_passed = len(passed_list) - xpass

    skipped = len(skipped_list)
    errors = len(errors_list)

    total = len(passed_list) + len(failed_list) + skipped + errors


    # ：如果没有运行任何测试，跳过邮件
    if total == 0:
        print("⚠️ 未运行任何测试用例，跳过发送邮件。")
        return

    allure_link = os.getenv("ALLURE_REPORT_URL",None)

    send_test_report(
        total=total,
        passed=real_passed,
        failed=real_failed,
        errors=errors,
        skipped=skipped,
        xfail=xfail,
        xpass=xpass,
        duration_sec=duration,
        allure_link=allure_link
    )








