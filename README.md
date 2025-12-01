auto_flow - 撮合交易系统自动化测试框架
作者：fufu（在线求职测试工作）
一个基于 Python + Flask + Pytest 的全栈自动化测试框架，专注撮合交易场景，支持复杂撮合逻辑验证、多签名机制（ECDSA/HMAC/MD5）、完整 E2E 链路测试、接口 + 数据库双断言与高性能压测方案。
项目徽章
Python 3.10+
Pytest 7.0+
Allure 2.13+
Locust 2.15+
CI 状态
🚀 项目简介
auto_flow 是面向撮合交易系统的轻量级、可扩展自动化测试框架，专为复杂业务场景设计。核心能力包括：
✅ 复杂撮合规则验证（价格优先 / 时间优先 / 最优撮合）
✅ 多签名机制全覆盖（ECDSA/HMAC/MD5）与安全攻击模拟
✅ 完整 E2E 业务链路测试（C2C 交易闭环 / 审核异常场景）
✅ 高性能压测方案（分布式 Locust / 角色分片 / 阶梯加压）
✅ Flask 模拟撮合后端 + SQLite 存储交易数据
✅ 接口 + 数据库双断言（确保撮合结果一致性）
✅ 安全测试专项（时序攻击 / 重放攻击 / 数据篡改）
✅ Allure 可视化报告与 GitHub Actions CI/CD 集成
适用于撮合系统的功能测试、E2E 回归、安全测试、性能压测场景。
🔧 核心功能
功能	说明
🌐 撮合服务模拟	Flask 实现撮合引擎接口（下单 / 撮合匹配 / 成交查询 / 审核）
🧠 复杂撮合逻辑验证	支持价格优先、时间优先等规则的精准校验
🔐 多签名机制测试	覆盖 ECDSA/HMAC/MD5 签名算法，支持合法请求与攻击场景验证
🔄 完整 E2E 场景测试	C2C 交易闭环（审核通过）/ 异常场景（审核拒绝）全链路覆盖
🗃️ SQLite 数据存储	存储订单 / 撮合记录 / 用户资金，支持数据库一致性断言
📄 YAML 驱动用例	结构化编写用例，支持参数化、动态变量与签名配置
🛡️ 安全攻击模拟	时序攻击 / 重放攻击 / 数据篡改 / 秘钥错误等场景验证
📊 Allure 报告	分步骤展示撮合流程、签名验证、断言结果，可视化强
⚡ 高性能压测	分布式 Locust 压测 / 角色分片 / 阶梯加压 / 并发安全控制
🔄 CI/CD 集成	GitHub Actions 自动触发测试，生成报告并归档
📋 测试用例设计
1. 测试分层结构
plaintext
auto_business_api_test/
├── .github/             # GitHub Actions CI/CD配置  
├── config/              # 项目配置文件（环境变量/接口地址）  
├── data/                # 测试数据（账号列表/配置文件）  
├── instance/            # Flask运行时数据（如SQLite数据库文件）  
├── libs/                # 公共工具库（签名生成/数据处理）  
├── load_test/           # 性能压测模块  
│   ├── scenarios/       # 压测场景脚本（挂单/购买/登录等角色行为）  
│   └── locustfile.py    # Locust压测入口脚本（分布式/阶梯加压配置）  
├── logs/                # 测试日志输出目录  
├── mock_server/         # 模拟服务相关资源（如上传文件）  
├── report/              # 测试报告输出目录（Allure/HTML）  
├── scripts/             # 辅助脚本（环境初始化/数据清理）  
├── tests/               # 测试用例目录  
│   ├── e2e/             # E2E全链路测试（C2C交易场景）  
│   └── unit/            # 单元测试（撮合逻辑/签名算法）  
├── .gitignore           # Git忽略文件配置  
├── pytest.ini           # Pytest运行配置  
├── README.md            # 项目说明文档  
├── requirements.txt     # 依赖包清单  
├── run_loadtest.sh      # 性能压测启动脚本  
├── run_test.sh          # 功能测试启动脚本  
└── set_env.sh           # 环境变量配置脚本（敏感信息，不上传Git）  
2. 签名机制测试覆盖
针对接口安全签名，实现合法请求 + 异常场景 + 攻击模拟的全维度测试：
签名算法	测试场景
ECDSA	
✅ 合法签名创建订单（CNY/USD 类型）
✅ 参数错误（金额非数字 / ProductID 无效）
✅ 安全攻击（时序 / 重放 / 数据篡改）
HMAC	
✅ 合法签名请求
✅ API Key 错误 / 时间戳过期
✅ 重放攻击验证
MD5	
✅ 基础签名验证
✅ 秘钥错误 / 空 Key 场景
✅ 参数合法性校验
3. E2E 场景测试
覆盖 C2C 交易核心链路，包含正常闭环与异常场景：
审核通过闭环：卖家注册→充值→挂单→买家下单→管理员审核→撮合完成→余额校验
审核失败场景：全流程 + 管理员拒绝审核→数据回滚（卖家余额恢复 / 挂单状态重置）
⚡ 性能测试方案（Locust）
1. 压测设计理念
针对撮合系统高并发场景，实现分布式、角色化、阶梯式性能压测，模拟真实业务流量：
角色区分：卖家（高频挂单）、买家（中频购买）、查询角色（余额 / 挂单查询）
场景覆盖：完整 E2E 链路（登录→挂单→购买→查询）+ 复杂撮合逻辑验证
分布式架构：Master-Worker 模式，支持大规模压测节点扩展
2. 核心特性
特性	说明
🔀 账号分片	按 Worker ID 切片全局账号池，避免账号冲突，支持海量用户模拟
🪜 阶梯加压	分阶段递增用户数（1/3→2/3→全量），模拟流量峰值场景
🔒 并发安全	协程锁保护公共挂单池，防止重复购买 / 数据竞争
🧠 内存控制	限制公共挂单池最大长度（10000），避免 OOM
📝 日志优化	频率控制失败日志输出（每 10 条记录 1 次），防止刷屏
🚫 容错机制	登录仅尝试 1 次，失败自动降级，不影响整体压测
3. 压测启动方式
bash
运行
# 本地启动压测（多节点）
sh run_loadtest.sh

🔐 签名机制与安全测试
1. 签名用例结构
YAML 用例支持签名配置、参数化与预期结果断言：
yaml
test_cases:
  success_cases:
    - name: "创建订单01_ECDSA签名成功：CNY订单"
      query_params: {version: "v1", page: 1}
      signature:
        secret: "{{en.ecdsa_SECRET}}"
        signature_mode: "valid_secret"
      input:
        product_id: "AB3"
        amount: 100
        order_type: "DEPOSIT"
      expected:
        status_code: 201
        amount: 100

  fail_cases:
    - name: "创建订单08_ECDSA签名失败：重放攻击"
      signature:
        secret: "{{en.ecdsa_SECRET}}"
        signature_mode: "replay_attack"
      input: {...}
      expected:
        status_code: 401
        error: "Invalid ECDSA signature"
2. 安全攻击模拟
支持针对签名机制的典型攻击场景测试：
时序攻击：过期时间戳请求验证
重放攻击：复用历史请求参数验证
数据篡改：签名后修改请求参数验证
秘钥错误：非法秘钥 / 空秘钥场景验证
🔄 CI/CD 集成（GitHub Actions）
每次git push或 PR 提交时自动触发流程：
安装 Python 依赖
启动 Flask 撮合模拟服务
执行分层测试（接口测试→E2E 测试→安全测试）
生成 Allure 测试报告并上传 Artifacts
🛠️ 快速开始
1. 环境安装
bash
运行
git clone https://github.com/tomfu90/auto_flow.git
cd auto_business_api_test
python -m venv .venv
source .venv/bin/activate  # Windows系统执行：.venv\Scripts\activate
pip install -r requirements.txt
2. 启动撮合服务
bash
运行
python app.py  # 默认端口5000
3. 运行测试
bash
运行
# 运行功能测试
sh run_test.sh

# 生成Allure报告
allure serve report/allure-results

# 启动性能压测
sh run_loadtest.sh