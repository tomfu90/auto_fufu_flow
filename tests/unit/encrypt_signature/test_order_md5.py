# coding =utf-8
# author = fufu
# md5加盐 签名订单接口测试
import os,sys

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_dir)
from libs.signature import md5_signature
from libs.utils import render_placeholders
import pytest
import allure
from libs.utils import load_yaml
from libs.logger import log_assertion
from libs.signature import md5_signature
testcases = load_yaml('data/order/test_order_md5.yaml')
success_cases = testcases['test_cases']['success_cases']
fail_cases =testcases['test_cases']['fail_cases']

#获取环境变量——签名秘钥：en.md5_key + en.md5_secret
context = {
    "en": {
        "md5_key": os.getenv("md5_key"),
        "md5_secret": os.getenv("md5_secret")
    }
}

@pytest.mark.parametrize('success_cases',success_cases)
def test_test_order_md5_success(db_conn,config,test_users,logged_user_client,success_cases):
    allure.dynamic.title(success_cases['name'])
    print(success_cases['name'])
    #获取url
    env = config['env']
    create_order_md5_url = config['environments'][env]['user']['create_order_md5_url']
    #获取默认有效用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    #拼装签名数据
    data = success_cases['input']
    api_secret = render_placeholders(success_cases['signature']['secret'],context)
    public_key = render_placeholders(success_cases['signature']['key_id'],context)
    signature = md5_signature(api_secret,data)
    params ={**data,"public_key":public_key,"signature":signature}
    #发起请求
    response = logged_user_client[username].post(create_order_md5_url,json=params)
    #断言
    with allure.step("校验响应状态码"):
        actual_value = response.status_code
        expected_value =success_cases['expected']['status_code']
        log_assertion(success_cases['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value == expected_value,f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验金额"):
        actual_value = response.json()['amount']
        expected_value = success_cases['expected']['amount']
        log_assertion(success_cases['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step('数据库断言：订单数据已写入'):
        row =db_conn.execute("select order_id,username,amount,currency,order_type,product_id,status,created_at from orders where  order_id =?  ",(response.json()['order_id'],)).fetchone()
        assert row is not None,"数据库无该订单信息"

        actual_value = row['username']
        expected_value = username
        log_assertion(success_cases['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value,f"数据库实际：{actual_value}，期望：{expected_value}"



@pytest.mark.parametrize('fail_cases',fail_cases)
def test_test_order_md5_fail(config,test_users,logged_user_client,fail_cases):
    allure.dynamic.title(fail_cases['name'])
    print(fail_cases['name'])
    #获取url
    env = config['env']
    create_order_md5_url = config['environments'][env]['user']['create_order_md5_url']
    #获取默认有效用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    #拼装签名数据
    data = fail_cases['input']
    api_secret = render_placeholders(fail_cases['signature']['secret'],context)
    public_key = render_placeholders(fail_cases['signature']['key_id'],context)
    signature = md5_signature(api_secret,data)
    params ={**data,"public_key":public_key,"signature":signature}
    #发起请求
    response = logged_user_client[username].post(create_order_md5_url,json=params)
    #断言
    with allure.step("校验响应状态码"):
        actual_value = response.status_code
        expected_value =fail_cases['expected']['status_code']
        log_assertion(fail_cases['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value == expected_value,f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验响应消息"):
        actual_value = response.json()['error']
        expected_value = fail_cases['expected']['error']
        log_assertion(fail_cases['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
