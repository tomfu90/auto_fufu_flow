# coding = utf-8
# author = fufu

from typing import Any, Dict, List


def validate_order_test_cases(yaml_data: Dict[str, Any]) -> None:
    """
    校验订单测试用例 YAML 文件结构（专用于 test_search_listing.yaml 类型）

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
        for field in ("name",  "description","mark", "expected"):
            if field not in case:
                raise ValueError(f"{path} 缺少必填字段: '{field}'")

        # 字段类型与非空校验
        name = case["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}.name 必须是非空字符串")

        # 字段类型与非空校验
        description = case["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{path}.description 必须是非空字符串")
        # 字段类型与非空校验
        mark = case["mark"]
        if not isinstance(mark, str) or not mark.strip():
            raise ValueError(f"{path}.mark 必须是非空字符串")


        exp = case["expected"]
        if not isinstance(exp, dict):
            raise ValueError(f"{path}.expected 必须是字典")
        if "status_code" not in exp:
            raise ValueError(f"{path}.expected 缺少 'status_code'")
        if "message" in exp:
            if not isinstance(exp["message"], str) :
                raise ValueError(
                    f"{path}.expected.action='{exp["message"]}' 不合法，")
        if "success"   in exp:
            if not isinstance(exp["success"], bool) :
                raise ValueError(f"{path}.expected.success 必须是非空字符串")
