#coding = utf-8
#author = fufu
import pytest
import sys,os
#设置项目根目录，防止意外找不到导内部模块路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)
from libs.api_client import  Apiclient
from libs.random_utils import generate_random_username,generate_random_email,generate_random_phone

@pytest.fixture()
def base_url(config):
    env = config["env"]
    base_url = config["environments"][env]['user']["base_url"]
    return base_url

@pytest.fixture()
def register_url(config):
    env = config["env"]
    register_url = config["environments"][env]['user']["register_url"]
    return register_url

@pytest.fixture()
def admin_update_balance_url(config):
    env = config["env"]
    admin_update_balance_url = config["environments"][env]['back']["admin_update_balance_url"]
    return admin_update_balance_url

@pytest.fixture()
def register_username(base_url,register_url):
    """先注册用户，返回username"""
    data ={
        "username": generate_random_username(),
        "password": "abc12345",
        "confirm_password": "abc12345",
        "phone": generate_random_phone(),
        "email": generate_random_email()
    }
    resp = Apiclient(base_url).post(register_url,json=data)
    assert resp.status_code == 200
    return data["username"]






