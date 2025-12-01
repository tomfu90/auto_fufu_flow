# coding = utf-8
# author = fufu
import pytest
from pathlib import Path
import sys,os
import allure
#获取项目根目录路径，防止意外找不到项目模块路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from libs.utils import load_yaml
from libs.logger import log_assertion


#获取测试数据
test_cases = load_yaml('data/upload/test_upload.yaml')
test_success_cases = test_cases['success_cases']
test_fail_cases = test_cases['fail_cases']

@pytest.mark.smoke
@pytest.mark.parametrize('test_case', test_success_cases)
def test_upload_success(config,test_users,logged_user_client,db_conn,test_case):
    print(f"开始测试用例：{test_case['name']}")
    #allure报告设置动态标题
    allure.dynamic.title(test_case['name'])
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    #获取url
    env = config['env']
    upload_file_url = config['environments'][env]['user']['upload_file_url']
    #发起请求-这是文件，需要读取内容
    filepath = str(project_root/test_case['input']['file'])
    print(f"filepath:{filepath}")
    with open(filepath,mode='rb') as f:
        response = logged_user_client[username].post(upload_file_url,files={'file': f})
    #获取文件名
    original_name =os.path.basename(test_case['input']['file'])
    with allure.step('校验响应状态码'):
        actual_value = response.status_code
        expected_value = test_case['expected']['status_code']
        log_assertion(test_case['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value == expected_value,f"实际：{actual_value} 期望：{expected_value}"
    with allure.step('校验响应信息'):
        actual_value = response.json()['message']
        expected_value = test_case['expected']['message']
        log_assertion(test_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"
    with allure.step('数据库校验：文件是否写入'):
        row = db_conn.execute('SELECT id,filename,original_name FROM uploads WHERE original_name =? order by upload_time desc limit 1', (original_name,)).fetchone()
        log_assertion(test_case['name'], row is not None, message=f"数据库查询不到{username}上传的文件：{original_name}")
        assert row is not None,f"数据库查询不到{username}上传的文件：{original_name}"
        actual_value = response.json()['filename']
        expected_value = row['filename']
        log_assertion(test_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"



@pytest.mark.parametrize('test_case',test_fail_cases)
def test_upload_fail(config,test_users,logged_user_client,db_conn,test_case):
    print(f"开始测试用例：{test_case['name']}")
    # allure报告设置动态标题
    allure.dynamic.title(test_case['name'])
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    # 获取url
    env = config['env']
    upload_file_url = config['environments'][env]['user']['upload_file_url']
    # 发起请求-这是文件，需要读取内容
    file_input = test_case['input']['file']
    if file_input is not None:
        filepath = str(project_root / test_case['input']['file'])
        print(f"filepath:{filepath}")
        with open(filepath,mode='rb') as f:
            response = logged_user_client[username].post(upload_file_url,files={'file': f})
    else:
        response = logged_user_client[username].post(upload_file_url)

    with allure.step('校验响应状态码'):
        actual_value = response.status_code
        expected_value = test_case['expected']['status_code']
        log_assertion(test_case['name'],actual_value==expected_value,actual_value,expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"
    with allure.step('校验响应信息'):
        actual_value = response.json()['error']
        expected_value = test_case['expected']['error']
        log_assertion(test_case['name'], actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"

def test_upload_list(config,test_users,logged_user_client,db_conn):
    allure.dynamic.title("查询上传记录")
    #获取url
    env = config['env']
    list_uploads_url = config['environments'][env]['user']['list_uploads_url']
    # 获取有效用户,第一个默认角色用户
    user_creds = test_users['valid_user_users']
    user_cred = next(user for user in user_creds if user['role'] == "default")
    username = user_cred['username']
    #查看第一页
    limit = 1
    response = logged_user_client[username].get(list_uploads_url,params={'limit': 1})
    with allure.step('校验响应状态码'):
        actual_value = response.status_code
        expected_value = 200
        log_assertion("查询上传记录",actual_value==expected_value,actual_value,expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"
    with allure.step('查询数据库上传记录'):
        rows = db_conn.execute('SELECT id,filename,original_name,file_size,username,upload_time FROM uploads where username=? order by upload_time desc limit ?',(username,limit)).fetchall()
        log_assertion("查询上传记录", rows is not None, message=f"数据库查询不到{username}上传的文件")
        #接口返回条数和数据库返回条数是否相同
        actual_value = len(rows)
        expected_value = len(response.json())
        log_assertion("查询上传记录", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"
        # 接口返回的文件名是否都存在数据库中
        actual_value = {item['filename'] for item in response.json()}
        expected_value = { row['filename'] for row in rows}
        log_assertion("查询上传记录", actual_value == expected_value, actual_value, expected_value)
        assert actual_value == expected_value, f"实际：{actual_value} 期望：{expected_value}"

