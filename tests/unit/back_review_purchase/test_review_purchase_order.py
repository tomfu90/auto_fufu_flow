#coding = utf-8
#author = fufu

import pytest
from pathlib import Path
import allure
import sys
#获取项目根目录
root_dir = Path(__file__).parent.parent
sys.path.insert(0,str(root_dir))
from libs.logger import log_assertion
from libs.utils import  load_yaml
from tests.unit.back_review_purchase.schemas import  validate_order_test_cases

data_file = "data/order/back_review_purchase_order.yaml"
#检查yaml格式和输入内容是否合法：
validate_order_test_cases(load_yaml(data_file))
success_cases = load_yaml(data_file)['test_cases']['success_cases']
fail_cases = load_yaml(data_file)['test_cases']['fail_cases']
#参数化驱动，2个参数
param_success =[(case,case['input']['mark']) for case in success_cases]
param_fail =[(case,case['input']['mark']) for case in fail_cases]

@pytest.mark.parametrize("case,prepare_order", param_success,indirect=['prepare_order'])
def test_back_review_purchase_success(case,prepare_order,logged_back_client,back_admin_user,db_conn,review_purchase_order_url):
    allure.dynamic.title(case['name'])
    allure.dynamic.description(case['description'])
    print(case['name'])
    #构造测试数据
    data ={
        "order_id": prepare_order,
        "action": case['input']['action']
    }
    resp = logged_back_client[back_admin_user].post(review_purchase_order_url, json=data)
    with allure.step("校验响应状态码"):
        actual_value = resp.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验响应:action"):
        actual_value = resp.json()['action']
        expected_value = case['expected']['action']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    # db多表断言
    with allure.step('数据库断言：purchase_orders表已修改'):
        row = db_conn.execute("""
                SELECT id, listing_id,status
                FROM purchase_orders
                WHERE id = ?
            """, (resp.json()['order_id'],)).fetchone()
        assert row is not None, "数据库无该订单信息"
        #数据库多字段校验
        fileds = ['id','status']
        actual_value = {filed: row[filed] for filed in fileds}
        expected_value = {
            'id': resp.json()['order_id'],
            'status':case['expected']['status']
        }
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"purchase_orders表字段校验失败，实际：{actual_value}!=预期：{expected_value}"


@pytest.mark.parametrize("case,prepare_order", param_fail,indirect=['prepare_order'])
def test_back_review_purchase_fail(case,prepare_order,logged_back_client,back_normal_user,back_admin_user,review_purchase_order_url):
    allure.dynamic.title(case['name'])
    allure.dynamic.description(case['description'])
    print(case['name'])
    #构造测试数据
    data ={
        "order_id": prepare_order,
        "action": case['input']['action']
    }
    # 无权限管理员审批场景
    if case['input'].get('permit') and case['input'].get('permit')== "no_permit":
        resp = logged_back_client[back_normal_user].post(review_purchase_order_url, json=data)
    # 有权限管理员审批场景
    else:
        resp = logged_back_client[back_admin_user].post(review_purchase_order_url, json=data)
    with allure.step("校验响应状态码"):
        actual_value = resp.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验响应:error"):
        actual_value = resp.json()['error']
        expected_value = case['expected']['error']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"

