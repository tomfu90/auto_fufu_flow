# coding = utf-8
# author = fufu
# 查看账户金额 和账户流水测试用例
import allure
import random
import sys
from pathlib import Path
# 设置模块导入路径
project_dir = Path(__file__).parent.parent
sys.path.insert(0, str(project_dir))
from libs.logger import log_assertion
from libs.utils import  load_yaml

def test_get_balance_sucess(config,logged_user_client,test_users,db_conn):
    ''' 查看账户金额'''
    #获取url
    env = config['env']
    get_balance_url = config['environments'][env]['user']['get_balance_url']
    #设置allure请求标题
    allure.dynamic.title("查看账户金额")
    #发起请求
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    resp = logged_user_client[username].get(get_balance_url)
    with allure.step("校验响应状态码"):
        actual_value = resp.status_code
        expected_value = 200
        log_assertion("查看账户金额",actual_value==expected_value,actual_value,expected_value)
        assert actual_value == expected_value,f"实际:{actual_value},预期{expected_value}"

    with allure.step("数据库校验账户余额"):
        row = db_conn.execute("select balance from accounts where username =? ",(username,)).fetchone()
        log_assertion("查看账户金额", row is not None, message="数据库该账户余额查询不到")
        assert row is not None,f"数据库该账户余额查询不到"
        actual_value = resp.json()['balance']
        expected_value = row['balance']
        log_assertion("查看账户金额", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"接口响应:{actual_value},数据库：{expected_value}"


def test_get_transactions_sucess(config,logged_user_client,test_users,db_conn):
    '''查看交易流水'''
    env = config['env']
    get_transactions_url = config['environments'][env]['user']['get_transactions_url']
    # 设置allure请求标题
    allure.dynamic.title("查看交易流水")
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    # 发起请求
    resp = logged_user_client[username].get(get_transactions_url)
    with allure.step("校验响应状态码"):
        actual_value = resp.status_code
        expected_value = 200
        log_assertion("查看交易流水", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际:{actual_value},预期{expected_value}"
    with allure.step("数据库校验流水"):
        rows = db_conn.execute("select id,username,type,amount,time from transactions where username =?  order by time desc", (username,)).fetchall()
        # 接口返回条数和数据库返回条数是否相同
        actual_value = len(resp.json()['transactions'])
        expected_value =  len(rows)
        log_assertion("查看交易流水", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"
        # 接口返回的数据是否都存在数据库中"id:amount"对比，不对比所有字段，部分关键字段比对
        actual_value = {":".join([item['id'],str(item['amount'])]) for item in resp.json()['transactions']}
        expected_value = {":".join([row['id'],str(row['amount'])]) for row in rows}
        log_assertion("查看交易流水", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"

def test_get_order_sucess(config,logged_user_client,test_users,db_conn):
    '''查看订单记录：有记录；要先创建订单，才能查询订单'''
    env = config['env']
    #获取创建订单接口
    create_api_orders_url = config['environments'][env]['user']['create_api_orders_url']
    #获取查询订单接口url，需要传入动态参数
    get_order_url_template = config['environments'][env]['user']['get_order_url']
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    #取第一个有效订单创建数据:create_order_success.yaml
    datas = load_yaml( 'data/order/create_order_success.yaml')['test_cases'][0]
    data = datas['input']
    # 创建订单请求数据
    # 发起创建订单请求
    resp1 = logged_user_client[username].post(create_api_orders_url, json=data)
    #断言创建订单请求成功
    with allure.step("校验状态码"):
        actual_value = resp1.status_code
        expected_value = datas['expected']['status_code']
        log_assertion("创建订单", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value,f"实际:{actual_value},预期：{expected_value}"
    with allure.step("校验创建订单金额"):
        actual_value = resp1.json()['amount']
        expected_value = datas['expected']['amount']
        log_assertion("创建订单", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value,f"实际:{actual_value},预期：{expected_value}"
    # 查询订单id
    order_id = resp1.json()['order_id']
    # 获取查询订单-完整url-传入创建订单的订单id
    get_order_url = get_order_url_template.format(order_id=order_id)
    # 发起查看交易流水请求
    resp2 = logged_user_client[username].get(get_order_url)
    with allure.step("校验状态码"):
        actual_value = resp2.status_code
        expected_value = 200
        log_assertion("查看订单记录", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际:{actual_value},预期{expected_value}"
    with allure.step("校验查询订单id"):
        actual_value = resp2.json()['order_id']
        expected_value = order_id
        log_assertion("查看订单记录", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际:{actual_value},预期{expected_value}"
    with allure.step("数据库校验查询订单金额"):
        row = db_conn.execute("select order_id,amount from orders where order_id =? ", (order_id,)).fetchone()
        log_assertion("查看订单记录", row is not None, message=f"数据库查询不到该订单{order_id}")
        assert row is not None,f"数据库查询不到该订单:{order_id}"
        actual_value = resp2.json()['amount']
        expected_value = row['amount']
        log_assertion("查看订单记录", actual_value == expected_value, actual_value, expected_value)
        assert  actual_value == expected_value, f"实际:{actual_value},预期{expected_value}"





def test_get_order_fail_404(config,logged_user_client,test_users):
    '''查看订单记录：无记录'''
    env = config['env']
    #获取配置url，需要传入动态参数
    get_order_url_template = config['environments'][env]['user']['get_order_url']
    order_id = random.randint(1000, 9999) #动态参数
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    get_order_url = get_order_url_template.format(order_id=order_id) #获取完整url
    resp = logged_user_client[username].get(get_order_url)
    with allure.step("校验状态码"):
        assert resp.status_code == 404,f"实际:{resp.status_code},预期：404"




if __name__ == '__main__':
    pytest.main(['-s', '-v'])


