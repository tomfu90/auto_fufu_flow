#coding = utf-8
#author = fufu
#登陆接口测试用例
import pytest
import yaml
from pathlib import Path
import sys
import allure

from tests.conftest import test_users

#获取项目根目录
root_dir = Path(__file__).parent.parent
#如果根目录不存在 sys.path，就插在最前面
if str(root_dir) not in sys.path:
    sys.path.insert(0,str(root_dir))
from libs import api_client
from libs.logger import log_assertion
from libs.utils import load_yaml

@pytest.mark.smoke
def test_login_success(config,test_users,db_conn):
    """登陆成功"""
    print(f"开始执行用例，登陆成功")
    #设置allure用例名
    allure.dynamic.title("登陆成功")
    #获取url
    env = config['env']
    base_url = config['environments'][env]['user']['base_url']
    login_url = config['environments'][env]['user']['login_url']
    #获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred =next(user for user in user_creds if user['role'] == "default")
    #发起请求，先创建会话实例
    client = api_client.Apiclient(base_url)
    # 发起登陆请求
    response = client.post(login_url,json=user_cred)
    token = response.json()['access_token']
    with allure.step("校验token"):
        row = db_conn.execute("select token from tokens where username =?",(user_cred['username'],)).fetchone()
        log_assertion(f"{user_cred['username']}登陆成功",row)
        assert response.json()['info'] == "登陆成功"
        assert row is not None
        assert row['token'] == token,f"响应token:{token}，数据库token:{row['token']}"

#读取无效用户数据
users= load_yaml('data/login/test_users.yaml')
_invalid_users=users['invalid_user_users']

@pytest.mark.parametrize('login_fail_case', _invalid_users)
def test_login_fail(config, login_fail_case):
    """登陆失败"""
    print(f"开始执行用例，{login_fail_case['name']}")
    #allure自动添加用例标题
    allure.dynamic.title(login_fail_case['name'])
    #获取url
    env = config['env']
    base_url = config['environments'][env]['user']['base_url']
    login_url = config['environments'][env]['user']['login_url']
    # 获取用户数据
    user_info = login_fail_case['input']
    # 发起请求，先创建会话实例
    client = api_client.Apiclient(base_url)
    # 发起登陆请求
    response = client.post(login_url, json=user_info)
    resp=response.json()
    with allure.step('校验状态码'):
        actual_value = response.status_code
        expected_value = login_fail_case['expected']['status_code']
        log_assertion(login_fail_case['name'], actual_value == expected_value, actual_value,expected_value)
        assert actual_value == expected_value,f"实际：{actual_value}，预期：{expected_value}"
    with allure.step('校验响应信息'):
        actual_value =  resp['error']
        expected_value = login_fail_case['expected']['error']
        log_assertion(login_fail_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value}，预期：{expected_value}"



if __name__ == '__main__':
    pytest.main(['--vs'])