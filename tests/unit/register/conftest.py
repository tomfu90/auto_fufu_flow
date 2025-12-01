# coding =utf -8
# author = fufu
import pytest
#设置项目根目录，防止意外找不到导内部模块路径
from pathlib import Path
import sys
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
from libs.api_client import  Apiclient
from libs.random_utils import generate_random_username,generate_random_email,generate_random_phone
# 提前构建3种重复场景：账号重复，手机号重复，邮箱重复
@pytest.fixture()
def base_url(config):
    env = config["env"]
    base_url = config["environments"][env]["user"]["base_url"]
    return base_url

@pytest.fixture()
def register_url(config):
    env = config["env"]
    register_url = config["environments"][env]["user"]["register_url"]
    return register_url


@pytest.fixture()
def repeat_username(register_url,base_url):
    """注册账号重复"""
    data = {
        "username": generate_random_username(),
        "password": "abc1201",
        "confirm_password": "abc1201",
        "phone": generate_random_phone(),
        "email": generate_random_email(),
    }
    resp = Apiclient(base_url).post(register_url, json=data)
    assert resp.status_code == 200
    return resp.json()['username']

@pytest.fixture()
def repeat_phone(register_url,base_url,db_conn):
    """注册手机号重复"""
    data = {
        "username": generate_random_username(),
        "password": "abc1201",
        "confirm_password": "abc1201",
        "phone": generate_random_phone(),
        "email": generate_random_email(),
    }
    resp = Apiclient(base_url).post(register_url, json=data)
    assert resp.status_code == 200
    return data['phone']

@pytest.fixture()
def repeat_email(register_url,base_url,db_conn):
    """注册邮箱重复"""
    data = {
        "username": generate_random_username(),
        "password": "abc1201",
        "confirm_password": "abc1201",
        "phone": generate_random_phone(),
        "email": generate_random_email(),
    }
    resp = Apiclient(base_url).post(register_url, json=data)
    assert resp.status_code == 200
    return data['email']





