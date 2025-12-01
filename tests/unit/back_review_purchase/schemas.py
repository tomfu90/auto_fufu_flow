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
    if  "test_cases" not in yaml_data:
        raise ValueError("顶层必须包含 'test_cases' 字段")

    test_cases = yaml_data["test_cases"]
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

    VALID_MARKS = {"exist", "null_id", "nonexistent", "canceled", "complete"}

    for group, idx, case in all_cases:
        path = f"{group}[{idx + 1}]"

        if not isinstance(case, dict):
            raise ValueError(f"{path} 不是字典")

        # 必填字段
        for field in ("name", "description", "input", "expected"):
            if field not in case:
                raise ValueError(f"{path} 缺少必填字段: '{field}'")

        # 字段类型与非空校验
        name = case["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}.name 必须是非空字符串")

        description = case["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{path}.description 必须是非空字符串")

        inp = case["input"]
        if not isinstance(inp, dict):
            raise ValueError(f"{path}.input 必须是字典")

        exp = case["expected"]
        if not isinstance(exp, dict):
            raise ValueError(f"{path}.expected 必须是字典")
        if "status_code" not in exp:
            raise ValueError(f"{path}.expected 缺少 'status_code'")
        if "action" in exp:
            if not isinstance(exp["action"], str) :
                raise ValueError(
                    f"{path}.expected.action='{exp["action"]}' 不合法，")
        if "error"   in exp:
            if not isinstance(exp["error"], str) :
                raise ValueError(f"{path}.expected.error 必须是非空字符串")


        # 校验 mark
        if "mark" not in inp:
            raise ValueError(f"{path}.input 缺少 'mark'")
        mark = inp["mark"]
        if not isinstance(mark, str) or mark not in VALID_MARKS:
            raise ValueError(
                f"{path}.input.mark='{mark}' 不合法，"
                f"必须是: {', '.join(sorted(VALID_MARKS))}"
            )

        # 校验 action（允许 None）
        action = inp.get("action")
        if action is not None:
            if not isinstance(action, str) :
                raise ValueError(f"{path}.input.action='{action}' 不合法，")