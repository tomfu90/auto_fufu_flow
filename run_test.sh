#!/bin/bash
# run_test.sh

cd "$(dirname "$0")"

# 激活虚拟环境（注意：Jenkins 脚本已创建 .venv）
source .venv/bin/activate

# 执行测试，仅生成 results（不生成 HTML！）
pytest tests --alluredir=./report/allure-results "$@"