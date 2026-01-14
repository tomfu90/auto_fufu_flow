# coding = utf-8
import traceback
import requests
import allure
import json
import sys
from pathlib import Path
#获取项目根目录
root_dir = Path(__file__).parent.parent
#如果根目录不存在 sys.path，就插在最前面
if str(root_dir) not in sys.path:
    sys.path.insert(0,str(root_dir))
from libs.logger import log_test_action



class Apiclient:

    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/") # 移除末尾斜杠（避免拼接时出现双斜杠）
        self.session = requests.Session() #创建持久会话

    def _request(self, method, path, **kwargs):
        url = self.base_url + path  # 拼接完整请求
        # 1. 从 session 获取默认 headers（如 Authorization）
        base_headers = dict(self.session.headers) # 获取会话请求头
        # 2. 合并本次请求传入的 headers（如 X-Signature）
        if "headers" in kwargs:
            actual_headers = {**base_headers, **kwargs["headers"]}
        # 3 如果请求中没有设置请求头，启用默认请求头
        else:
            actual_headers = base_headers
        if "json" in kwargs:
            body = kwargs["json"]
        elif "data" in kwargs:
            raw_data = kwargs["data"]
            if isinstance(raw_data, dict):
                body = raw_data
            elif isinstance(raw_data, str):
                try:
                    body = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    body = raw_data
            else:
                body = str(raw_data)
        else:
            body = {}
        files = kwargs.get("files") or {}
        #构造请求摘要，用于allure和log日志记录
        req_summary = f"{method} {url}"
        req_info =(
            f"URL: {url}\n"
            f"Method: {method}\n"
            f"Headers: {json.dumps(actual_headers,indent=2,ensure_ascii=False)}\n"
            f"Body:{json.dumps(body,indent=2,ensure_ascii=False) if body else 'None'}" # 将python字典格式转为json格式传递

        )
        try:
            with allure.step(f'发送请求:{req_summary}'):
                allure.attach(req_info, "请求详情", attachment_type=allure.attachment_type.TEXT)
            # 如果 kwargs 中没有 timeout，则默认设为 15
            if "timeout" not in kwargs:
                kwargs["timeout"] = 15
            # 发起请求
            response = self.session.request(method, url, **kwargs)
            # 成功处理响应
            try:
                resp_data = response.json()
                resp_text = json.dumps(resp_data, indent=2, ensure_ascii=False)
            except Exception:
                resp_data = None
                resp_text = response.text
            with allure.step(f"响应：{response.status_code}"):
                allure.attach(resp_text, "响应详情", allure.attachment_type.JSON if resp_data else allure.attachment_type.TEXT)
            #记录成功业务日志
            log_test_action(action="api_request_success", details=f"URL={url} |Status={response.status_code}| Headers={actual_headers} ｜Method={method}| URL={url} | Request={body}| Response={resp_data if resp_data else "non-json"}")

            return response
        except requests.exceptions.RequestException as e:
            # 捕获requests请求异常
            error_msg = f"{e.__class__.__name__}: {str(e)}"
            full_traceback = traceback.format_exc()
            #allure记录异常
            with allure.step(f"请求失败：{req_summary}"):
                allure.attach(req_info,"请求详情", attachment_type=allure.attachment_type.TEXT)
                allure.attach(error_msg,"错误信息", attachment_type=allure.attachment_type.TEXT)
                allure.attach(full_traceback, "堆栈信息", attachment_type=allure.attachment_type.TEXT)
            #业务日志记录异常
            log_test_action(action='api_request_failed', details=f"URL={url} | Headers={actual_headers} | Method={method}| Request={body}|Error={error_msg}")
            raise
        except Exception as e:
            # 兜底异常
            log_test_action(action='api_request_error',details=f"URL={url} | Headers={actual_headers} | Method={method}| Request={body}|Error={str(e)} | Trace={traceback.format_exc()}")
            raise


    def get(self, path, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self._request("POST", path, **kwargs)

if __name__ == "__main__":
    api_client = Apiclient('http://127.0.0.1:5000')
    data1 ={
        'username': 'tester',
        'password': 'SecurePass123!'

    }
    print(f"data1:{data1}")
    resp1 = api_client.post('/api/login', json=data1)
    print(resp1.json())
    data2 = {
        'username': 'tester12',
        'password': 'SecurePass1231!111'

    }
    print(f"data2:{data2}")
    resp2 = api_client.post('/api/login', json=data2)
    print(resp2.json())







