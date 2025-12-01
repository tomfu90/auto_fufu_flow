# coding = utf-8
# author = fufu

from typing import Any, Dict, List


def validate_order_test_cases(yaml_data: Dict[str, Any]) -> None:
    """
    校验订单测试用例 YAML 文件结构（专用于 test_create_purchase_order.yaml 类型）

    支持结构：
      test_cases:
        success_cases: [...]
        fail_cases: [...]
    """
    test_cases = yaml_data
    if not isinstance(test_cases, dict):
        raise ValueError("'test_cases' 必须是字典")

    # 收集所有用例：(分组名, 索引, 用例)
    all_cases: List[tuple[str, int, Dict[str, Any]]] = []
    for group_name in ("success_cases", "fail_cases"):
        cases: List[Dict[str, Any]] = test_cases.get(group_name, [])
        if not isinstance(cases, list):
            raise ValueError(f"'{group_name}' 必须是列表")
        for i, case in enumerate(cases):
            all_cases.append((group_name, i, case))

    if not all_cases:
        raise ValueError("至少需要一个测试用例（在 success_cases 或 fail_cases 中）")


    for group, idx, case in all_cases:
        path = f"{group}[{idx + 1}]"

        if not isinstance(case, dict):
            raise ValueError(f"{path} 不是字典")

        # 必填字段
        for field in ("name",  "input", "expected"):
            if field not in case:
                raise ValueError(f"{path} 缺少必填字段: '{field}'")

        # 字段类型与非空校验
        name = case["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}.name 必须是非空字符串")

        inp = case["input"]
        if not isinstance(inp, dict):
            raise ValueError(f"{path}.input 必须是字典")
        if "username" not in inp:
            raise ValueError(f"{path}.inp 缺少 'username'")
        if "username"  in inp:
            if not isinstance(inp["username"], str) and inp["username"] is not None:
                raise ValueError(f"{path}.input.username={inp['username']} 不合法，必须为字符串或 null")
        if "password" not in inp:
            raise ValueError(f"{path}.inp 缺少 'password'")
        if "password"  in inp:
            if not isinstance(inp["password"], str) and inp["password"] is not None:
                raise ValueError(f"{path}.input.password={inp['password']} 不合法，必须为字符串或 null")
        if "confirm_password" not in inp:
            raise ValueError(f"{path}.inp 缺少 'confirm_password'")
        if "confirm_password"  in inp:
            if not isinstance(inp["confirm_password"], str) and inp["confirm_password"] is not None:
                raise ValueError(f"{path}.input.confirm_password={inp['confirm_password']} 不合法，必须为字符串或 null")
        if "phone" not in inp:
            raise ValueError(f"{path}.inp 缺少 'phone'")
        if "phone"  in inp:
            if not isinstance(inp["phone"], str) :
                raise ValueError(f"{path}.input.phone={inp['phone']} 不合法，必须为字符串)")
        if "email" not in inp:
            raise ValueError(f"{path}.inp 缺少 'email'")
        if "email"  in inp:
            if not isinstance(inp["email"], str) :
                raise ValueError(f"{path}.input.email={inp['email']} 不合法，必须为字符串)")



        exp = case["expected"]
        if not isinstance(exp, dict):
            raise ValueError(f"{path}.expected 必须是字典")
        if "status_code" not in exp:
            raise ValueError(f"{path}.expected 缺少 'status_code'")
        if "message" in exp:
            if not isinstance(exp["message"], str) :
                raise ValueError(
                    f"{path}.expected.action='{exp["message"]}' 不合法，")
        if "error"   in exp:
            if not isinstance(exp["error"], str) :
                raise ValueError(f"{path}.expected.error 必须是非空字符串")
