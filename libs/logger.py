# coding = utf-8
# author =fufu
import logging
import os
import json
from pathlib import Path

#创建日志目录
project_root = Path(__file__).parent.parent # 项目根目录
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)

logger = logging.getLogger('logger') #创建名为"logger"的日志器（相同名称会返回同一实例）
logger.setLevel(logging.INFO) #	只记录INFO及以上级别（DEBUG信息会被忽略）

if not logger.handlers:
    log_file = log_dir/ "test.log"
    #  mode='w' 实现覆盖写入 ，默认 mode='a' 追加
    handler = logging.FileHandler( str(log_file) ,mode='w',encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s  - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

def log_test_action(action: str, details: str  =""):
    """记录 API 请求/操作"""
    logger.info(f"[ACTION] {action} | {details}")

def log_assertion(case_name: str,passed: bool,actual=None,expected=None,message: str=""):
    """记录断言结果，便于审计"""
    status = "✅ PASS" if passed else "❌ FAIL"
    log_msg = f"[ASSERT] Case='{case_name}'|{status}"
    if not passed:
        log_msg += f" | Actual={actual} | Expected={expected} |Reason={message} "
    logger.info(log_msg)
