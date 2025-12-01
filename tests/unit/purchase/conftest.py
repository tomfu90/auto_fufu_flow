#coding = utf-8
#auth= fufu

# #coding = utf-8
# #author = fufu
#
import pytest
import random

@pytest.fixture()
def listing_active_other(sell_user,config,logged_user_client,db_conn):
    """他人发布的有效挂单"""
    product_id = f"AUTO{random.randint(1000, 9999)}"
    data = {"product_id": product_id, "amount": 100, "currency": "CNY"}
    env = config['env']
    create_listing_url = config['environments'][env]['user']['create_listing_url']
    resp = logged_user_client[sell_user].post(create_listing_url, json=data)
    assert resp.status_code == 201
    listing_id = resp.json()['listing_id']
    row = db_conn.execute("SELECT amount FROM listings WHERE id = ?", (listing_id,)).fetchone()
    return {"listing_id": listing_id, "amount": row['amount']}

@pytest.fixture
def listing_active_self(logged_user_client, default_user,config, db_conn):
    """本人发布的有效挂单"""
    product_id = f"AUTO{random.randint(1000, 9999)}"
    data = {"product_id": product_id, "amount": 100, "currency": "CNY"}
    env = config['env']
    create_listing_url = config['environments'][env]['user']['create_listing_url']
    resp = logged_user_client[default_user].post(create_listing_url, json=data)
    assert resp.status_code == 201
    listing_id = resp.json()['listing_id']
    row = db_conn.execute("SELECT amount FROM listings WHERE id = ?", (listing_id,)).fetchone()
    return {"listing_id": listing_id, "amount": row['amount']}


@pytest.fixture
def listing_canceled(logged_user_client, sell_user, config, db_conn):
    """已取消的挂单"""
    product_id = f"AUTO{random.randint(1000, 9999)}"
    data = {"product_id": product_id, "amount": 100, "currency": "CNY"}
    env = config['env']
    create_listing_url = config['environments'][env]['user']['create_listing_url']
    resp = logged_user_client[sell_user].post(create_listing_url, json=data)
    assert resp.status_code == 201
    listing_id = resp.json()['listing_id']
    row = db_conn.execute("SELECT amount FROM listings WHERE id = ?", (listing_id,)).fetchone()
    # 取消
    cancel_listing_url = config['environments'][env]['user']['cancel_listing_url']
    cancel_resp = logged_user_client[sell_user].post(cancel_listing_url, json={"listing_id": listing_id})
    assert cancel_resp.status_code == 200
    return {"listing_id": listing_id, "amount": row['amount']}



@pytest.fixture
def listing_sold(
    logged_user_client, logged_back_client, test_users,sell_user, default_user,config, db_conn):
    """已完成的挂单（已成交）"""
    # 1. 卖家挂单
    product_id = f"AUTO{random.randint(1000, 9999)}"
    data = {"product_id": product_id, "amount": 100, "currency": "CNY"}
    env = config['env']
    create_listing_url = config['environments'][env]['user']['create_listing_url']
    resp = logged_user_client[sell_user].post(create_listing_url, json=data)
    assert resp.status_code == 201
    listing_id = resp.json()['listing_id']
    row = db_conn.execute("SELECT amount FROM listings WHERE id = ?", (listing_id,)).fetchone()
    amount = row['amount']

    # 2. 买家下单
    create_purchase_order_url = config['environments'][env]['user']['create_purchase_order_url']
    buy_resp = logged_user_client[default_user].post(
        create_purchase_order_url,
        json={"listing_id": listing_id, "purchase_amount": amount}
    )
    assert buy_resp.status_code == 201
    order_id = buy_resp.json()['order_id']

    # 3. 后台审核通过
    admin = next(u for u in test_users['valid_back_users'] if u['role'] == 'ADMIN')
    review_purchase_order_url = config['environments'][env]['back']['review_purchase_order_url']
    logged_back_client[admin['username']].post(
        review_purchase_order_url,
        json={"order_id": order_id, "action": "approve"}
    )

    return {"listing_id": listing_id, "amount": amount}

@pytest.fixture
def listing_nonexistent():
    """挂单id不存在，手动造数据"""
    return {"listing_id": 99999999, "amount": 100}


@pytest.fixture
def listing_null_id():
    """挂单id为空，手动造数据"""
    return {"listing_id": None, "amount": 100}



#======场景路由====
@pytest.fixture()
def prepare_listing_by_scenario(request,
            listing_active_other,
            listing_active_self,
            listing_canceled,
            listing_sold,
            listing_nonexistent,
            listing_null_id
                                ):
    scenario = request.param
    map ={
        "other_active":listing_active_other,
""        "self": listing_active_self,
        "canceled": listing_canceled,
        "sold": listing_sold,
        "nonexistent" : listing_nonexistent,
        "null_id": listing_null_id
    }
    if scenario not in map:
        raise ValueError(f"Unknown listing_scenario: {scenario}")
    return map[scenario]












