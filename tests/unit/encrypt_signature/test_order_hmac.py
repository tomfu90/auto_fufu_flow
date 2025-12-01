# coding = utf-8
# author = fufu
import os,sys,json

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_dir)
from libs.signature import hmac_signature
import pytest
import allure
from libs.utils import load_yaml
from libs.logger import log_assertion
import time,uuid
from libs.utils import render_placeholders
cases = load_yaml('data/order/test_order_hmac.yaml')
success_cases =cases['test_cases']['success_cases']
fail_cases =cases['test_cases']['fail_cases']

#获取环境变量——签名秘钥：en.hmac_key + en.hmac_secret
context = {
    "en": {
        "hmac_key": os.getenv("hmac_key"),
        "hmac_secret": os.getenv("hmac_secret")
    }
}

@pytest.mark.parametrize('case', success_cases)
def test_test_order_hmac_success(db_conn,config,default_user,logged_user_client,case):
    # 设置allure标题
    allure.dynamic.title(case['name'])
    # 设置输出框标题
    print(case['name'])
    #获取默认请求用户
    username = default_user
    #获取url
    env = config['env']
    create_order_hmac_url = config['environments'][env]['user']['create_order_hmac_url']
    # 构建测试数据
    body=case['input'] #测试用例输出-body
    # 将body 字典改为原始字符串，调用json.dumps, 以防服务器解析签名错误
    body_str = json.dumps(body,separators=(',',':'),ensure_ascii=False)
    api_key = render_placeholders(case['signature']['key_id'],context) #测试用例-签名参数
    api_secret =render_placeholders(case['signature']['secret'], context) #测试用例-签名参数
    # 调用签名方法，返回临时请求头
    headers =hmac_signature(
        api_key = api_key,
        api_secret = api_secret,
        method = 'POST',
        path = create_order_hmac_url,
        query_params = None,
        body = body_str,
        timestamp ='',
        nonce=''
    )
    #再构建临时请求头，不调用json=body,这个会修改body内容（空格之类），签名严格排序的
    headers.update({"Content-Type":"application/json"})
    # 发起请求，会调用session.header 和临时请求头，用data传递原始字符串
    resp = logged_user_client[username].post(create_order_hmac_url,data=body_str,headers=headers)
    # 断言校验
    with allure.step("响应校验：状态码"):
        actual_value = resp.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value==expected_value,f"实际：{actual_value}!=预期：{expected_value}"
    with allure.step("响应校验：金额"):
        actual_value = resp.json()['amount']
        expected_value = case['expected']['amount']
        log_assertion(case['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value==expected_value,f"实际：{actual_value}!=预期：{expected_value}"
    with allure.step("响应校验：数据库核对"):
        row = db_conn.execute(
            "select order_id,username,amount,currency,order_type,product_id,status,created_at from orders where  order_id =?  ",
            (resp.json()['order_id'],)).fetchone()
        assert row is not None, "数据库无该订单信息"
        # 定义数据库需要校验的字段
        fields_to_check = ['amount', 'product_id']
        actual_value = {filed: row[filed] for filed in fields_to_check}
        expected_value = {filed: case['expected'][filed] for filed in case['expected']  if filed!='status_code'}
        log_assertion(case['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value == expected_value ,f"数据库字段校验失败，实际：{actual_value}!=预期：{expected_value}"



@pytest.mark.parametrize('case', fail_cases)
def test_test_order_hmac_fail(db_conn,config,default_user,logged_user_client,case):
    # 设置allure标题
    allure.dynamic.title(case['name'])
    # 设置输出框标题
    print(case['name'])
    #获取默认请求用户
    username = default_user
    #获取url
    env = config['env']
    create_order_hmac_url = config['environments'][env]['user']['create_order_hmac_url']
    # 构建测试数据
    body=case['input'] #测试用例输出-body
    # 将body 字典改为原始字符串，调用json.dumps, 以防服务器解析签名错误
    body_str = json.dumps(body,separators=(',',':'),ensure_ascii=False)
    api_key = render_placeholders(case['signature']['key_id'],context) #测试用例-签名参数
    api_secret =render_placeholders(case['signature']['secret'], context) #测试用例-签名参数
    # 获取签名类型
    signature_mode =case['signature']['signature_mode']
    # 场景1 非时序攻击和重放攻击，都可以走下面的流程：包含签名错误
    if signature_mode  in('valid_secret','invalid_secret','invalid_key_id','empty_key_id'):
        # 调用签名方法，返回临时请求头
        headers =hmac_signature(
            api_key = api_key,
            api_secret = api_secret,
            method = 'POST',
            path = create_order_hmac_url,
            query_params = None,
            body = body_str,
            timestamp ='',
            nonce=''
        )
        #再构建临时请求头，不调用json=body,这个会修改body内容（空格之类），签名严格排序的
        headers.update({"Content-Type":"application/json"})
        # 发起请求，会调用session.header 和临时请求头，用data传递原始字符串
        resp = logged_user_client[username].post(create_order_hmac_url,data=body_str,headers=headers)
    # 场景2 时序攻击
    if signature_mode == 'expired_timestamp':
        old_timestamp = str(int(time.time()) - 3600)  # 3600 = 1小时 ，服务器允许5分钟
        # 调用签名方法，返回临时请求头
        headers =hmac_signature(
            api_key = api_key,
            api_secret = api_secret,
            method = 'POST',
            path = create_order_hmac_url,
            query_params = None,
            body = body_str,
            timestamp =old_timestamp,  # 签名方法timestamp 默认为空，现在传入过期很久的日期
            nonce=''
        )
        #再构建临时请求头，不调用json=body,这个会修改body内容（空格之类），签名严格排序的
        headers.update({"Content-Type":"application/json"})
        # 发起请求，会调用session.header 和临时请求头，用data传递原始字符串
        resp = logged_user_client[username].post(create_order_hmac_url,data=body_str,headers=headers)
    # 场景3 重放攻击
    if signature_mode == 'replay_attack':
        # 调用签名方法，返回临时请求头
        headers =hmac_signature(
            api_key = api_key,
            api_secret = api_secret,
            method = 'POST',
            path = create_order_hmac_url,
            query_params = None,
            body = body_str,
            timestamp ='',  # 签名方法timestamp 默认为空，现在传入过期很久的日期
            nonce=''
        )
        #再构建临时请求头，不调用json=body,这个会修改body内容（空格之类），签名严格排序的
        headers.update({"Content-Type":"application/json"})
        # 发起请求，会调用session.header 和临时请求头，用data传递原始字符串
        resp1 = logged_user_client[username].post(create_order_hmac_url,data=body_str,headers=headers)
        # 间隔1s，相同请求再次发送，重放攻击
        time.sleep(1)
        resp = logged_user_client[username].post(create_order_hmac_url, data=body_str, headers=headers)
    # 场景4 篡改签名数据
    if signature_mode == 'tampered_body':
        # 调用签名方法，返回临时请求头
        headers = hmac_signature(
            api_key=api_key,
            api_secret=api_secret,
            method='POST',
            path=create_order_hmac_url,
            query_params=None,
            body=body_str,
            timestamp='',
            nonce='',
        )
        # 再构建临时请求头，不调用json=body,这个会修改body内容（空格之类），签名严格排序的
        headers.update({"Content-Type": "application/json"})
        # 构造篡改后数据：
        tampered_body=case['input'].copy()
        tampered_body["amount"] = 9999  # 篡改！
        tampered_body_str = json.dumps(tampered_body, separators=(',', ':'), ensure_ascii=False)
        resp = logged_user_client[username].post(create_order_hmac_url, data=tampered_body_str, headers=headers)



    # 断言校验
    with allure.step("响应校验：状态码"):
        actual_value = resp.status_code
        expected_value = case['expected']['status_code']
        log_assertion(case['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value==expected_value,f"实际：{actual_value}!=预期：{expected_value}"
    with allure.step("响应校验：错误信息"):
        actual_value = resp.json()['error']
        expected_value = case['expected']['error']
        log_assertion(case['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value==expected_value,f"实际：{actual_value}!=预期：{expected_value}"


