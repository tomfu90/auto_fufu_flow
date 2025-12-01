# coding =utf -8
# author = fufu
import pytest
import random


@pytest.fixture()
def base_url(config):
    env = config["env"]
    base_url = config["environments"][env]["user"]["base_url"]
    return base_url

@pytest.fixture()
def get_listing_url(config):
    env = config["env"]
    get_listing_url = config["environments"][env]["user"]["get_listing_url"]
    return get_listing_url


@pytest.fixture()
def create_listing_url(config):
    env = config["env"]
    create_listing_url = config["environments"][env]["user"]["create_listing_url"]
    return create_listing_url

@pytest.fixture()
def create_listing(create_listing_url,logged_user_client,sell_user):
    """先创建一个挂单"""
    product_id = f"AUTO{random.randint(1000, 9999)}"
    data = {"product_id": product_id, "amount": 100, "currency": "CNY"}
    response = logged_user_client[sell_user].post(create_listing_url,json=data)
    assert response.status_code == 201
    return response.json()['listing_id']