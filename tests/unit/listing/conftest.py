# #coding = utf-8
# #author = fufu
#
import pytest
import random

@pytest.fixture()
def prepare_listing(db_conn,test_users,default_user,logged_user_client,logged_back_client,config):
    """
        根据指定状态准备 listing_id
        用法:
            lid = prepare_listing(ACTIVE)
            lid = prepare_listing(CANCELED)
            lid = prepare_listing(SOLD)
            lid = prepare_listing(OTHER_USER)
    """
    def _make(state):
        # --- 公共：获取用户和 URL ---
        sell_users = [u for u in test_users['valid_user_users'] if u['role'] == 'sell']
        username_sell = sell_users[0]['username'] #本人创建：sell_user
        env = config['env']
        create_listing_url = config['environments'][env]['user']['create_listing_url']
        product_id = f"AUTO{random.randint(1000, 9999)}"
        data = {
            "product_id": product_id,
            "amount": 100,
            "currency": "CNY"
        }
        # --- 按状态分别设计场景 ---
        # 1 挂单中状态，挂单id- 本人创建：sell_user
        if state == "active":
            resp = logged_user_client[username_sell].post(create_listing_url, json=data)
            assert resp.status_code == 201
            listing_id = resp.json()['listing_id']
            return listing_id
        # 2 不存在挂单id，手动造数据，取消失败
        if state == "empty":
            listing_id = "9999999"  # 不存在的挂单id
            return listing_id
        # 3 挂单中状态，挂单id- 其他人创建：default_user ,对应场景 ：取消他人挂单
        if state == "other":
            resp = logged_user_client[default_user].post(create_listing_url, json=data)
            assert resp.status_code == 201
            listing_id = resp.json()['listing_id']
            return listing_id
        # 4 挂单状态已取消，再次进行取消: 1先创建挂单，2取消成功，返回取消挂单id；对应场景：挂单状态非挂单中（已取消），取消失败
        if state == "canceled":
            resp = logged_user_client[username_sell].post(create_listing_url, json=data)
            assert resp.status_code == 201
            listing_id = resp.json()['listing_id']
            cancel_listing_url = config['environments'][env]['user']['cancel_listing_url']
            data = {
                     "listing_id": listing_id,
                 }
            resp1 = logged_user_client[username_sell].post(cancel_listing_url, json=data)
            assert resp1.status_code == 200
            return listing_id
        # 5 已完成的挂单: 测试 已完成挂单失败取消失败场景 1 用户sell_user 创建挂单  2 用户default_user 购买挂单，生成对应订单  3 后台管理员审核订单-审核通过
        if state == "sold":
            # 1 sell_user创建挂单
            resp = logged_user_client[username_sell].post(create_listing_url, json=data)
            assert resp.status_code == 201
            listing_id = resp.json()['listing_id']
            # 2 查询挂单金额
            listing = db_conn.execute("""
                                SELECT amount
                                FROM listings
                                WHERE id = ?
                            """, (listing_id,)).fetchone()
            purchase_amount = listing['amount']
            # 3 default_user 默认用户去全部购买：default_user
            buy_data = {
                'listing_id': listing_id,
                "purchase_amount": purchase_amount
            }
            create_purchase_order_url = config['environments'][env]['user']['create_purchase_order_url']
            resp_buy = logged_user_client[default_user].post(create_purchase_order_url, json=buy_data)
            assert resp_buy.status_code == 201
            # 4 后台管理员 审核通过
            back_user = next(user for user in test_users['valid_back_users'] if user['role'] == "ADMIN")
            back_user_name = back_user['username']
            data_action = {
                'order_id': resp_buy.json()['order_id'],
                "action": "approve"
            }
            review_purchase_order_url= config['environments'][env]['back']['review_purchase_order_url']
            resp_back = logged_back_client[back_user_name].post(review_purchase_order_url, json=data_action)
            assert resp_back.status_code == 200
            return listing_id
        else:
            raise ValueError(f"Unsupported listing state: {state}. Expected one of: active, empty, other, canceled, sold")
    return _make
















