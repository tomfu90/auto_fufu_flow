#coding = utf-8
# author = fufu

import pytest
from pathlib import Path
import allure
import sys
#获取项目根目录
root_dir = Path(__file__).parent.parent
sys.path.insert(0,str(root_dir))
from libs.logger import log_assertion
from libs.utils import  load_yaml

data_file = "data/order/test_create_listing.yaml"
success_cases = load_yaml(data_file)['test_cases']['success_cases']
fail_cases = load_yaml(data_file)['test_cases']['fail_cases']

@pytest.mark.smoke
@pytest.mark.parametrize('case', success_cases)
def test_create_listing_success(db_conn,test_users,config,logged_user_client,case):
    allure.dynamic.title(case['name'])
    print(case['name'])
    # 获取url
    env = config['env']
    create_listing_url = config['environments'][env]['user']['create_listing_url']
    # 获取客户端role=sell的有效用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "sell")
    username = user_cred['username']
    #发起请求
    response = logged_user_client[username].post(create_listing_url, json=case['input'])
    # 断言
    with allure.step("校验响应状态码"):
        actual_value = response.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验金额"):
        actual_value = response.json()['amount']
        expected_value = case['expected']['amount']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step('数据库断言：订单数据已写入'):
        row = db_conn.execute(
            "select seller_username,amount,currency,product_id,created_at,status from listings where  product_id =? ",
            (response.json()['product_id'],)).fetchone()
        assert row is not None, "数据库无该订单信息"
        # 定义数据库需要校验的字段
        fields_to_check = ['amount', 'product_id']
        actual_value = {filed: row[filed] for filed in fields_to_check}
        expected_value = {filed: case['expected'][filed] for filed in case['expected'] if filed != 'status_code'}
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"数据库字段校验失败，实际：{actual_value}!=预期：{expected_value}"

@pytest.mark.parametrize('case', fail_cases)
def test_create_listing_fail(config, test_users, logged_user_client, case):
    allure.dynamic.title(case['name'])
    print(case['name'])
    # 获取url
    env = config['env']
    create_listing_url = config['environments'][env]['user']['create_listing_url']
    # 获取客户端role=sell的有效用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "sell")
    username = user_cred['username']
    #发起请求
    response = logged_user_client[username].post(create_listing_url, json=case['input'])
    # 断言
    with allure.step("校验响应状态码"):
        actual_value = response.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验响应消息"):
        actual_value = response.json()['error']
        expected_value = case['expected']['error']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"