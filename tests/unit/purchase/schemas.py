# coding = utf-8
# author= fufu
def validate_test_cases(cases, case_type=""):
    """
    校验测试用例 YAML 结构
    - 检查必填字段是否存在
    - 检查关键字段的值是否合法
    """
    # 所有用例都必须包含的字段
    REQUIRED_FIELDS = {
        "name",
        "description",
        "listing_scenario",
        "purchase_amount",
        "dynamic",
        "expected"
    }

    # 合法的 listing_scenario 值（可根据实际调整）
    VALID_SCENARIOS = {"other_active", "self", "canceled", "sold", "nonexistent", "null_id"}

    prefix = f"[{case_type}] " if case_type else ""

    for i, case in enumerate(cases):
        idx = i + 1

        # 1. 必须是字典
        if not isinstance(case, dict):
            raise ValueError(f"{prefix}用例 #{idx} 不是字典类型")

        # 2. 检查必填字段是否缺失
        missing = [f for f in REQUIRED_FIELDS if f not in case]
        if missing:
            raise ValueError(f"{prefix}用例 #{idx} 缺少必填字段: {missing}")

        # 3. 检查 listing_scenario 是否合法
        scenario = case["listing_scenario"]
        if scenario not in VALID_SCENARIOS:
            raise ValueError(
                f"{prefix}用例 #{idx} 的 listing_scenario='{scenario}' 不合法，"
                f"必须是以下之一: {sorted(VALID_SCENARIOS)}"
            )

        # 4. 检查 dynamic 是否为布尔值
        dynamic = case["dynamic"]
        if not isinstance(dynamic, bool):
            raise ValueError(f"{prefix}用例 #{idx} 的 dynamic 必须是布尔值 (true/false)，当前值: {dynamic}")

        # 5. 检查 expected 是否为字典
        expected = case["expected"]
        if not isinstance(expected, dict):
            raise ValueError(f"{prefix}用例 #{idx} 的 expected 必须是字典，当前类型: {type(expected).__name__}")