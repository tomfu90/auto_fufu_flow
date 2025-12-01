# coding = utf-8
# author = fufu

import sys
import pytest
from pathlib import Path
import allure
import random
import string

from tests.unit.register.conftest import register_url

#设置项目根目录，防止意外找不到导内部模块路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
from libs.utils import load_yaml
from libs.api_client import  Apiclient
from libs.logger import log_assertion
from libs.utils import  load_test_cases
from tests.unit.register.schemas import  validate_order_test_cases
# 检查yaml格式
validate_order_test_cases(load_yaml("data/login/test_register.yaml"))
#获取用例数据-用渲染方法，替换yaml中{{}}占位符 随机数
testcases = load_test_cases("data/login/test_register.yaml")
success_cases = testcases['success_cases']
fail_cases = testcases['fail_cases']



@pytest.mark.smoke
@pytest.mark.parametrize("case", success_cases)
def test_register_success(case,db_conn,base_url,register_url):
    print(f"开始发起测试：{case['name']}")
    #allure动态标题
    allure.dynamic.title(case['name'])
    #注册会话
    client = Apiclient(base_url)
    #发起注册请求
    response = client.post(register_url, json=case['input'])
    with allure.step('校验响应状态码'):
        #校验状态码
        actual_value = response.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'], actual_value==expected_value, actual_value, expected_value)
        assert actual_value == expected_value,f"实际：{actual_value} 期望：{expected_value}"
    with allure.step('校验响应返回信息'):
        actual_value = response.json()['message']
        expected_value = case['expected']['message']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"
    with allure.step('数据库users校验：表中插入数据'):
        row = db_conn.execute("SELECT username FROM users WHERE username=?", (case['input']['username'],)).fetchone()
        actual_value =row['username']
        expected_value = response.json()['username']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"期望：{expected_value} 实际users数据库：{actual_value}"
    with allure.step('数据库accounts校验：创建账户'):
        row = db_conn.execute("SELECT username,balance FROM accounts WHERE username=?", (case['input']['username'],)).fetchone()
        #数据库多字段校验
        fields =['username','balance']
        actual_value = {field: row[field] for field in fields}
        expected_value ={'username':response.json()['username'],'balance':0}
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"期望：{expected_value} 实际accounts数据库：{actual_value}"

@pytest.mark.parametrize("case",fail_cases)
def test_register_fail(case,base_url,register_url,repeat_phone,repeat_email,repeat_username):
    print(f"开始发起测试：{case['name']}")
    #allure动态标题
    allure.dynamic.title(case['name'])
    #获取请求数据
    data = case['input']
    #场景1 -账号重复
    if case['input'].get('mark') and case['input'].get('mark') =="username_repeat":
        data['username'] = repeat_username
    #场景2 -手机号重复
    elif case['input'].get('mark') and case['input'].get('mark') =="phone_repeat":
        data['phone'] = repeat_phone
    #场景3 -邮箱重复
    elif case['input'].get('mark') and case['input'].get('mark') == "email_repeat":
        data['email'] = repeat_email
    #场景4 -其他失败场景，不修改任何东西，直接用yaml数据测试
    else:
        pass

    #注册会话
    client = Apiclient(base_url)
    #发起注册请求
    response = client.post(register_url, json=data)
    print(data)
    with allure.step('校验响应状态码'):
        #校验状态码
        actual_value = response.status_code
        expected_value = case['expected']['status_code']
        log_assertion(actual_value, actual_value==expected_value, actual_value, expected_value)
        assert actual_value == expected_value,f"实际：{actual_value} 期望：{expected_value}"
    with allure.step('校验响应返回信息'):
        actual_value = response.json()['error']
        expected_value = case['expected']['error']
        log_assertion(actual_value, actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"

