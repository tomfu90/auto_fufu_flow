# coding = utf-8
# author = fufu
# utils/random_utils.py
import random
import string

def generate_random_username(length=5, prefix="auo"):
    """生成随机用户名，如 auto1b2c3"""
    chars = string.ascii_lowercase + string.digits
    return prefix + ''.join(random.choices(chars, k=length))

def generate_random_email(domain="test.com"):
    """生成随机邮箱"""
    chars = string.ascii_lowercase + string.digits
    username = "auo" + ''.join(random.choices(chars, k=7))
    return username + "@" + domain

def generate_random_phone():
    """生成随机手机号（示例：138xxxx1234）"""
    return "138" + ''.join(random.choices(string.digits, k=8))


if __name__ == "__main__":
    print(generate_random_username())
    print(generate_random_email())
    print(generate_random_phone())