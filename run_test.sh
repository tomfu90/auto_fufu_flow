#!/bin/bash
# run_test.sh
cd "$(dirname "$0")"
source .venv/bin/activate
source set_env.sh  # 加载密钥

# 执行测试并生成Allure结果文件
pytest tests --alluredir=./report/allure-results "$@"

# 生成Allure HTML报告（--clean 覆盖旧报告）
allure generate ./report/allure-results -o ./report/allure-report --clean

# 自动打开报告（可选，Mac/Linux可用）
allure open ./report/allure-report