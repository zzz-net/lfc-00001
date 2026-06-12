# 报销审批系统

基于 FastAPI + SQLite 的轻量级报销审批后端系统。

## 功能特性

- ✅ 员工创建、修改、提交报销单
- ✅ 经理审批或驳回报销单
- ✅ 财务人员打款（支持手动打款和后台队列自动打款）
- ✅ 详情查询和审计日志
- ✅ 状态流转统一校验
- ✅ 打款任务队列（支持失败重试、重启恢复、幂等性保证）
- ✅ 模拟打款失败功能（用于测试）

## 状态流转

```
草稿(draft) → 已提交(submitted) → 经理通过(manager_approved) → 已打款(paid)
              ↓                                          ↑
             驳回(rejected) → 修改后可重新提交
```

**状态转换规则**（统一校验）：

| 当前状态 | 允许转换到 |
|---------|-----------|
| draft | submitted |
| submitted | manager_approved, rejected |
| manager_approved | paid |
| rejected | draft |
| paid | (无) |

## 技术栈

- Python 3.10+
- FastAPI 0.104+
- SQLAlchemy 2.0
- SQLite (轻量本地数据库)
- 后台线程队列（无需额外中间件）

## 快速开始

### 1. 安装依赖

```bash
cd d:\workSpace\AI__SPACE\lfc-00001
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python start.py
```

服务将在 `http://localhost:8000` 启动。

**启动日志**会显示：
- 数据库初始化完成
- 重置卡住的处理中任务（用于重启恢复）
- 打款队列处理器已启动

### 3. 访问 API 文档

启动后访问 `http://localhost:8000/docs` 查看交互式 API 文档（Swagger UI）。

---

## 一键验证（推荐）

启动服务后，在另一个终端运行自动化测试脚本：

```bash
# 运行完整测试（主流程 + 边界测试 + 失败重试）
python init_test_data.py all

# 或分步运行：
python init_test_data.py init      # 仅初始化完整流程
python init_test_data.py boundary  # 仅边界情况测试
python init_test_data.py retry     # 仅失败重试测试
```

---

## 手动验证步骤

### 第1步：创建测试用户

```bash
# 创建经理（ID=1）
curl -X POST "http://localhost:8000/api/reimbursements/users" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"张经理\",\"role\":\"manager\",\"manager_id\":null}"

# 创建员工（ID=2，直属经理为ID=1）
curl -X POST "http://localhost:8000/api/reimbursements/users" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"李员工\",\"role\":\"employee\",\"manager_id\":1}"

# 创建财务（ID=3）
curl -X POST "http://localhost:8000/api/reimbursements/users" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"王财务\",\"role\":\"finance\",\"manager_id\":null}"
```

### 第2步：员工创建报销单（草稿状态）

```bash
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":2,\"amount\":500,\"description\":\"差旅费-北京出差\"}"
```

**预期结果**：状态为 `draft`

### 第3步：员工提交报销单

```bash
curl -X POST "http://localhost:8000/api/reimbursements/1/submit?user_id=2"
```

**预期结果**：状态从 `draft` → `submitted`

### 第4步：经理审批通过

```bash
curl -X POST "http://localhost:8000/api/reimbursements/1/approve?manager_id=1"
```

**预期结果**：
- 状态从 `submitted` → `manager_approved`
- 自动创建打款任务（状态 `pending`）
- 后台队列处理器会自动处理打款（约5秒内）

### 第5步：查看打款任务

```bash
# 查看所有待处理任务
curl -X GET "http://localhost:8000/api/payment/pending"

# 或等待几秒后查看任务状态
curl -X GET "http://localhost:8000/api/payment/1"
```

**预期结果**：打款任务状态变为 `completed`

### 第6步：查看报销单最终状态

```bash
curl -X GET "http://localhost:8000/api/reimbursements/1"
```

**预期结果**：状态为 `paid`

### 第7步：查看审计日志

```bash
curl -X GET "http://localhost:8000/api/audit/reimbursement/1"
```

**预期结果**：可以看到完整的状态流转记录：
- create: null → draft
- submit: draft → submitted
- approve: submitted → manager_approved
- auto_pay: manager_approved → paid  （后台自动任务）

每条记录包含：操作人ID、动作、前后状态、时间戳。
- `pay` 动作：operator_id 为真实财务用户 ID，表示人工手动打款
- `auto_pay` 动作：operator_id 为自动任务执行人 ID，解析规则如下：

**自动打款执行人解析规则（按优先级）**：
1. 先查找 `role = 'system'` 的用户（系统自动任务账号），取 ID 最小的
2. 找不到则 fallback 到 `role = 'finance'` 的用户（财务账号），取 ID 最小的
3. 两者都找不到：打款任务标记 `FAILED`，错误信息写明"未找到可用执行人"，报销单保持 `manager_approved`，**不写任何 operator_id 非法的审计日志**

### 第8步：驳回后修改重提（可选）

如果经理驳回了报销单，员工可以修改后重新提交：

```bash
# 驳回后修改金额和描述（状态自动从 rejected 转回 draft）
curl -X PUT "http://localhost:8000/api/reimbursements/1?user_id=2" ^
  -H "Content-Type: application/json" ^
  -d "{\"amount\":600,\"description\":\"差旅费-北京出差（调整金额）\"}"

# 重新提交
curl -X POST "http://localhost:8000/api/reimbursements/1/submit?user_id=2"

# 经理再次审批
curl -X POST "http://localhost:8000/api/reimbursements/1/approve?manager_id=1"
```

**预期结果**：
- PUT 返回状态为 `draft`，金额已更新
- 重新提交后状态为 `submitted`
- 审批后状态为 `manager_approved`
- 审计日志包含 `update: rejected → draft` 记录

---

## 边界情况测试（必须全部失败）

### 1. 金额为0

```bash
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":2,\"amount\":0,\"description\":\"测试\"}"
```

**预期**：400 错误，"金额必须大于0"

### 2. 负数金额

```bash
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":2,\"amount\":-100,\"description\":\"测试\"}"
```

**预期**：400 错误，"金额必须大于0"

### 3. 超过金额上限（配置上限10000）

```bash
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":2,\"amount\":15000,\"description\":\"测试\"}"
```

**预期**：400 错误，"金额超过上限 10000.0"

### 4. 员工越权打款（非财务角色）

```bash
# 先创建并审批一张报销单
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":2,\"amount\":200,\"description\":\"测试越权\"}"
curl -X POST "http://localhost:8000/api/reimbursements/2/submit?user_id=2"
curl -X POST "http://localhost:8000/api/reimbursements/2/approve?manager_id=1"

# 尝试用员工ID打款（应失败）
curl -X POST "http://localhost:8000/api/reimbursements/2/pay?finance_id=2"
```

**预期**：403 错误，"用户不是财务人员"

### 5. 经理审批自己创建的报销单

```bash
# 经理自己创建报销单
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":1,\"amount\":100,\"description\":\"自己报销\"}"
curl -X POST "http://localhost:8000/api/reimbursements/3/submit?user_id=1"

# 尝试自己审批（应失败）
curl -X POST "http://localhost:8000/api/reimbursements/3/approve?manager_id=1"
```

**预期**：400 错误，"不能审批自己的报销单"

### 6. 重复审批

```bash
# 创建新报销单
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":2,\"amount\":150,\"description\":\"测试重复审批\"}"
curl -X POST "http://localhost:8000/api/reimbursements/4/submit?user_id=2"

# 第一次审批（成功）
curl -X POST "http://localhost:8000/api/reimbursements/4/approve?manager_id=1"

# 第二次审批（应失败）
curl -X POST "http://localhost:8000/api/reimbursements/4/approve?manager_id=1"
```

**预期**：400 错误，"无法从 manager_approved 状态转换到 manager_approved 状态"

### 7. 从驳回状态直接打款

```bash
# 创建新报销单
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":2,\"amount\":250,\"description\":\"测试驳回打款\"}"
curl -X POST "http://localhost:8000/api/reimbursements/5/submit?user_id=2"

# 经理驳回
curl -X POST "http://localhost:8000/api/reimbursements/5/reject?manager_id=1"

# 尝试直接打款（应失败）
curl -X POST "http://localhost:8000/api/reimbursements/5/pay?finance_id=3"
```

**预期**：400 错误，"无法从 rejected 状态转换到 paid 状态"

---

## 打款失败重试测试

### 测试场景：模拟打款失败，重启服务后恢复，重试成功

#### 第1步：开启100%模拟失败

```bash
curl -X POST "http://localhost:8000/api/payment/simulate-failure" ^
  -H "Content-Type: application/json" ^
  -d "{\"enabled\":true,\"failure_rate\":1.0}"
```

#### 第2步：创建并审批报销单

```bash
curl -X POST "http://localhost:8000/api/reimbursements" ^
  -H "Content-Type: application/json" ^
  -d "{\"employee_id\":2,\"amount\":300,\"description\":\"失败重试测试\"}"
curl -X POST "http://localhost:8000/api/reimbursements/6/submit?user_id=2"
curl -X POST "http://localhost:8000/api/reimbursements/6/approve?manager_id=1"
```

#### 第3步：等待后台队列尝试打款（约6秒）

```bash
# 查看任务状态（应为 failed，重试次数=1）
curl -X GET "http://localhost:8000/api/payment/2"

# 查看审计日志（应有 payment_failed 记录）
curl -X GET "http://localhost:8000/api/audit/reimbursement/6"
```

#### 第4步：重启服务（模拟服务崩溃）

**在运行服务的终端按 Ctrl+C，然后重新启动：**

```bash
python start.py
```

**观察启动日志**：
```
INFO: 正在重置卡住的处理中任务...
INFO: 已重置 0 个卡住的任务
INFO: 正在启动打款队列处理器...
INFO: 打款队列处理器已启动
```

#### 第5步：关闭模拟失败，手动重试任务

```bash
# 关闭模拟失败
curl -X POST "http://localhost:8000/api/payment/simulate-failure" ^
  -H "Content-Type: application/json" ^
  -d "{\"enabled\":false,\"failure_rate\":0.0}"

# 手动重试任务
curl -X POST "http://localhost:8000/api/payment/2/retry"
```

#### 第6步：等待后台处理（约6秒）

```bash
# 查看任务状态（应为 completed）
curl -X GET "http://localhost:8000/api/payment/2"

# 查看报销单状态（应为 paid）
curl -X GET "http://localhost:8000/api/reimbursements/6"
```

#### 第7步：验证幂等性 - 尝试重复打款

```bash
curl -X POST "http://localhost:8000/api/reimbursements/6/pay?finance_id=3"
```

**预期**：400 错误，"该报销单已打款，不能重复打款"

#### 第8步：查看完整审计日志

```bash
curl -X GET "http://localhost:8000/api/audit/reimbursement/6"
```

**预期**：日志包含完整的流转记录，包括失败和重试：
- create: null → draft
- submit: draft → submitted
- approve: submitted → manager_approved
- payment_failed: manager_approved → manager_approved  （operator_id=0，系统用户）
- payment_retry: manager_approved → manager_approved   （operator_id=0，系统用户）
- auto_pay: manager_approved → paid                    （operator_id=0，系统用户）

---

## 关键设计说明

### 1. 事务原子性保证

所有状态变更操作都使用 `with_for_update()` 行锁 + 数据库事务，确保：
- 并发操作不会产生竞态条件
- 状态变更和审计日志在同一事务中提交
- 任何异常都会回滚，不会留下非法状态

### 2. 状态统一校验

所有状态流转都通过 `_validate_status_transition()` 函数统一校验，基于 `config.py` 中的 `VALID_STATUS_TRANSITIONS` 配置，杜绝非法状态转换。

### 3. 打款队列可靠性

- **重启恢复**：启动时自动扫描 `processing` 状态的任务，重置为 `pending`
- **幂等性**：已打款的报销单（`is_processed=True`）不会重复处理
- **失败重试**：失败任务会记录错误信息，可手动重试
- **状态一致性**：打款任务状态和报销单状态始终保持一致

### 4. 审计日志完整性

每一次状态变更都记录：
- 操作人ID
- 动作类型（create/submit/approve/reject/pay等）
- 变更前状态
- 变更后状态
- 操作时间

---

## API 接口总览

### 报销单管理
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/reimbursements | 创建报销单 |
| GET | /api/reimbursements | 查询报销单列表（`user_id` 必填；employee 只看自己的） |
| GET | /api/reimbursements/{id} | 查询报销单详情 |
| PUT | /api/reimbursements/{id} | 修改报销单（草稿/已驳回状态；驳回修改后自动转回 draft） |
| POST | /api/reimbursements/{id}/submit | 提交报销单 |
| POST | /api/reimbursements/{id}/approve | 经理审批通过 |
| POST | /api/reimbursements/{id}/reject | 经理驳回 |
| POST | /api/reimbursements/{id}/pay | 财务手动打款 |

### 用户管理
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/reimbursements/users | 创建用户 |
| GET | /api/reimbursements/users | 查询所有用户 |
| GET | /api/reimbursements/users/{id} | 查询用户详情 |

### 审计日志
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/audit | 查询所有审计日志 |
| GET | /api/audit/reimbursement/{id} | 查询指定报销单的审计日志 |
| GET | /api/audit/operator/{id} | 查询指定操作人的审计日志 |

### 打款任务
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/payment | 查询所有打款任务 |
| GET | /api/payment/pending | 查询待处理任务 |
| GET | /api/payment/failed | 查询失败任务 |
| GET | /api/payment/{id} | 查询任务详情 |
| POST | /api/payment/{id}/process | 手动处理任务 |
| POST | /api/payment/{id}/retry | 重试失败任务 |
| POST | /api/payment/{id}/cancel | 取消任务 |
| POST | /api/payment/reset-stuck | 重置卡住的任务 |
| POST | /api/payment/simulate-failure | 设置模拟失败 |
| GET | /api/payment/worker/status | 查看队列状态 |

### 系统
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 根路径 |
| GET | /health | 健康检查 |
| GET | /docs | API 文档 |

---

## 配置说明

在 [app/config.py](file:///d:/workSpace/AI__SPACE/lfc-00001/app/config.py) 中可以调整：

```python
MAX_REIMBURSEMENT_AMOUNT = 10000.0      # 报销金额上限
PAYMENT_WORKER_INTERVAL = 5              # 后台队列轮询间隔（秒）
PAYMENT_MAX_RETRIES = 3                  # 最大重试次数
PAYMENT_SIMULATE_FAILURE = False         # 默认是否模拟失败
PAYMENT_FAILURE_RATE = 0.0               # 默认失败率
```

---

## 项目结构

```
lfc-00001/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口，生命周期管理
│   ├── database.py          # 数据库连接配置
│   ├── models.py            # SQLAlchemy 数据模型
│   ├── schemas.py           # Pydantic 请求/响应模型
│   ├── config.py            # 系统配置
│   ├── payment_worker.py    # 后台打款队列处理器（核心）
│   ├── services/            # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── reimbursement_service.py
│   │   ├── user_service.py
│   │   ├── audit_service.py
│   │   ├── payment_service.py
│   │   └── import_service.py    # 批量导入服务
│   └── routes/              # API 路由层
│       ├── __init__.py
│       ├── reimbursement.py
│       ├── audit.py
│       ├── payment.py
│       └── import_batch.py      # 批量导入路由
├── init_test_data.py        # 自动化测试脚本
├── test_batch_import.py     # 批量导入专项测试
├── requirements.txt
├── start.py
└── README.md
```

---

## 常见问题

**Q: 数据库文件在哪里？**
A: SQLite 数据库文件 `reimbursement.db` 会在项目根目录自动创建。

**Q: 如何清空数据库重新测试？**
A: 停止服务后删除 `reimbursement.db` 文件，重新启动服务即可。

**Q: 后台队列处理速度可以调整吗？**
A: 可以修改 `config.py` 中的 `PAYMENT_WORKER_INTERVAL`（默认5秒）。

**Q: 如何确保服务崩溃后数据一致？**
A: 服务启动时会自动扫描 `processing` 状态的任务并重置为 `pending`，后台队列会重新处理。已打款的任务标记为 `is_processed=True`，不会重复执行。
