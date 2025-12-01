# tests/test_user_listing.py
# coding = utf-8
# author = fufu

import pytest
from pathlib import Path
import sys

# 获取项目根目录并加入 sys.path
root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from libs.utils import load_yaml
from libs.api_client import  Apiclient
import allure
from libs.logger import log_assertion
from tests.unit.search.schemas import validate_order_test_cases
# 加载测试数据
test_cases = load_yaml("data/search/test_search_listing.yaml")
#校验yaml格式
validate_order_test_cases(test_cases)

success_cases = test_cases["success_cases"]
fail_cases = test_cases["fail_cases"]
all_cases = success_cases + fail_cases
case_ids = [f"{i:02d}_{case['name']}" for i, case in enumerate(all_cases)]


@pytest.mark.parametrize("case", all_cases, ids=case_ids)
def test_get_listing(
    case,
    get_listing_url,
    logged_user_client,
    create_listing,
    default_user,      # 查询者（普通用户）
    sell_user,         # 挂单卖家（用于“本人挂单”）
    db_conn,
    base_url
):
    """
    测试 /api/listing 接口：
    - 成功：查询自己的挂单
    - 失败：参数错误、无权限、未认证等
    """

    mark = case["mark"]

    if mark == "no_token":
        client = Apiclient(base_url)
        json_data = {"listing_id": 123}
        resp = client.post(get_listing_url, json=json_data)
    elif mark == "invalid_token":
        client = Apiclient(base_url)
        client.session.headers["Authorization"] = "Bearer invalid_fake_token_123"
        json_data = {"listing_id": create_listing}
        resp = client.post(get_listing_url, json=json_data)
    elif mark == "other":
        # default_user查看sell_user发布挂单
        json_data = {"listing_id": create_listing}
        resp = logged_user_client[default_user].post(get_listing_url, json=json_data)
    elif mark == "null_id":
        json_data = {}  # 或 None，但 requests 会转为 {}
        resp = logged_user_client[default_user].post(get_listing_url, json=json_data)
    elif mark == "no_int":
        json_data = {"listing_id": "not_a_number"}
        resp = logged_user_client[default_user].post(get_listing_url, json=json_data)
    elif mark == "nonexistent":
        json_data = {"listing_id": 999999999}
        resp = logged_user_client[default_user].post(get_listing_url, json=json_data)
    elif mark == "exist":
        json_data = {"listing_id": create_listing}
        resp = logged_user_client[sell_user].post(get_listing_url, json={"listing_id": create_listing})
    else:
        raise ValueError(f"Unknown mark: {mark}")
    # 状态码断言，通用
    with allure.step("校验响应状态码"):
        actual_value = resp.status_code
        expected_value = case['expected']['status_code']
        log_assertion(f"{case['name']}-状态码校验", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"状态码校验：实际{actual_value} != 预期{expected_value}"
    #  成功分支，断言
    if resp.json().get('success'):
        with allure.step("校验响应:success"):
            actual_value = resp.json()['success']
            expected_value = case['expected']['success']
            log_assertion(f"{case['name']}-success校验", actual_value == expected_value, actual_value, expected_value)
            assert actual_value == expected_value, f"success校验：实际{actual_value} != 预期{expected_value}"
        #db断言 -查询期末余额
        with allure.step('数据库断言：listings查询数据'):
            row = db_conn.execute("""
                    SELECT id, seller_username, product_id, amount,status
                    FROM listings
                    WHERE id = ?
                """, (json_data['listing_id'],)).fetchone()
            assert row is not None,  f"数据库账户表无挂单数据{json_data['listing_id']}"
            #表多字段查询
            fields = ["id","seller_username","product_id","amount","status"]
            actual_value = {
                "id": resp.json()['data']['id'],
                "seller_username": resp.json()['data']['seller_username'],
                "product_id": resp.json()['data']['product_id'],
                "amount": resp.json()['data']['amount'],
                "status": resp.json()['data']['status']

            }
            expected_value = {field: row[field] for field in fields}
            log_assertion(f"{case['name']}-数据库校验", actual_value == expected_value , actual_value, expected_value)
            assert actual_value == expected_value , f"接口实际：{actual_value}!=数据库返回：{expected_value}"
    # 失败分支，断言
    else:
        with allure.step("校验响应:error"):
            actual_value = resp.json()['error']
            expected_value = case['expected']['error']
            log_assertion(f"{case['name']}-error", actual_value == expected_value, actual_value, expected_value)
            assert actual_value == expected_value, f"error：实际{actual_value} != 预期{expected_value}"


