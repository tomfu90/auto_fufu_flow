# coding = utf-8
# author = fufu
"""
统一工具函数
目的：避免代码重复
"""
from pathlib import Path
import yaml
import re
import sys

root_dir = Path(__file__).parent.parent
#如果根目录不存在 sys.path，就插在最前面
if str(root_dir) not in sys.path:
    sys.path.insert(0,str(root_dir))

from libs.random_utils import generate_random_username,generate_random_email,generate_random_phone

def load_yaml(filepath: str):
    '''
    加载yaml文件
    :param filepath: 相对于项目根路径的目录
    :return: yaml解析后的字典
    '''
    base_path = Path(__file__).parent.parent #项目根目录
    full_path = base_path / filepath #完整文件路径
    #首先判断文件路径是否存在，不存在抛异常
    if not full_path.exists():
        raise FileNotFoundError(f"文件路径不存在：{full_path}")
    #文件路径存在，读取yaml文件内容
    with open(full_path, 'r', encoding='utf-8') as f:
        return  yaml.safe_load(f)


def render_placeholders(obj, context):
    """
    递归替换数据中的占位符： 3种形式
      - {{key}} → 来自 context（如 random_username）
      - {{key1.key2}}  → 来自 context 嵌套上下文（如 sell.username）
      - ${en.key} → 来自 context  获取的环境变量，前缀en.
    """
    if isinstance(obj, dict):
        return {k: render_placeholders(v, context) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [render_placeholders(item, context) for item in obj]
    elif isinstance(obj, str):
        def replace_match(match):
            path = match.group(1)  # 如 "buyer_reg.username"
            keys = path.split('.')  # ['buyer_reg', 'username']
            value = context
            try:
                for key in keys:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        raise KeyError(f"路径 '{path}' 中的键 '{key}' 未找到")
                return str(value)
            except (KeyError, TypeError) as e:
                raise KeyError(f"占位符 '{{{{{path}}}}}' 解析失败: {e}")
        # 允许占位符包含字母、数字、下划线、点号
        return re.sub(r"\{\{([a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*)\}\}", replace_match, obj)
    else:
        return obj


def load_test_cases(yaml_path):
    """
    加载 YAML 文件，并自动替换占位符（如 {{random_username}}）
    返回渲染后的 Python 对象
    """
    raw_data = load_yaml(yaml_path)
    # 第2步：准备一个空字典，用于存放渲染后的结果
    rendered = {}
    # 第3步：分别处理两个关键部分：成功用例 和 失败用例
    for section in ['success_cases', 'fail_cases']:
        if section in raw_data:
            # 初始化该部分的列表（例如 rendered['fail_register'] = []）
            rendered[section] = []
            # 第4步：遍历该部分下的每一个测试用例（case）
            for case in raw_data[section]:
                # 为当前这个 case 单独生成一组新的随机值
                context = {
                    "random_username": generate_random_username(),  # 比如 "auo9xk2m"
                    "random_email": generate_random_email(),  # 比如 "auo123abc@test.com"
                    "random_phone": generate_random_phone()  # 比如 "13812345678"
                }
                # 第5步：用这一组 context 去渲染当前 case 的所有字段
                rendered_case = render_placeholders(case, context)
                # 第6步：把渲染好的 case 加入结果列表
                rendered[section].append(rendered_case)
        else:
            # 如果 YAML 中没有这个 section（比如漏写了），就设为空列表，避免报错
            rendered[section] = []

    # 第7步：返回最终结构：{ "success_register": [...], "fail_register": [...] }
    return rendered


if __name__ == '__main__':
    print(load_test_cases("data/login/test_register.yaml"))