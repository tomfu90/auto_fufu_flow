#coding = utf-8
#author =fufu
import pytest
from pathlib import Path
import allure
import sys
#获取项目根目录
root_dir = Path(__file__).parent.parent
sys.path.insert(0,str(root_dir))
from libs.logger import log_assertion
from libs.utils import  load_yaml
from tests.unit.back_update_balance.schemas import validate_order_test_cases
data_file = "data/balance/test_back_update_balance.yaml"
#检查yaml格式和输入内容是否合法：
validate_order_test_cases(load_yaml(data_file))
success_cases = load_yaml(data_file)['success_cases']
fail_cases = load_yaml(data_file)['fail_cases']
# 加载全部用例（保持 YAML 顺序）
all_cases = success_cases + fail_cases
# 生成有序 ID（保持原始顺序）
case_ids = [f"{i:02d}_{case['name']}" for i,case in enumerate(all_cases)]

@pytest.mark.parametrize("case", all_cases,ids=case_ids)
def test_back_update_balance_add(case,logged_back_client,back_admin_user,back_normal_user,register_username,admin_update_balance_url,db_conn):
    allure.dynamic.title(case['name'])
    allure.dynamic.title(case['description'])
    print(case['name'])
    mark = case["input"]["mark"]
    amount = case["input"]["amount"]
    # 1 动态准备username
    if mark in ["add","sub","add_no_permit","sub_no_permit"]:
        username = register_username
        if mark in ["sub", "sub_no_permit"]:
            # 先充值 200，确保可以扣减
            resp_data = {"username":username,"amount":200}
            resp = logged_back_client[back_admin_user].post(admin_update_balance_url,json=resp_data)
            assert resp.status_code == 200
    elif mark == "null_username":
        username = None
    elif mark == "nonexist_username":
        username = "nonexist_username"
    else:
        raise ValueError(f"Unknown mark: {mark}")
    # 2 准备请求数据
    data = {"username": username, "amount": amount}
    # 3 选择客户端（权限控制）
    if mark in ["add_no_permit","sub_no_permit"]:
        client = logged_back_client[back_normal_user] #非admin管理员
    else:
        client = logged_back_client[back_admin_user]  #admin管理员
    # 4 询数据库用户初始余额:amount_begin ,先排除不存在用户
    if mark not in ["null_username", "nonexist_username"]:
        row = db_conn.execute("""
                        SELECT username,balance
                        FROM accounts
                        WHERE username = ?
                    """, (data['username'],)).fetchone()
        assert row is not None, f"数据库账户表无该用户数据{data['username']}"
        amount_begin =row["balance"]
    # 5. 发起请求
    resp = client.post(admin_update_balance_url,json=data)
    # 6状态码断言，通用
    with allure.step("校验响应状态码"):
        actual_value = resp.status_code
        expected_value = case['expected']['status_code']
        log_assertion(f"{case['name']}-状态码校验", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"状态码校验：实际{actual_value} != 预期{expected_value}"
    # 7 成功分支，断言
    if resp.json().get('success'):
        with allure.step("校验响应:success"):
            actual_value = resp.json()['success']
            expected_value = case['expected']['success']
            log_assertion(f"{case['name']}-success校验", actual_value == expected_value, actual_value, expected_value)
            assert actual_value == expected_value, f"success校验：实际{actual_value} != 预期{expected_value}"
        #db断言 -查询期末余额
        with allure.step('数据库断言：accounts表期末余额比对'):
            row = db_conn.execute("""
                    SELECT username,balance
                    FROM accounts
                    WHERE username = ?
                """, (data['username'],)).fetchone()
            assert row is not None,  f"数据库账户表无该用户数据{data['username']}"
            actual_value = row['balance']  #数据库表期末余额
            expected_value = case['expected']['adjustment'] + amount_begin  #预期期末：期初+账变（调整金额）
            log_assertion(f"{case['name']}-数据库校验", actual_value == expected_value , actual_value, expected_value)
            assert actual_value == expected_value , f"accounts表期末余额校验：实际期末：{actual_value}!=预期期末：{expected_value}"
    # 8 失败分支，断言
    else:
        with allure.step("校验响应:error"):
            actual_value = resp.json()['error']
            expected_value = case['expected']['error']
            log_assertion(f"{case['name']}-error", actual_value == expected_value, actual_value, expected_value)
            assert actual_value == expected_value, f"error：实际{actual_value} != 预期{expected_value}"




