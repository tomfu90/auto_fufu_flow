# coding = utf-8
# author = fufu

import pytest
from pathlib import Path
import yaml
import allure
import sys
#获取项目根目录
root_dir = Path(__file__).parent.parent
sys.path.insert(0,str(root_dir))

from libs.logger import log_assertion

from libs.utils import  load_yaml



data_file = "data/order/create_order_success.yaml"
test_cases = load_yaml(data_file)['test_cases']

@pytest.mark.smoke
@pytest.mark.parametrize('create_order_success_case', test_cases)
def test_create_order_success(config, test_users, logged_user_client,db_conn,create_order_success_case):
    '''创建订单成功'''
    print(f"\n{create_order_success_case['name']} ")
    #动态设置allure中的用例名称
    allure.dynamic.title(create_order_success_case['name'])
    env = config['env']
    create_api_orders_url = config['environments'][env]['user']['create_api_orders_url'] #获取对应url
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    #发起请求-创建订单
    resp = logged_user_client[username].post(create_api_orders_url, json=create_order_success_case['input'])
    #allure记录断言
    with allure.step('响应校验：状态码'):
        actual_value = resp.status_code
        expected_value = create_order_success_case['expected']['status_code']
        log_assertion(create_order_success_case['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value == expected_value,f"实际：{actual_value}，期望：{expected_value}"

    with allure.step('响应校验：金额'):
        actual_value = resp.json()['amount']
        expected_value = create_order_success_case['expected']['amount']
        log_assertion(create_order_success_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value,f"实际：{actual_value}，期望：{expected_value}"

    with allure.step('数据库断言：订单数据已写入'):
        row =db_conn.execute("select order_id,username,amount,currency,order_type,product_id,status,created_at from orders where  order_id =?  ",(resp.json()['order_id'],)).fetchone()
        assert row is not None,"数据库无该订单信息"

        actual_value = row['username']
        expected_value = username
        log_assertion(create_order_success_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value,f"数据库实际：{actual_value}，期望：{expected_value}"

        actual_value = row['amount']
        expected_value = create_order_success_case['expected']['amount']
        log_assertion(create_order_success_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"数据库实际：{actual_value}，期望：{expected_value}"




data_file = "data/order/create_order_validation.yaml"
test_cases = load_yaml(data_file)['test_cases']

@pytest.mark.parametrize('create_order_validation_case', test_cases)
def test_create_order_validation(config, test_users, logged_user_client,create_order_validation_case,db_conn):
    '''创建订单失败'''
    print(f"\n{create_order_validation_case['name']} ")
    # 动态设置allure中的用例名称
    allure.dynamic.title(create_order_validation_case['name'])
    env = config['env']
    create_api_orders_url = config['environments'][env]['user']['create_api_orders_url'] #获取对应url
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    #查询当前用户余额：
    row = db_conn.execute(" select balance from accounts where username =?  ",(username,)).fetchone()
    balance = row['balance']
    print(f"{username}:{balance} ")
    #发起请求-创建订单
    resp = logged_user_client[username].post(create_api_orders_url,  json=create_order_validation_case['input'])
    with allure.step('校验响应'):
        actual_value = resp.status_code
        expected_value = create_order_validation_case['expected']['status_code']
        log_assertion(create_order_validation_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value}，期望：{expected_value}"

        actual_value = resp.json()['error']
        expected_value =  create_order_validation_case['expected']['error']
        log_assertion(create_order_validation_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value},期望：{expected_value}"








