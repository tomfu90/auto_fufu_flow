# mock_server/app.py
# coding = utf-8
"""
多用户支持的 Mock 服务（全功能版）：
- 支持多用户独立注册与登录（含账号/密码/手机/邮箱校验）
- 每个用户获得唯一短期有效 Token（1 小时），通过 Bearer 认证
- Token 与用户强绑定，实现精确鉴权与数据隔离
- 用户数据完全隔离：订单、挂单、交易流水、上传文件等均按 username 隔离
- 支持三种主流 API 签名验证机制：
    • HMAC-SHA256（Header 签名，含 timestamp + nonce 防重放）
    • ECDSA (SECP256k1)（公钥即身份标识，支持 Base64 编码未压缩格式）
    • MD5 + Base64（Body 内嵌签名，兼容传统 Mock 接口风格）
- 提供标准业务模块：
    • 账户余额查询（/api/account/balance）
    • 交易流水查询（/api/account/transactions）
    • 订单创建与查询（普通 / HMAC / ECDSA / MD5 四种入口）
    • 商品挂单（卖家发布）、取消挂单
    • 购买挂单（买家下单），支持部分购买
    • 管理员审核购买订单（approve / reject）
    • 管理员后台调整用户余额（防负余额）
- 文件上传支持：
    • 仅允许 JPG/JPEG/PNG 格式
    • 单文件 ≤ 100KB
    • 文件元信息存入数据库，按用户隔离
- 安全防护：
    • 所有签名均校验时间戳（±5 分钟窗口）
    • 全局内存级 Nonce 防重放（300 秒内不可复用）
    • 敏感操作需 Token + 签名双重验证
    • 管理员权限严格隔离（admins 表 + role 字段校验）
- 数据库设计规范：
    • users / accounts / orders / listings / purchase_orders / uploads / tokens / api_keys / admins
    • 外键约束启用（PRAGMA foreign_keys = ON）
- 辅助接口：
    • /health 健康检查
    • /api/listing 查询挂单详情
    • /api/GetUploads 列出用户上传记录 等
"""

from flask import Flask, request, jsonify, g
import time
import sqlite3
import uuid
from datetime import datetime,timedelta
import os,sys
from werkzeug.utils import secure_filename
from pathlib import Path
import re
#获取项目根目录
root_dir = Path(__file__).parent.parent
#如果根目录不存在 sys.path，就插在最前面
if str(root_dir) not in sys.path:
    sys.path.insert(0,str(root_dir))

#导入项目模块
from libs.database import get_db_connection,init_db
import hmac
import hashlib
import base64
import json
from urllib.parse import urlencode,parse_qsl,quote
from ecdsa import VerifyingKey, SECP256k1
from ecdsa.util import sigdecode_string


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = root_dir /'mock_server'/'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)




def verify_token(auth_header):
    #校验auth_header是否存在，是否指定字符串开头
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    #将获取到的token和数据库查询比对
    with get_db_connection() as conn:
        row = conn.execute("SELECT username,expires_at FROM tokens WHERE token=?",(token,)).fetchone()
        #1 数据库查询不到返回空
        if not row:
            return None
        expires_at = datetime.strptime(row['expires_at'], '%Y-%m-%d %H:%M:%S.%f')
        #2 token过期 返回无效
        if datetime.now() > expires_at:
            conn.execute("DELETE FROM tokens WHERE token=?",(token,))
            return None
        return row['username']



# 内存缓存 nonce（生产环境建议用 Redis）
_seen_nonces = {}



def _normalize_request_data(method:str,path:str,query_params: dict, body: str,  timestamp: str,nonce: str) -> str:
    """
        构造待签名字符串（行业通用规范）
        格式: METHOD\nPATH\nQUERY_STRING_SORTED\nBODY\nTIMESTAMP\nNONCE
    """
    sorted_query = urlencode(sorted(query_params.items()),safe='',quote_via=quote) if query_params else ""
    return f"{method}\n{path}\n{sorted_query}\n{body}\n{timestamp}\n{nonce}"


def _is_nonce_used(nonce: str, timestamp: int, window_seconds: int = 300) -> bool:
    """防重放攻击：nonce 在 window_seconds 内不可复用"""
    now = int(time.time())
    expire = now - window_seconds
    # 清理过期 nonce
    to_remove = [k for k,v in _seen_nonces.items() if v < expire]
    for k in to_remove:
        del _seen_nonces[k]
    if nonce in _seen_nonces:
        return True
    _seen_nonces[nonce] = timestamp
    return False

def verify_hmac_signature(api_secret: str, signature: str, method: str, path: str, query_params: dict, body: str, timestamp: str, nonce: str) -> bool:
    """
    HAMC-sha256签名验证方法
    """
    try:
        ts_int = int(timestamp)
    except (ValueError, TypeError):
        return False

    now = int(time.time())
    if abs(now - ts_int) > 300:  # 5分钟窗口
        return False

    if _is_nonce_used(nonce, ts_int):
        return False

    message = _normalize_request_data(method, path, query_params, body, timestamp, nonce).encode('utf-8')
    expected_sig = base64.b64encode(hmac.new(api_secret.encode('utf-8'), message, hashlib.sha256).digest()).decode(
        'utf-8')

    return hmac.compare_digest(expected_sig, signature)


def verify_ecdsa_signature(public_key_b64: str, signature_b64: str, method: str, path: str, query_params: dict, body: str, timestamp: str, nonce: str) -> bool:
    """
        ecdsa签名验证方法
    """
    try:
        ts_int = int(timestamp)
    except (ValueError, TypeError):
        return False

    now = int(time.time())
    if abs(now - ts_int) > 300:
        return False

    if _is_nonce_used(nonce, ts_int):
        return False

    try:
        # 解码公钥（Base64 -> bytes）
        public_key_bytes = base64.b64decode(public_key_b64)
        # 验证是否为未压缩 SECP256k1 公钥（应以 0x04 开头，65字节）
        if len(public_key_bytes) != 65 or public_key_bytes[0] != 4:
            return False
        vk = VerifyingKey.from_string(public_key_bytes[1:], curve=SECP256k1)
    except Exception:
        return False

    message = _normalize_request_data(method, path, query_params, body, timestamp, nonce).encode('utf-8')
    digest = hashlib.sha256(message).digest()
    try:
        sig_bytes = base64.b64decode(signature_b64)
        return vk.verify_digest(sig_bytes, digest, sigdecode=sigdecode_string)
    except Exception:
        return False


def _build_query_string(params: dict) -> str:
    """
    构建 k1=v1&k2=v2 字符串：
      - 过滤 None、空字符串、纯空白
      - 所有值转为字符串
      - 按 key 升序排序
    """
    filtered = {}
    for k, v in params.items():
        if v is None:
            continue
        v_str = str(v)
        if v_str.strip() == "":
            continue
        filtered[k] = v_str
    sorted_items = sorted(filtered.items())
    return urlencode(sorted_items,safe='',quote_via=quote)




def verify_md5_signature(secret: str,signature_b64: str,body: str)-> bool:
    """
      验证 Base64 编码的 MD5 签名（主流 Mock 接口风格）

      签名生成逻辑（客户端）：
        params = { ...业务字段..., "key": secret }
        signing_str = "k1=v1&k2=v2&...&key=xxx"  （排序后）
        md5_bytes = MD5(signing_str)
        sign = base64.b64encode(md5_bytes).decode()
        final_body = { ...业务字段..., "sign": sign }

      :param secret: 私钥（由上层根据 public_key 或其他方式查出后传入）
      :param signature_b64: 客户端传入的 Base64 编码签名
      :param body: 原始请求体 JSON 字符串（含 "sign" 字段）
      :return: bool
      """
    # 1. 解析 body
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return False


    # 2. 还原业务参数（移除 signature 和 publick_key）
    business_params = {k: v for k, v in data.items() if k not in( "signature","public_key") }

    # 3. 加入私钥字段（参与排序！）
    sign_params = business_params.copy()
    sign_params['secret'] = secret

    # 4. 构建待签名字符串
    signing_str = _build_query_string(sign_params)

    # 5. 计算 MD5 二进制摘要
    md5_digest = hashlib.md5(signing_str.encode('utf-8')).digest()

    # 6. Base64 编码
    expected_b64 = base64.b64encode(md5_digest).decode('ascii')

    if signature_b64 == expected_b64:
        return True
    return False



def get_api_key_info(key_id: str) -> dict | None:
    """
    提供辅助函数（根据 key_id 查 secret 和用户名）
    用于hmac-hsa256 +MD5-32 签名辅助用
    """
    if not key_id:
        return None
    with get_db_connection() as conn:
        row = conn.execute("SELECT secret, username FROM api_keys WHERE key_id = ? AND is_active = 1",(key_id,)).fetchone()
        return dict(row) if row else None



@app.route('/api/v1/md5/order', methods=['POST'])
def create_order_md5():
    """
        使用 MD5 + Base64 签名创建订单（主流 Mock 风格）

        Body (JSON):
          {
            "amount": 100,
            "order_type": "deposit",
            "product_id": "PROD123",
            "currency": "CNY",
            "public_key": "ak_test123",   ← 必须与 X-API-Key 一致（或仅用 body）
            "signature": "Base64(MD5(...))"  ← Base64 编码的 MD5 签名
          }

        签名规则：
          params = {所有 body 字段，除了 "signature" 和 "public_key"}
          params["secret"] = <真实私钥>
          signing_str = 按 key 升序拼接为 k1=v1&k2=v2...
          signature = base64.b64encode(MD5(signing_str)).decode()
    """
    # 1. 验证用户身份
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    # 2. 获取原始 body 字符串（必须与客户端完全一致）
    body_data = request.get_json()

    #3. 获取公钥信息
    key_id = body_data.get("public_key")
    if not key_id:
        return jsonify({"error": "Missing 'public_key' field in body"}), 400
    #4. 获取在服务器端公钥绑定的私钥
    key_info = get_api_key_info(key_id)
    if not key_info:
        return jsonify({"error": "Invalid or inactive API key"}), 401

    if key_info['username'] != username:
        return jsonify({"error": "API key does not belong to current user"}), 401
    # 5. 提取签名
    client_signature = body_data.get("signature")
    if not client_signature:
        return jsonify({"error": "Missing 'signature' field in body"}), 400

    # 6. 获取原始 body 字符串（必须与客户端完全一致）
    raw_body = request.get_data(as_text=True)
    # 7. 验签（调用你写的函数）
    if not verify_md5_signature(
        secret=key_info['secret'],
        signature_b64=client_signature,
        body=raw_body
    ):
        return jsonify({"error": "Invalid MD5 signature"}), 401

    # 8. 业务逻辑校验
    amount = body_data.get('amount')
    order_type = body_data.get('order_type')
    currency = body_data.get('currency', 'CNY')
    product_id = body_data.get('product_id')

    if not isinstance(amount, (int, float)) or amount <= 0 or amount > 100000:
        return jsonify({"error": "Invalid amount"}), 400
    if not product_id or len(str(product_id)) not in range(2, 9):
        return jsonify({"error": "Invalid product_id"}), 400
    if currency.upper() not in ['CNY', 'USD']:
        return jsonify({"error": "Invalid currency"}), 400
    if order_type.upper() not in ['DEPOSIT', 'WITHDRAW', 'PAYMENT']:
        return jsonify({"error": "Invalid order_type"}), 400

    # 9. 创建订单
    order_id = f"ORD{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = 'CREATED'

    with get_db_connection() as conn:
        conn.execute("""
             INSERT INTO orders(order_id, username, amount, currency, order_type,
                                product_id, status, created_at)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         """, (order_id, username, amount, currency.upper(), order_type.upper(),
               product_id, status, created_at))

    return jsonify({
        "order_id": order_id,
        "username": username,
        "amount": round(float(amount), 2),
        "order_type": order_type.upper(),
        "currency": currency.upper(),
        "product_id": product_id,
        "status": status,
        "created_at": created_at
    }), 201



@app.route('/api/v1/hmac/order', methods=['POST'])
def create_order_hmac():
    """
        使用 HMAC-SHA256 签名创建订单
        Headers:
          X-API-Key: <key_id> ← 公开的 Key ID（如 ak_abc123）
          X-Timestamp: <unix_timestamp>
          X-Nonce: <unique_string>
          X-Signature: <base64(hmac-sha256)>
        Body: JSON
    """
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    key_id = request.headers.get('X-API-Key')
    timestamp = request.headers.get('X-Timestamp')
    nonce = request.headers.get('X-Nonce')
    signature = request.headers.get('X-Signature')

    if not all([key_id, timestamp, nonce, signature]):
        return jsonify({
            "error": "Missing required headers: X-API-Key, X-Timestamp, X-Nonce, X-Signature"
        }), 400

    body = request.get_data(as_text=True) or ""
    try:
        json.loads(body)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON body"}), 400

    query_params = dict(parse_qsl(request.query_string.decode('utf-8'))) if request.query_string else {}

    key_info = get_api_key_info(key_id)
    if not key_info:
        return jsonify({"error": "Invalid or inactive API key"}), 401

    api_secret = key_info['secret']
    if key_info['username'] != username:
        return jsonify({"error": " API key 和用户不对应"}), 401

    # 验签
    if not verify_hmac_signature(api_secret, signature, request.method, request.path, query_params, body, timestamp,
                                 nonce):
        return jsonify({"error": "Invalid signature"}), 401
    # 业务逻辑
    data = json.loads(body)
    amount = data.get('amount')
    order_type = data.get('order_type')
    currency = data.get('currency', 'CNY')
    product_id = data.get('product_id')

    # 业务逻辑校验
    if not isinstance(amount, (int, float)) or amount <= 0 or amount > 100000:
        return jsonify({"error": "Invalid amount"}), 400
    if not product_id or len(str(product_id)) not in range(2, 9):
        return jsonify({"error": "Invalid product_id"}), 400
    if currency.upper() not in ['CNY', 'USD']:
        return jsonify({"error": "Invalid currency"}), 400
    if order_type.upper() not in ['DEPOSIT', 'WITHDRAW', 'PAYMENT']:
        return jsonify({"error": "Invalid order_type"}), 400

    #创建订单（现在有真实username）
    order_id = f"ORD{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = 'CREATED'

    #插入数据库
    with get_db_connection() as conn:
        conn.execute(""" insert into orders(order_id,username,amount,currency,order_type,
        product_id,status,created_at) values (?,?,?,?,?,?,?,?)"""
        ,(order_id,username,amount,currency.upper(),order_type.upper(),product_id,status,created_at))

    return jsonify({
        "order_id": order_id,
        "username": username,
        "amount": round(float(amount), 2),
        "order_type": order_type.upper(),
        "currency": currency.upper(),
        "product_id": product_id,
        "status": status,
        "created_at": created_at
    }), 201


@app.route('/api/v1/ecdsa/order', methods=['POST'])
def create_order_ecdsa():
    """
    使用 ECDSA (SECP256k1) 签名创建订单
    Headers:
      X-API-Key: <base64_public_key>   # 未压缩格式，65字节，以04开头
      X-Timestamp: <unix_timestamp>
      X-Nonce: <unique_string>
      X-Signature: <base64(signature)>
    Body: JSON
    """
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    public_key_b64 = request.headers.get('X-API-Key')
    timestamp = request.headers.get('X-Timestamp')
    nonce = request.headers.get('X-Nonce')
    signature = request.headers.get('X-Signature')

    if not all([public_key_b64, timestamp, nonce, signature]):
        return jsonify({"error": "Missing required headers: X-API-Key, X-Timestamp, X-Nonce, X-Signature"}), 400

    body = request.get_data(as_text=True) or ""
    try:
        json.loads(body)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON body"}), 400

    query_params = dict(parse_qsl(request.query_string.decode('utf-8'))) if request.query_string else {}

    if not verify_ecdsa_signature(public_key_b64, signature, request.method, request.path, query_params, body, timestamp, nonce):
        return jsonify({"error": "Invalid ECDSA signature"}), 401

    data = json.loads(body)
    amount = data.get('amount')
    order_type = data.get('order_type')
    currency = data.get('currency', 'CNY')
    product_id = data.get('product_id')

    if not isinstance(amount, (int, float)) or amount <= 0 or amount > 100000:
        return jsonify({"error": "Invalid amount"}), 400
    if not product_id or len(str(product_id)) not in range(2, 9):
        return jsonify({"error": "Invalid product_id"}), 400
    if currency.upper() not in ['CNY', 'USD']:
        return jsonify({"error": "Invalid currency"}), 400
    if order_type.upper() not in ['DEPOSIT', 'WITHDRAW', 'PAYMENT']:
        return jsonify({"error": "Invalid order_type"}), 400

    order_id = f"ORD{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = 'CREATED'
    #插入数据库
    with get_db_connection() as conn:
        conn.execute(""" insert into orders(order_id,username,amount,currency,order_type,
        product_id,status,created_at) values (?,?,?,?,?,?,?,?)"""
        ,(order_id,username,amount,currency.upper(),order_type.upper(),product_id,status,created_at))

    return jsonify({
        "order_id": order_id,
        "username": username,
        "amount": round(float(amount), 2),
        "order_type": order_type.upper(),
        "currency": currency.upper(),
        "product_id": product_id,
        "status": "CREATED",
        "created_at": created_at
    }), 201






@app.route('/api/login', methods=['POST'])
def login():
    '''登陆'''
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "用户名或密码不能为空"}), 400

    with get_db_connection() as conn:
        row = conn.execute("select password from users where username=?",(username.lower(),)).fetchone()
        if not row or  row['password']!=password:
            return jsonify({"error": "用户名或密码错误"}), 401

    token = str(uuid.uuid4())
    now = datetime.now()
    expires = now + timedelta(hours=1)
    now_at = now.strftime('%Y-%m-%d %H:%M:%S.%f')
    expires_at =expires.strftime('%Y-%m-%d %H:%M:%S.%f')

    with get_db_connection() as conn:
        # 删除旧token ,插入新token，防止多个token存在
        conn.execute('''delete from tokens where username=?''', ( username.lower(),))
        conn.execute('''insert into tokens values (?,?,?,?)''', (token,username.lower(),now_at,expires_at))

    return jsonify({"access_token": token,"info":"登陆成功"})





@app.route('/api/account/balance', methods=['GET'])
def get_balance():
    '''查看账户余额'''
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    with get_db_connection() as conn:
        row = conn.execute("select balance from accounts where username=?",(username,)).fetchone()
        if not row:
            return jsonify({"username":username,"error": "账户不存在"}),404
        balance = row['balance']

    return jsonify({"username": username, "balance": balance})


@app.route('/api/account/transactions', methods=['GET'])
def get_transactions():
    '''查看交易流水'''
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    with get_db_connection() as conn:
        rows = conn.execute("select id,username,type,amount,time from transactions where username=? order by time desc",(username,)).fetchall()
        transactions = [ dict(row) for row in rows]

    return jsonify({"username": username,"transactions":transactions})




@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    '''查看订单记录'''
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    with get_db_connection() as conn:
        row = conn.execute("select * from orders where order_id=? and username=? ",(order_id,username)).fetchone()

    if not row:
        return jsonify({"error": "Order not found"}), 404

    return jsonify(dict(row))


@app.route('/api/orders', methods=['POST'])
def create_order():
    '''创建订单'''
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    data = request.get_json()
    amount = data.get('amount')
    order_type = data.get('order_type')
    currency = data.get('currency', 'CNY') # 不传默认cny
    product_id = data.get('product_id')

    # 金额不能为空
    if amount is None or amount == "" :
        return jsonify({"error": "Invalid amount"}), 400
    #金额必须为数字格式
    if not isinstance(amount, (int,float)):
        return jsonify({"error": "Invalid amount"}), 400
    #金额不能超过3位小数
    if '.' in str(amount) and len(str(amount).split('.')[1])>2:
        return jsonify({"error": "金额最多只能有2位小数"}), 422
    #金额不能小于0
    if amount <= 0:
        return jsonify({"error": "金额不能小于0"}), 422
    #金额不能超过10000
    if amount > 100000:
        return jsonify({"error": "金额不能超过100000"}),422
    # product_id 不能为空
    if not product_id:
        return jsonify({"error": "Invalid product_id"}), 400
    # product_id 长度要在2-8位之间
    if len(str(product_id)) < 2  or len(str(product_id))>8:
        return jsonify({"error": "product_id长度要在2-8之间"}), 422
    # currency输入要符合要求，只能是CNY USD 之中的
    if  currency.upper() not in ['CNY', 'USD']:
        return jsonify({"error": "currency格式输入错误"}), 400
    # type不能为空
    if not order_type:
        return jsonify({"error": "Invalid order_type"}), 400
    # type 输入只能在DEPOSIT, WITHDRAW, PAYMENT之中
    if order_type.upper() not in ['DEPOSIT', 'WITHDRAW', 'PAYMENT']:
        return jsonify({"error": "order_type格式输入错误"}), 400

    #查询数据库用户余额
    with get_db_connection() as conn:
        row = conn.execute("select balance from accounts where username=? ",(username,)).fetchone()
        if not row:
            return jsonify({"error":"账户不存在"}),404
    #创建支出-订单余额 不能大于当前用户余额
    amount = round( float(amount), 2)
    if amount > row['balance'] and order_type in ['PAYMENT', 'WITHDRAW']:
        return jsonify({"error":"当前订单金额超过账户余额"}), 422
    # 👇 加这一行 👇
    app.logger.info(f"[DEBUG] 用户 {username} 的当前余额: {row['balance']}, 订单金额: {amount}, 类型: {order_type}")
    order_id = f"ORD{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = 'CREATED' #默认订单状态是创建
    #插入数据库
    with get_db_connection() as conn:
        conn.execute(""" insert into orders(order_id,username,amount,currency,order_type,
        product_id,status,created_at) values (?,?,?,?,?,?,?,?)"""
        ,(order_id,username,amount,currency.upper(),order_type.upper(),product_id,status,created_at))

    return( {
        "order_id": order_id,
        "username": username,
        "amount": amount,
        "order_type": order_type.upper(),
        "currency": currency.upper(),
        "product_id": product_id,
        "status": status,
        "created_at": created_at
    }), 201

@app.route('/api/GetUploads', methods=['GET'])
def list_uploads():
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401
    limit = request.args.get('limit',default=10,type=int)
    limit = min(max(limit,1),100)
    with get_db_connection() as conn:
        rows = conn.execute('''select id,filename,original_name,
        file_size,username,upload_time from uploads where username=?
         order by upload_time desc limit ?''' ,(username,limit)).fetchall()

    return jsonify([dict(row) for row in rows ]), 200


@app.route('/api/upload', methods=['POST'])
def upload_file():
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401
    # 缺少文件上传属性
    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files['file']
    # 点击了上传按钮，但没选择文件->上传文件为为空
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    # 文件上传格式校验
    ext = os.path.splitext(file.filename)[1].lstrip('.').lower()
    ALLOWED_MIMETYPES ={'jpg','jpeg','png'}
    if ext not in ALLOWED_MIMETYPES:
        return jsonify({"error": f"上传图片格式错误，支持的格式：'jpg','jpeg','png'"}), 400
    # 文件上传大小校验
    # 100k = 100 * 1024 字节
    original_name = file.filename
    file_name = f"{uuid.uuid4().hex}_{secure_filename(original_name)}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
    file.save(filepath)
    file_size = os.path.getsize(filepath)
    MAX_FILE_SIZE = 100* 1024
    if file_size > MAX_FILE_SIZE:
        os.remove(filepath)
        return jsonify({"error": f"上传文件大小超过最大限制:100k"}), 403


    upload_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db_connection() as conn:
        conn.execute(""" insert into uploads(filename,original_name,file_size,
        username,upload_time) values (?,?,?,?,?)""",
                     (file_name,original_name,file_size,username,upload_time))
    return jsonify({"message": "文件上传成功", "filename": file_name})

@app.route('/api/register', methods=['post'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    confirm_password = data.get('confirm_password')
    phone = data.get('phone')
    email = data.get('email')
    #必填项为空，注册失败
    if not username or not password or not confirm_password:
        return jsonify({"error":"账号或密码不能为空"}),400
    if password != confirm_password:
        return jsonify({"error": "密码和确认密码不一致"}), 403
    #用户名长度在2-10 之间
    if len(username)<2 or len(username)>10:
        return jsonify({"error": "账号长度不在2-10之间"}), 403
    #用户名格式检验：数字+字母
    if not re.match(r"^[a-zA-Z0-9]+$",username):
        return jsonify({"error": "账号只能由数字+字母组成"}), 403
    # 密码长度在6-16 之间
    if len(password)<6 or len(password)>16:
        return jsonify({"error": "密码长度不在6-16之间"}), 403
    #密码格式检验：数字+字母+下划线
    if not re.match(r"^[a-zA-Z0-9_]+$",password):
        return jsonify({"error": "密码只能由数字+字母+下划线组成"}), 403
    # 手机号或邮箱至少填一个
    if not phone and not email:
        return jsonify({"error": "手机号或邮箱至少填写一项"}), 400
    #查询数据库：检查 username / phone / email 是否已存在
    with get_db_connection() as conn:
        # 检查用户名是否重复
        row = conn.execute("select username from users where username=?",(username.lower(),)).fetchone()
        if row:
            return jsonify({"error": "账号已注册，请勿重复注册"}), 403
        # 检查手机号是否已被使用（仅当 phone 非空时）
        if phone:
            phone_row = conn.execute("SELECT phone FROM users WHERE phone = ?", (phone,)).fetchone()
            if phone_row:
                return jsonify({"error": "该手机号已被注册"}), 403
        # 检查邮箱是否已被使用（仅当 email 非空时）
        if email:
            email_row = conn.execute("SELECT email FROM users WHERE email = ?", (email,)).fetchone()
            if email_row:
                return jsonify({"error": "该邮箱已被注册"}), 403


    with get_db_connection() as conn:
        # 11 插入数据库用户表（注意：username 转小写，phone/email 可为 None）
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        conn.execute(
            """
            INSERT INTO users (username, password, phone, email, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username.lower(), password, phone, email, created_at)
        )
        # 2 自动创建账户，初始余额为 0
        conn.execute(
            "INSERT INTO accounts (username, balance) VALUES (?, ?)",
            (username.lower(), 0.0)
        )

    return jsonify({"username": username,"message":"注册成功"})


#flask状态检查
@app.route('/health')
def health():
    return {"status": "ok"}




@app.route('/api/listing/create', methods=['POST'])
def create_listing():
    """用户挂单（卖家发布商品）"""
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    data = request.get_json()
    product_id = data.get('product_id')
    amount = data.get('amount')
    currency = data.get('currency', 'CNY')

    # 参数校验
    if not product_id or len(str(product_id)) not in range(2, 9):
        return jsonify({"error": "Invalid product_id"}), 400
    if not isinstance(amount, (int, float)) or amount <= 0 or amount > 100000:
        return jsonify({"error": "Invalid amount"}), 400
    if currency.upper() not in ['CNY', 'USD']:
        return jsonify({"error": "Invalid currency"}), 400

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "LISTED"
    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO listings (seller_username, product_id, amount, currency, created_at,status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, product_id, amount, currency.upper(), created_at,status))
        listing_id = cursor.lastrowid

    return jsonify({
        "message": "Listing created successfully",
        "listing_id": listing_id,
        "seller_username": username,
        "product_id": product_id,
        "amount": round(float(amount), 2),
        "currency": currency.upper(),
        "status": status,
        "created_at": created_at
    }), 201

@app.route('/api/listing/cancel', methods=['POST'])
def cancel_listing():
    """卖家取消自己的挂单"""
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    data = request.get_json()
    listing_id = data.get('listing_id')

    with get_db_connection() as conn:
        # 查询挂单是否存在、是否属于当前用户、是否可取消
        listing = conn.execute("""
            SELECT id, seller_username, status
            FROM listings
            WHERE id = ?
        """, (listing_id,)).fetchone()

        if not listing:
            return jsonify({"error": "Listing not found"}), 404

        if listing['seller_username'] != username:
            return jsonify({"error": "You can only cancel your own listing"}), 403

        if listing['status'] != 'LISTED':
            return jsonify({"error": "Only LISTED listings can be canceled"}), 400

        # 执行取消：更新状态为 CANCELED
        conn.execute("""
            UPDATE listings SET status = 'CANCELLED' WHERE id = ? """, (listing_id,))

    return jsonify({
        "message": "Listing canceled successfully",
        "listing_id": listing_id,
        "status": "CANCELLED"
    }), 200

@app.route('/api/purchase/create/ecdsa', methods=['POST'])
def create_purchase_order_ecdsa():
    """
    使用 ECDSA (SECP256k1) 签名创建购买订单（买家下单）
    Headers:
      X-API-Key: <base64_public_key>   # 未压缩格式，65字节，以04开头
      X-Timestamp: <unix_timestamp>
      X-Nonce: <unique_string>
      X-Signature: <base64(signature)>
    Body: JSON with listing_id and purchase_amount
    """
    # Step 1: 验证 Token 获取用户名
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    # Step 2: 提取并校验 ECDSA 所需 headers
    public_key_b64 = request.headers.get('X-API-Key')
    timestamp = request.headers.get('X-Timestamp')
    nonce = request.headers.get('X-Nonce')
    signature = request.headers.get('X-Signature')

    if not all([public_key_b64, timestamp, nonce, signature]):
        return jsonify({"error": "Missing required headers: X-API-Key, X-Timestamp, X-Nonce, X-Signature"}), 400

    # Step 3: 获取并校验请求体为合法 JSON
    body = request.get_data(as_text=True) or ""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON body"}), 400

    # Step 4: 解析 query params（用于签名）
    query_params = dict(parse_qsl(request.query_string.decode('utf-8'))) if request.query_string else {}

    # Step 5: 验证 ECDSA 签名（复用原有逻辑）
    if not verify_ecdsa_signature(public_key_b64, signature, request.method, request.path, query_params, body, timestamp, nonce):
        return jsonify({"error": "Invalid ECDSA signature"}), 401

    # Step 6: 从 body 中提取参数（与 create_purchase_order 一致）
    listing_id = data.get('listing_id')
    purchase_amount = data.get('purchase_amount')

    if purchase_amount is None:
        return jsonify({"error": "purchase_amount is required"}), 400
    try:
        purchase_amount = float(purchase_amount)
    except (ValueError, TypeError):
        return jsonify({"error": "purchase_amount must be a valid number"}), 400
    if purchase_amount <= 0:
        return jsonify({"error": "purchase_amount must be greater than 0"}), 400
    if '.' in str(purchase_amount):
        integer_part, decimal_part = str(purchase_amount).split('.', 1)
        if len(decimal_part) > 2:
            return jsonify({"error": "purchase_amount cannot have more than 2 decimal places"}), 400

    if not listing_id:
        return jsonify({"error": "Missing listing_id"}), 400

    # Step 7: 数据库操作（完全复用 create_purchase_order 的逻辑）
    with get_db_connection() as conn:
        listing = conn.execute("""
            SELECT id, seller_username, product_id, amount, currency, status
            FROM listings WHERE id = ?
        """, (listing_id,)).fetchone()

        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        if listing['status'] != 'LISTED':
            return jsonify({"error": "Listing is not available for purchase"}), 400
        if listing['seller_username'] == username:
            return jsonify({"error": "Cannot buy your own listing"}), 400

        existing = conn.execute("""
            SELECT id FROM purchase_orders 
            WHERE listing_id = ? AND buyer_username = ?
        """, (listing_id, username)).fetchone()
        if existing:
            return jsonify({"error": "You have already placed an order for this listing"}), 400

        listing_amount = float(listing['amount'])
        if purchase_amount > listing_amount:
            return jsonify({
                "error": "purchase_amount cannot exceed listing amount",
                "listing_amount": round(listing_amount, 2),
                "purchase_amount": purchase_amount
            }), 400

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.execute("""
            INSERT INTO purchase_orders (
                listing_id, buyer_username, amount, currency, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            listing_id,
            username,
            purchase_amount,
            listing['currency'],
            created_at
        ))
        order_id = cursor.lastrowid

    return jsonify({
        "message": "Purchase order created and pending review",
        "listing_id": listing_id,
        "buyer_username": username,
        "amount": round(float(purchase_amount), 2),
        "currency": listing['currency'],
        "status": "PENDING_REVIEW",
        "order_id": order_id,
        "created_at": created_at
    }), 201

@app.route('/api/purchase/create', methods=['POST'])
def create_purchase_order():
    """用户购买挂单商品（买家下单）"""
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    data = request.get_json()
    listing_id = data.get('listing_id')
    purchase_amount = data.get('purchase_amount')
    if purchase_amount is None:
        return jsonify({"error": "purchase_amount is required"}), 400
    try:
        # 转为 float 并检查是否为有效数字
        purchase_amount = float(purchase_amount)
    except (ValueError, TypeError):
        return jsonify({"error": "purchase_amount must be a valid number"}), 400
    # 检查是否为正数
    if purchase_amount <= 0:
        return jsonify({"error": "purchase_amount must be greater than 0"}), 400
    # 检查是否超过小数点2位
    if '.' in str(purchase_amount):
        # 分割整数部分和小数部分
        integer_part, decimal_part = str(purchase_amount).split('.', 1)
        # 检查小数部分的长度
        if len(decimal_part) > 2:
            return jsonify({"error": "purchase_amount cannot have more than 2 decimal places"}), 400

    #检查是否有挂单id
    if not listing_id:
        return jsonify({"error": "Missing listing_id"}), 400

    with get_db_connection() as conn:
        # 查询挂单是否存在且未售出
        listing = conn.execute("""
            SELECT id, seller_username, product_id, amount, currency, status
            FROM listings WHERE id = ?
        """, (listing_id,)).fetchone()

        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        if listing['status'] != 'LISTED':
            return jsonify({"error": "Listing is not available for purchase"}), 400
        if listing['seller_username'] == username:
            return jsonify({"error": "Cannot buy your own listing"}), 400

        # 检查是否已对该挂单提交过购买请求（防重复）
        existing = conn.execute("""
            SELECT id FROM purchase_orders 
            WHERE listing_id = ? AND buyer_username = ?
        """, (listing_id, username)).fetchone()
        if existing:
            return jsonify({"error": "You have already placed an order for this listing"}), 400

        # ：校验 purchase_amount 不超过挂单金额
        listing_amount = float(listing['amount'])
        if purchase_amount > listing_amount:
            return jsonify({
                "error": "purchase_amount cannot exceed listing amount",
                "listing_amount": round(listing_amount, 2),
                "purchase_amount": purchase_amount
            }), 400

        # 创建购买订单（使用 purchase_amount 而非 listing 全额）
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = conn.execute("""
            INSERT INTO purchase_orders (
                listing_id, buyer_username, amount, currency, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            listing_id,
            username,
            purchase_amount,  # ← 使用用户指定的购买金额
            listing['currency'],
            created_at
        ))
        order_id = cursor.lastrowid
    return jsonify({
        "message": "Purchase order created and pending review",
        "listing_id": listing_id,
        "buyer_username": username,
        "amount": round(float(purchase_amount), 2),
        "currency": listing['currency'],
        "status": "PENDING_REVIEW",
        "order_id":order_id,
        "created_at": created_at
    }), 201


@app.route('/api/listing', methods=['POST'])
def get_listing():
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401

    data = request.get_json()
    if not data or 'listing_id' not in data:
        return jsonify({"error": "缺少 listing_id 参数"}), 400

    listing_id = data['listing_id']

    try:
        listing_id = int(listing_id)
    except (TypeError, ValueError):
        return jsonify({"error": "listing_id 必须为整数"}), 400

    with get_db_connection() as conn:
        row = conn.execute("""
            SELECT id, seller_username, product_id, amount, currency, status, created_at, sold_at
            FROM listings
            WHERE id = ?
        """, (listing_id,)).fetchone()

    if not row:
        return jsonify({"error": "挂单不存在"}), 404
    if row["seller_username"] != username:
        return jsonify({"error": "无权查看他人的挂单"}), 403

    response = {
        "success": True,
        "data": {
            "id": row["id"],
            "seller_username": row["seller_username"],
            "product_id": row["product_id"],
            "amount": row["amount"],
            "currency": row["currency"],
            "status": row["status"],
            "created_at": row["created_at"],
            "sold_at": row["sold_at"]
        }
    }

    return jsonify(response), 200





@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    """管理员登录（使用 admins 表）"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username or password cannot be empty"}), 400

    with get_db_connection() as conn:
        row = conn.execute("SELECT username,role,password FROM admins WHERE username = ?", (username,)).fetchone()
        if not row or row['password'] != password:
            return jsonify({"error": "Invalid admin credentials"}), 401
    # 生成管理员专用 token（可复用 tokens 表，但建议隔离；此处为简化复用）
    token = str(uuid.uuid4())
    now = datetime.now()
    expires = now + timedelta(hours=1)
    now_at = now.strftime('%Y-%m-%d %H:%M:%S.%f')
    expires_at = expires.strftime('%Y-%m-%d %H:%M:%S.%f')

    with get_db_connection() as conn:
        conn.execute("DELETE FROM tokens WHERE username = ?", (username,))
        conn.execute("INSERT INTO tokens (token, username, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     (token, username, now_at, expires_at))

    return jsonify({
        "access_token": token,
        "role": row['role'] ,
        "message": f"{username} login successful"
    })


@app.route('/api/admin/review_purchase', methods=['POST'])
def review_purchase_order():
    """管理员审核购买订单"""
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401


    # 验证是否为ADMIN管理员（检查 admins 表）,非admin管理员无法审批
    with get_db_connection() as conn:
        row = conn.execute("SELECT role FROM admins WHERE username = ?", (username,)).fetchone()
        if row is None or row[0] != "ADMIN":
            return jsonify({"error": "Insufficient permissions"}), 403

    data = request.get_json()
    order_id = data.get('order_id')
    action = data.get('action')  # 'approve' 或 'reject'

    if not order_id or action not in ['approve', 'reject'] or not action :
        return jsonify({"error": "Invalid order_id or action"}), 400

    with get_db_connection() as conn:
        po = conn.execute("""
            SELECT id, listing_id, amount,buyer_username,status FROM purchase_orders WHERE id = ?
        """, (order_id,)).fetchone()

        if not po:
            return jsonify({"error": "Purchase order not found"}), 404
        if po['status'] != 'PENDING_REVIEW':
            return jsonify({"error": "Order is not pending review"}), 400

        reviewed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_status = 'COMPLETED' if action == 'approve' else 'REJECTED'

        # 更新 purchase_orders
        conn.execute("""
            UPDATE purchase_orders
            SET status = ?, reviewed_at = ?, reviewed_by = ?, review_action = ?
            WHERE id = ?
        """, (new_status, reviewed_at, username, action, order_id))

        if action == 'approve':
            # 获取卖家 ID
            listing = conn.execute("""
                            SELECT seller_username FROM listings WHERE id = ?
                        """, (po['listing_id'],)).fetchone()
            if not listing:
                return jsonify({"error": "Listing not found"}), 404
            seller_username = listing['seller_username']
            buyer_username = po['buyer_username']
            amount = po['amount']
            #出售用户扣减对应挂单金额
            conn.execute("""
                            UPDATE accounts SET balance = balance - ? WHERE username = ?
                        """, (amount, seller_username))
            # 购买用户增加对应挂单金额
            conn.execute("""
                            UPDATE accounts SET balance = balance + ? WHERE username = ?
                        """, (amount, buyer_username))
            # 同时更新 listings 状态为 SOLD
            conn.execute("""
                UPDATE listings SET status = 'SOLD', sold_at = ?
                WHERE id = ?
            """, (reviewed_at, po['listing_id']))

    return jsonify({
        "order_id": order_id,
        "action": action,
        "new_status": new_status,
        "reviewed_by": username,
        "reviewed_at": reviewed_at
    })


from decimal import Decimal, InvalidOperation

@app.route('/api/admin/update_balance', methods=['POST'])
def admin_update_balance():
    """管理员后台更新用户余额"""
    username = verify_token(request.headers.get('Authorization'))
    if not username:
        return jsonify({"error": "Invalid or missing token"}), 401


    # 验证是否为ADMIN管理员（检查 admins 表）,非admin管理员无法更新
    with get_db_connection() as conn:
        row = conn.execute("SELECT role FROM admins WHERE username = ?", (username,)).fetchone()
        if row is None or row[0] != "ADMIN":
            return jsonify({"error": "Insufficient permissions"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体不能为空"}), 400

    target_username = data.get('username')
    amount = data.get('amount')

    if not target_username:
        return jsonify({"error": "username 不能为空"}), 400
    if amount is None:
        return jsonify({"error": "amount 不能为空"}), 400

    # 校验金额
    try:
        amount_decimal = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return jsonify({"error": "amount 必须为有效数字"}), 400

    if amount_decimal == 0:
        return jsonify({"error": "amount 不能为 0"}), 400

    if amount_decimal.as_tuple().exponent < -2:
        return jsonify({"error": "amount 最多保留 2 位小数"}), 400

    amount_float = float(amount_decimal)

    with get_db_connection() as conn:
        # 检查用户是否存在（通过 users 表）
        user_exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (target_username,)
        ).fetchone()
        if not user_exists:
            return jsonify({"error": "用户不存在"}), 404

        # 获取当前余额（从 accounts 表）
        account_row = conn.execute(
            "SELECT balance FROM accounts WHERE username = ?", (target_username,)
        ).fetchone()

        if not account_row:
            # 理论上不应发生（注册时已创建），但做兜底
            return jsonify({"error": "账户未初始化"}), 500

        current_balance = account_row["balance"]
        new_balance = round(current_balance + amount_float, 2)

        # 防止负余额
        if new_balance < 0:
            return jsonify({"error": "操作后余额不能为负"}), 400

        # 更新 accounts 表
        conn.execute(
            "UPDATE accounts SET balance = ? WHERE username = ?",
            (new_balance, target_username)
        )

    return jsonify({
        "success": True,
        "data": {
            "username": target_username,
            "new_balance": new_balance,
            "adjustment": amount_float
        }
    }), 200

if __name__ == '__main__':
    # 在 app.run() 前添加
    with get_db_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")  # 确保外键约束
        cursor = conn.execute("PRAGMA database_list")
        print("API 使用的数据库路径:", cursor.fetchone()[2])
    init_db()  # 确保数据库表已创建
    app.run(host='0.0.0.0', port=5000, debug=False,use_reloader=False)