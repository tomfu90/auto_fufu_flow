# tests/e2e/test_trading_flow.py
# coding = utf-8
# author =fufu
import pytest
from pathlib import Path
import os,sys
import allure

# 获取项目根目录
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from libs.utils import render_placeholders, load_yaml
from libs.random_utils import generate_random_username, generate_random_email, generate_random_phone
from libs.logger import log_assertion,log_test_action
from libs.api_client import Apiclient




class TradingFlowRunner:
    def __init__(self, config, db_conn):
        self.config = config
        self.db_conn = db_conn
        self.context = {}
        # 缓存动态用户的 token 字符串：key=username, value=token_str
        self._user_tokens = {}      # 前端用户
        self._admin_tokens = {}     # 后台管理员



    def _get_client(self, base_url: str, token: str = None):
        client = Apiclient(base_url)
        if token:
            client.session.headers.update({"Authorization": f"Bearer {token}"})
        return client

    def execute_step(self, step_def: dict):
        name = step_def.get("name")
        action = step_def["action"]
        raw_input = step_def.get("input", {})
        save_as = step_def.get("save_as")

        # === 准备 context（含 random_*）===
        has_random = any("{{random_" in str(v) for v in raw_input.values())
        context_for_render = {}
        if has_random:
            context_for_render.update({
                "random_username": generate_random_username(),
                "random_email": generate_random_email(),
                "random_phone": generate_random_phone(),
            })
        # context_for_render 是临时记录，没有self ；第二次执行方法就丢弃上次的
        # self.context 是实例级记录：实例级记录多次执行方法，会一直记录上下文
        full_context = {**self.context, **context_for_render}
        resolved_input = render_placeholders(raw_input, full_context)
        # 获取用户url,不硬编码:
        env = self.config["env"]
        register_url = self.config['environments'][env]['user']["register_url"]
        user_login_url = self.config['environments'][env]['user']["login_url"]
        create_listing_url = self.config['environments'][env]['user']["create_listing_url"]
        create_purchase_order_url = self.config['environments'][env]['user']["create_purchase_order_url"]
        get_listing_url = self.config['environments'][env]['user']["get_listing_url"]
        get_balance_url = self.config['environments'][env]['user']["get_balance_url"]
        upload_file_url = self.config['environments'][env]['user']["upload_file_url"]
        # 获取后台url，不硬编码:
        back_login_url = self.config['environments'][env]['back']["login_url"]
        review_purchase_order_url = self.config['environments'][env]['back']["review_purchase_order_url"]
        admin_update_balance_url = self.config['environments'][env]['back']["admin_update_balance_url"]
        #记录每一步的请求数据
        with allure.step(name):
            allure.attach(str(resolved_input), "Resolved Input", allure.attachment_type.JSON)
            # ===== 身份识别：优先使用 as_user / as_admin =====
            client = None
            base_url = None

            if "as_user" in resolved_input:
                username = resolved_input.pop("as_user")
                if username not in self._user_tokens:
                    raise ValueError(f"前端用户 '{username}' 未登录，无法使用 as_user")
                token = self._user_tokens[username]
                base_url = self.config["environments"][env]["user"]["base_url"]
                client = self._get_client(base_url, token)

            elif "as_admin" in resolved_input:
                username = resolved_input.pop("as_admin")
                if username not in self._admin_tokens:
                    raise ValueError(f"后台管理员 '{username}' 未登录，无法使用 as_admin")
                token = self._admin_tokens[username]
                base_url = self.config["environments"][env]["back"]["base_url"]
                client = self._get_client(base_url, token)

            # ===== 执行具体 action =====
            if action == "register":
                base_url = self.config["environments"][env]["user"]["base_url"]
                client = self._get_client(base_url)
                resp = client.post(register_url, json=resolved_input)
                with allure.step("响应断言"):
                    assert resp.status_code == 200,f"{name}接口响应状态码{resp.status_code},非预期200"
                    log_assertion(name,resp.status_code == 200,actual=resp.status_code,expected=200)
                result = resp.json()

            elif action == "login":
                base_url = self.config["environments"][env]["user"]["base_url"]
                client = self._get_client(base_url)
                login_data = {"username": resolved_input["username"], "password": resolved_input["password"]}
                resp = client.post(user_login_url, json=login_data)
                with allure.step("响应断言"):
                    assert resp.status_code == 200,f"{name}接口响应状态码{resp.status_code},非预期200"
                    log_assertion(name,resp.status_code == 200,actual=resp.status_code,expected=200)
                result = resp.json()
                # 缓存 token
                self._user_tokens[resolved_input["username"]] = result["access_token"]

            elif action == "admin_login":
                base_url = self.config["environments"][env]["back"]["base_url"]
                client = self._get_client(base_url)
                login_data = {"username": resolved_input["username"], "password": resolved_input["password"]}
                resp = client.post(back_login_url, json=login_data)
                with allure.step("响应断言"):
                    assert resp.status_code == 200,f"{name}接口响应状态码{resp.status_code},非预期200"
                    log_assertion(name,resp.status_code == 200,actual=resp.status_code,expected=200)
                result = resp.json()
                # 缓存 token
                self._admin_tokens[resolved_input["username"]] = result["access_token"]

            elif action == "admin_add_balance":
                if client is None:
                    raise ValueError("admin_add_balance 必须通过 as_admin 指定身份")
                payload = {
                    "username": resolved_input["username"],
                    "amount": float(resolved_input["amount"]),
                }
                resp = client.post(admin_update_balance_url, json=payload)
                with allure.step("响应断言"):
                    assert resp.status_code == 200,f"{name}接口响应状态码{resp.status_code},非预期200"
                    log_assertion(name,resp.status_code == 200,actual=resp.status_code,expected=200)
                result = resp.json()

            elif action == "create_listing":
                if client is None:
                    raise ValueError("create_listing 必须通过 as_user 指定身份")
                payload = {
                    "product_id": resolved_input["product_id"],
                    "amount": float(resolved_input["amount"]),
                    "currency": resolved_input.get("currency", "CNY")
                }
                resp = client.post(create_listing_url, json=payload)
                with allure.step("响应断言"):
                    assert resp.status_code == 201,f"{name}接口响应状态码{resp.status_code},非预期201"
                    log_assertion(name,resp.status_code == 201,actual=resp.status_code,expected=201)
                result = resp.json()

            elif action == "purchase_listing":
                if client is None:
                    raise ValueError("purchase_listing 必须通过 as_user 指定身份")
                payload = {
                    "listing_id": resolved_input["listing_id"],
                    "purchase_amount": float(resolved_input["purchase_amount"])
                }
                resp = client.post(create_purchase_order_url, json=payload)
                with allure.step("响应断言"):
                    assert resp.status_code == 201,f"{name}接口响应状态码{resp.status_code},非预期201"
                    log_assertion(name,resp.status_code == 201,actual=resp.status_code,expected=201)
                result = resp.json()

            elif action == "approve_order":
                if client is None:
                    raise ValueError("approve_order 必须通过 as_admin 指定身份")
                payload = {
                    "order_id": resolved_input["order_id"],
                    "action": resolved_input["action"]
                }
                resp = client.post(review_purchase_order_url, json=payload)
                with allure.step("响应断言"):
                    assert resp.status_code == 200,f"{name}接口响应状态码{resp.status_code},非预期200"
                    log_assertion(name,resp.status_code == 200,actual=resp.status_code,expected=200)
                result = resp.json()

            elif action == "search_listing":
                if client is None:
                    raise ValueError("search_listing 必须通过 as_user 指定身份")
                payload = {"listing_id": resolved_input["listing_id"]}
                resp = client.post(get_listing_url, json=payload)
                with allure.step("响应断言"):
                    assert resp.status_code == 200,f"{name}接口响应状态码{resp.status_code},非预期200"
                    log_assertion(name,resp.status_code == 200,actual=resp.status_code,expected=200)
                result = resp.json()

            elif action == "search_balance":
                if client is None:
                    raise ValueError("search_balance 必须通过 as_user 指定身份")
                resp = client.get(get_balance_url)
                with allure.step("响应断言"):
                    assert resp.status_code == 200,f"{name}接口响应状态码{resp.status_code},非预期200"
                    log_assertion(name,resp.status_code == 200,actual=resp.status_code,expected=200)
                result = resp.json()

            elif action == "upload_file":
                if client is None:
                    raise ValueError("upload_file 必须通过 as_user 指定身份")
                file_path = resolved_input["file"]
                abs_file_path = project_root / "data"/ "upload"/ "data"/file_path
                if not abs_file_path.exists():
                    raise FileNotFoundError(f"上传文件不存在: {abs_file_path}")
                with open(abs_file_path, 'rb') as f:
                    resp = client.post(upload_file_url, files={"file": f})
                with allure.step("响应断言"):
                    assert resp.status_code == 200,f"{name}接口响应状态码{resp.status_code},非预期200"
                    log_assertion(name,resp.status_code == 200,actual=resp.status_code,expected=200)
                result = resp.json()

            elif action == "assert_db":
                query = resolved_input["query"]
                params = resolved_input.get("params", [])
                expected = resolved_input["expected"]
                log_test_action(
                    action="db_query",
                    details=f"Query={query} | Params={params} | Expected={expected}"
                )
                cur = self.db_conn.cursor()
                cur.execute(query, params)
                row = cur.fetchone()

                assert row is not None,  "数据库无该记录"
                actual = {k: row[k] for k in expected}

                assert actual == expected, f"DB断言失败\n实际: {actual}\n预期: {expected}"
                with allure.step("响应断言"):
                    assert actual == expected,f"DB断言失败\n实际: {actual}\n预期: {expected}"
                    log_assertion(name,actual == expected,actual=actual,expected=expected)
                result = actual

            else:
                raise NotImplementedError(f"Action '{action}' is not implemented")

            if save_as:
                self.context[save_as] = result

            return result




# ========================
# Pytest Test
# ========================
def test_e2e_trading_flow(config, db_conn):
    """执行完整交易流程 YAML 用例 —— 不依赖任何预置用户"""
    spec = load_yaml('data/e2e/user_trading_flow.yaml')
    allure.title(spec["name"])
    allure.description(spec["description"])

    runner = TradingFlowRunner(config=config, db_conn=db_conn)
    for step_def in spec["steps"]:
        runner.execute_step(step_def)
