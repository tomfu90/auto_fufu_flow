# coding = utf-8
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

data_file = "data/order/test_cancel_listing.yaml"
success_cases = load_yaml(data_file)['test_cases']['success_cases']
fail_cases = load_yaml(data_file)['test_cases']['fail_cases']

@pytest.mark.parametrize('case', success_cases)
def test_cancel_listing_success(db_conn,config,sell_user,logged_user_client,prepare_listing,case):
    allure.dynamic.title(case['name'])
    allure.dynamic.description(case['description'])
    print(case['name'])
    # 获取url
    env = config['env']
    cancel_listing_url = config['environments'][env]['user']['cancel_listing_url']
    #获取挂单id
    mark= case['mark']
    listing_id = prepare_listing(mark)
    data ={'listing_id' : listing_id}
    # 发起请求
    response = logged_user_client[sell_user].post(cancel_listing_url, json=data)
    # 断言
    with allure.step("校验响应状态码"):
        actual_value = response.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step("校验响应"):
        actual_value = response.json()['message']
        expected_value = case['expected']['message']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际{actual_value} != 预期{expected_value}"
    with allure.step('数据库断言：数据库已修改'):
        row = db_conn.execute("""
            SELECT id, seller_username, status
            FROM listings
            WHERE id = ?
        """, (listing_id,)).fetchone()
        assert row is not None, "数据库无该订单信息"

        actual_value = row['status']
        expected_value = case['expected']['status']
        log_assertion(case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"数据库字段校验失败，实际：{actual_value}!=预期：{expected_value}"


@pytest.mark.parametrize('case', fail_cases)
def test_cancel_listing_fail(db_conn,default_user,config,sell_user,logged_user_client,prepare_listing,case):
    allure.dynamic.title(case['name'])
    allure.dynamic.description(case['description'])
    print(case['name'])
    # 获取url
    env = config['env']
    #取消挂单url
    cancel_listing_url = config['environments'][env]['user']['cancel_listing_url']
    #获取测试用例对应场景标志位
    mark= case['mark']
    data = {"listing_id" : prepare_listing(mark) }


    response = logged_user_client[sell_user].post(cancel_listing_url, json=data)
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
