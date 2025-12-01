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

from tests.unit.purchase.schemas import  validate_test_cases
#获取用例
data_file = "data/order/test_create_purchase_order.yaml"
success_cases = load_yaml(data_file)['test_cases']['success_cases']
fail_cases = load_yaml(data_file)['test_cases']['fail_cases']
#检查yaml格式和输入内容是否合法：
validate_test_cases(success_cases, case_type="success")
validate_test_cases(fail_cases, case_type="fail")
#参数化 驱动，2个参数
param_success = [(case, case["listing_scenario"]) for case in success_cases]
param_fail = [ (case, case["listing_scenario"]) for case in fail_cases]


def calulate_purchase_order(dynamic,amount,purchase_amount):
    """
    抽离yaml用例，金额计算逻辑
    amount :: conftest fixture 返的前置构造挂单收据 {"listing_id": listing_id, "amount": amount}
    purchase_amount :: 测试用例yaml 里的 purchase_amount
    """
    # 场景1 ：购买金额=挂单金额 ，对应yaml 2个字段 ：dynamic= False & purchase_amount= "total"
    if not dynamic and purchase_amount=="total":
        return amount
    # 场景2 ：购买金额=挂单金额 减少/增加 （超买/部分购买），对应yaml 2个字段 ：dynamic= True & purchase_amount ！= "total"
    if  dynamic and purchase_amount != "total":
        return amount+purchase_amount
    # 场景3: 购买金额任意输入，跟挂单金额没关系，对应yaml 2个字段 ：dynamic= False & purchase_amount ！= "total"
    if not dynamic and purchase_amount != "total":
        return purchase_amount


@pytest.mark.parametrize("case,prepare_listing_by_scenario", param_success,indirect=["prepare_listing_by_scenario"])
def test_create_purchase_order_success(db_conn,config,default_user,logged_user_client,case,prepare_listing_by_scenario):
    allure.dynamic.title(case['name'])
    allure.dynamic.description(case['description'])
    print(case['name'])
    # 获取url
    env = config['env']
    create_purchase_order_url = config['environments'][env]['user']['create_purchase_order_url']
    # 获取测试数据
    # prepare_listing_by_scenario 返回格式：{"listing_id": listing_id, "amount": amount}
    # 购买下单接口 请求body：{"listing_id": listing_id, "purchase_amount": purchase_amount}
    data ={
        "listing_id": prepare_listing_by_scenario['listing_id'],
        "purchase_amount": calulate_purchase_order(case['dynamic'],prepare_listing_by_scenario['amount'],case['purchase_amount'])
    }
    resp = logged_user_client[default_user].post(create_purchase_order_url, json=data)
    # 断言
    with allure.step("校验响应状态码"):
        actual_value = resp.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验响应"):
        actual_value = resp.json()['message']
        expected_value = case['expected']['message']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step('数据库断言：数据库已修改'):
        row = db_conn.execute("""
                SELECT id, buyer_username, status,amount
                FROM purchase_orders
                WHERE id = ?
            """, (resp.json()['order_id'],)).fetchone()
        assert row is not None, "数据库无该订单信息"
        #数据库多字段校验
        fileds = ['amount','status','id']
        actual_value = {filed: row[filed] for filed in fileds}
        expected_value = {
            'amount':resp.json()['amount'],
            'status':case['expected']['status'],
            'id': resp.json()['order_id']
        }
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"数据库字段校验失败，实际：{actual_value}!=预期：{expected_value}"


@pytest.mark.parametrize("case,prepare_listing_by_scenario", param_fail,indirect=["prepare_listing_by_scenario"])
def test_cancel_listing_fail(db_conn, default_user, config, logged_user_client, case,prepare_listing_by_scenario):
    allure.dynamic.title(case['name'])
    allure.dynamic.description(case['description'])
    print(case['name'])
    # 获取url
    env = config['env']
    create_purchase_order_url = config['environments'][env]['user']['create_purchase_order_url']
    data = {
        "listing_id": prepare_listing_by_scenario['listing_id'],
        "purchase_amount": calulate_purchase_order(case['dynamic'], prepare_listing_by_scenario['amount'],case['purchase_amount'])
    }

    #重复购买场景
    if case.get('duplicate') == True:
        response = logged_user_client[default_user].post(create_purchase_order_url, json=data)
        assert response.status_code == 201
    response = logged_user_client[default_user].post(create_purchase_order_url, json=data)
    # 断言
    with allure.step("校验响应状态码"):
        actual_value = response.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验响应"):
        actual_value = response.json()['error']
        expected_value = case['expected']['error']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"

