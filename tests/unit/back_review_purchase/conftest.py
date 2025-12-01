# coding =utf-8
# author =fufu

import random
import pytest

#先抽取url
@pytest.fixture()
def create_listing_url(config):
    """挂单接口url"""
    env = config['env']
    create_listing_url = config['environments'][env]['user']['create_listing_url']
    return create_listing_url

@pytest.fixture()
def create_purchase_order_url(config):
    """购买接口url"""
    env = config['env']
    create_purchase_order_url = config['environments'][env]['user']['create_purchase_order_url']
    return create_purchase_order_url

@pytest.fixture()
def review_purchase_order_url(config):
    """后台审批订单接口url"""
    env = config['env']
    review_purchase_order_url = config['environments'][env]['back']['review_purchase_order_url']
    return review_purchase_order_url




# mark 代表场景标志位和fixture对应关系：
# 1  fixture: exist_order         对应yaml     exist         代表挂单存在
# 2  fixture: null_id_order       对应yaml     null_id       代表挂单为空
# 3  fixture: nonexistent_order   对应yaml     nonexistent   代表挂单不存在
# 4  fixture: canceled_order      对应yaml     canceled      代表挂单已取消
# 5  fixture: complete_order      对应yaml     complete      代表挂单已完成

@pytest.fixture()
def null_id_order():
    """挂单为空"""
    return None

@pytest.fixture()
def nonexistent_order():
    """挂单不存在"""
    return 9999999 #不存在的数据


@pytest.fixture()
def exist_order(sell_user,default_user,db_conn,logged_user_client,create_listing_url,create_purchase_order_url):
    """正常的撮合订单（购买匹配挂单）"""
    # 1 构建挂单请求数据
    product_id = f"AUTO{random.randint(1000, 9999)}"
    data = {
        "product_id": product_id,
        "amount": 100,
        "currency": "CNY"
    }
    # 2 sell_user发起挂单
    resp = logged_user_client[sell_user].post(create_listing_url, json=data)
    assert resp.status_code == 201
    listing_id = resp.json()['listing_id']
    # 3 发起购买请求数据
    listing = db_conn.execute("""
                                    SELECT amount
                                    FROM listings
                                    WHERE id = ?
                                """, (listing_id,)).fetchone()
    purchase_amount = listing['amount']
    # 4 default_user 默认用户去全部购买：default_user
    buy_data = {
        'listing_id': listing_id,
        "purchase_amount": purchase_amount
    }
    resp = logged_user_client[default_user].post(create_purchase_order_url, json=buy_data)
    assert resp.status_code == 201
    return resp.json()['order_id']

@pytest.fixture()
def complete_order(sell_user,default_user,db_conn,back_admin_user,logged_back_client,
                   logged_user_client,create_listing_url,create_purchase_order_url,review_purchase_order_url):
    """已完成挂单订单（已经审批通过）"""
    # 1 构建挂单请求数据
    product_id = f"AUTO{random.randint(1000, 9999)}"
    data = {
        "product_id": product_id,
        "amount": 100,
        "currency": "CNY"
    }
    # 2 sell_user发起挂单
    resp = logged_user_client[sell_user].post(create_listing_url, json=data)
    assert resp.status_code == 201
    listing_id = resp.json()['listing_id']
    # 3 发起购买请求数据
    listing = db_conn.execute("""
                                    SELECT amount
                                    FROM listings
                                    WHERE id = ?
                                """, (listing_id,)).fetchone()
    purchase_amount = listing['amount']
    # 4 default_user 默认用户去全部购买：default_user
    buy_data = {
        'listing_id': listing_id,
        "purchase_amount": purchase_amount
    }
    resp = logged_user_client[default_user].post(create_purchase_order_url, json=buy_data)
    assert resp.status_code == 201
    #5 后台admin用户审批通过
    #构造审批通过请求数据
    data ={
        'order_id': resp.json()['order_id'],
        "action": "approve"
    }
    resp = logged_back_client[back_admin_user].post(review_purchase_order_url, json=data)
    assert resp.status_code == 200
    return resp.json()['order_id']

@pytest.fixture()
def canceled_order(sell_user,default_user,db_conn,back_admin_user,logged_back_client,
                   logged_user_client,create_listing_url,create_purchase_order_url,review_purchase_order_url):
    """已取消挂单订单（已经审批拒绝）"""
    # 1 构建挂单请求数据
    product_id = f"AUTO{random.randint(1000, 9999)}"
    data = {
        "product_id": product_id,
        "amount": 100,
        "currency": "CNY"
    }
    # 2 sell_user发起挂单
    resp = logged_user_client[sell_user].post(create_listing_url, json=data)
    assert resp.status_code == 201
    listing_id = resp.json()['listing_id']
    # 3 发起购买请求数据
    listing = db_conn.execute("""
                                    SELECT amount
                                    FROM listings
                                    WHERE id = ?
                                """, (listing_id,)).fetchone()
    purchase_amount = listing['amount']
    # 4 default_user 默认用户去全部购买：default_user
    buy_data = {
        'listing_id': listing_id,
        "purchase_amount": purchase_amount
    }
    resp = logged_user_client[default_user].post(create_purchase_order_url, json=buy_data)
    assert resp.status_code == 201
    #5 后台admin用户审批通过
    #构造审批拒绝请求数据
    data ={
        'order_id': resp.json()['order_id'],
        "action": "reject"
    }
    resp = logged_back_client[back_admin_user].post(review_purchase_order_url, json=data)
    assert resp.status_code == 200
    return resp.json()['order_id']


#----------场景路由-----------
@pytest.fixture()
def prepare_order(request,
                exist_order,
                null_id_order,
                nonexistent_order,
                canceled_order,
                complete_order
                  ):
    mark =request.param
    map = {
        "exist": exist_order,
        "null_id": null_id_order,
        "nonexistent": nonexistent_order,
        "canceled": canceled_order,
        "complete": complete_order
    }

    if mark not in map:
        raise ValueError(f"{mark} not in map")
    return map[mark]