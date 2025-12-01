# coding = utf-8
import time
import uuid
import hmac
import hashlib
import base64
from hmac import digest
from urllib.parse import urlencode,quote
from ecdsa import VerifyingKey, SECP256k1, SigningKey
from ecdsa.util import sigencode_string

def _normalize_request_data(method:str,path:str,query_params: dict = None,body: str = "",timestamp: int= "",nonce: str = "") -> str:
    """
      根据服务端规则构造待签名字符串。
    示例格式（请根据你后端实际规则调整）：
        METHOD\nPATH\nQUERY_STRING\nBODY\nTIMESTAMP\nNONCE
    """
    if query_params == None:
        query_params = {}
    # 排序并编码（空 dict → ""）
    sorted_query = urlencode(sorted(query_params.items()),safe='',quote_via=quote) if query_params else ""
    return f"{method}\n{path}\n{sorted_query}\n{body}\n{timestamp}\n{nonce}"




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

# ======================
# HMAC-SHA256 签名
# ======================
def hmac_signature(api_key:str, api_secret:str,method: str,path: str ,
                   query_params: dict =None, body: dict=None,timestamp: str="", nonce:str="") -> dict[str, str]:
    """
     生成 HMAC-SHA256 签名请求头。

     返回示例：
     {
         "X-API-Key": "your_key",
         "X-Timestamp": "1712345678",
         "X-Nonce": "a1b2c3d4...",
         "X-Signature": "base64_encoded_hmac..."
     }
     """
    if timestamp == "":
        timestamp = str(int(time.time()))
    if nonce == "":
        nonce = str(uuid.uuid4())

    message = _normalize_request_data(method, path, query_params,body, timestamp, nonce).encode("utf-8")
    signature =base64.b64encode(hmac.new(api_secret.encode('utf-8'), message, hashlib.sha256).digest()).decode(
        'utf-8')

    return  {
         "X-API-Key": api_key,
         "X-Timestamp": str(timestamp),
         "X-Nonce": nonce,
         "X-Signature": signature
     }
# ======================
# ECDSA (SECP256k1) 签名
# ======================

def ecdsa_signature(api_secret: str,method: str,path: str ,
                   query_params: dict =None, body: dict=None,timestamp: str="", nonce:str="") -> dict[str, str]:
    """
    使用 ECDSA (SECP256k1) 私钥生成签名请求头。

    参数：
        private_key_hex: 32字节私钥的十六进制字符串（不含 0x）

    返回示例：
    {
        "X-API-Key": "base64_uncompressed_public_key",
        "X-Timestamp": "1712345678",
        "X-Nonce": "a1b2c3d4...",
        "X-Signature": "base64_encoded_signature..."
    }
    """
    if timestamp == "":
        timestamp = str(int(time.time()))
    if nonce == "":
        nonce = str(uuid.uuid4())

    message = _normalize_request_data(method, path, query_params,body, timestamp, nonce).encode("utf-8")
    digest  = hashlib.sha256(message).digest()
    # 从私钥生成签名
    private_key_bytes = bytes.fromhex(api_secret)
    sk = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
    signature_bytes = sk.sign_digest_deterministic(digest, hashfunc=hashlib.sha256, sigencode=sigencode_string)
    signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")
    # 生成公钥（用于 X-API-Key）
    vk = sk.verifying_key
    public_key_uncompressed = b'\x04' + vk.to_string()  # 未压缩格式
    public_key_b64 = base64.b64encode(public_key_uncompressed).decode("utf-8")

    return {
        "X-API-Key": public_key_b64,
        "X-Timestamp": str(timestamp),
        "X-Nonce": nonce,
        "X-Signature": signature_b64
    }

# ======================
# md5签名
# ======================
def md5_signature(api_secret: dict,params: dict) -> str:
    """
        使用 md5加盐签名

    """
    body={**params,"secret":api_secret}
    signing_str = _build_query_string(body)
    md5_digest = hashlib.md5(signing_str.encode('utf-8')).digest()
    return base64.b64encode(md5_digest).decode('ascii')



