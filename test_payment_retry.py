import requests
import time
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8000"

def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")

def check_service():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=3)
        return r.status_code == 200
    except:
        return False

def get_user_ids():
    r = requests.get(f"{BASE_URL}/api/reimbursements/users")
    users = r.json()
    manager_id = None
    employee_id = None
    finance_id = None
    for u in users:
        if u["role"] == "manager":
            manager_id = u["id"]
        elif u["role"] == "employee":
            employee_id = u["id"]
        elif u["role"] == "finance":
            finance_id = u["id"]
    return manager_id, employee_id, finance_id

def test_payment_failure_and_retry():
    print_section("打款失败重试 + 重启恢复测试")

    if not check_service():
        print("[FAIL] 服务未运行，请先启动服务")
        sys.exit(1)

    manager_id, employee_id, finance_id = get_user_ids()
    if not all([manager_id, employee_id, finance_id]):
        print("[FAIL] 请先创建测试用户（运行 test_core.py）")
        sys.exit(1)

    print(f"使用用户 - 经理:{manager_id}, 员工:{employee_id}, 财务:{finance_id}")

    # 第1步：开启100%模拟失败
    print_section("第1步：开启100%模拟打款失败")
    r = requests.post(f"{BASE_URL}/api/payment/simulate-failure",
                      json={"enabled": True, "failure_rate": 1.0})
    print(f"设置模拟失败: {r.status_code}")
    print(f"当前配置: {r.json()}")
    assert r.status_code == 200

    # 第2步：创建并审批报销单
    print_section("第2步：创建并审批报销单")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 300.0, "description": "失败重试测试"})
    reim_id = r.json()["id"]
    print(f"创建报销单 ID={reim_id}, 状态={r.json()['status']}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id={employee_id}")
    print(f"提交报销单: 状态={r.json()['status']}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/approve?manager_id={manager_id}")
    print(f"经理审批: 状态={r.json()['status']}")

    # 第3步：查看打款任务
    print_section("第3步：查看待处理打款任务")
    r = requests.get(f"{BASE_URL}/api/payment/pending")
    tasks = r.json()
    task_id = None
    for t in tasks:
        if t["reimbursement_id"] == reim_id:
            task_id = t["id"]
            print(f"找到任务 ID={t['id']}, 状态={t['status']}, 重试={t['retry_count']}")
            break
    assert task_id is not None, "未找到打款任务"

    # 第4步：等待后台处理（会失败）
    print_section("第4步：等待后台打款（约10秒，会失败）")
    for i in range(10):
        time.sleep(1)
        print(f"  等待中... {i+1}/10")

    # 第5步：查看失败状态
    print_section("第5步：查看失败状态")
    r = requests.get(f"{BASE_URL}/api/payment/{task_id}")
    task = r.json()
    print(f"任务状态: {task['status']}")
    print(f"重试次数: {task['retry_count']}")
    print(f"错误信息: {task['error_message']}")
    print(f"最后尝试: {task['last_attempt_at']}")
    assert task["status"] == "failed", f"期望 failed，实际 {task['status']}"
    assert task["retry_count"] >= 1, "重试次数应该大于0"

    # 第5.5步：查看审计日志
    print_section("第5.5步：查看审计日志（应有 payment_failed 记录）")
    r = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id}")
    logs = r.json()
    print(f"日志条数: {len(logs)}")
    has_failed_log = False
    for log in logs:
        print(f"  [{log['created_at']}] 操作人={log['operator_id']}, 动作={log['action']}, "
              f"{log['before_status']} -> {log['after_status']}")
        if log["action"] == "payment_failed":
            has_failed_log = True
    assert has_failed_log, "应该有 payment_failed 日志记录"

    # 第6步：检查报销单状态仍是 manager_approved（没有变成非法状态）
    print_section("第6步：验证报销单状态（应仍为 manager_approved）")
    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id}")
    status = r.json()["status"]
    print(f"报销单状态: {status}")
    assert status == "manager_approved", f"期望 manager_approved，实际 {status}"
    print("[OK] 状态正确，没有留下非法状态")

    # 第7步：关闭模拟失败，手动重试任务
    print_section("第7步：关闭模拟失败，手动重试任务")
    r = requests.post(f"{BASE_URL}/api/payment/simulate-failure",
                      json={"enabled": False, "failure_rate": 0.0})
    print(f"关闭模拟失败: {r.json()}")

    r = requests.post(f"{BASE_URL}/api/payment/{task_id}/retry")
    print(f"重试任务: 状态={r.json()['status']}, 重试次数={r.json()['retry_count']}")

    # 第8步：等待处理成功
    print_section("第8步：等待后台打款成功（约10秒）")
    for i in range(10):
        time.sleep(1)
        print(f"  等待中... {i+1}/10")

    # 第9步：验证成功
    print_section("第9步：验证打款成功")
    r = requests.get(f"{BASE_URL}/api/payment/{task_id}")
    task = r.json()
    print(f"任务状态: {task['status']}")
    print(f"已处理: {task['is_processed']}")
    assert task["status"] == "completed", f"期望 completed，实际 {task['status']}"
    assert task["is_processed"] == True, "应该已处理"

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id}")
    status = r.json()["status"]
    print(f"报销单状态: {status}")
    assert status == "paid", f"期望 paid，实际 {status}"

    # 第10步：验证幂等性 - 尝试重复打款
    print_section("第10步：验证幂等性 - 尝试重复打款（应失败）")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/pay?finance_id={finance_id}")
    print(f"重复打款结果: 状态码={r.status_code}, 错误={r.json().get('detail')}")
    assert r.status_code == 400, "重复打款应该失败"

    # 第11步：查看完整审计日志
    print_section("第11步：查看完整审计日志")
    r = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id}")
    logs = r.json()
    print(f"日志条数: {len(logs)}")
    for log in logs:
        print(f"  [{log['created_at']}] 操作人={log['operator_id']}, 动作={log['action']}, "
              f"{log['before_status']} -> {log['after_status']}")

    # 验证日志包含所有必要动作
    actions = [log["action"] for log in logs]
    expected_actions = ["create", "submit", "approve", "payment_failed", "payment_retry", "pay"]
    for action in expected_actions:
        assert action in actions, f"缺少日志: {action}"
    print("\n[OK] 所有审计日志都存在")

    print_section("测试总结")
    print("[OK] 打款失败测试通过")
    print("[OK] 重试功能测试通过")
    print("[OK] 幂等性验证通过")
    print("[OK] 审计日志完整")
    print("[OK] 没有留下非法状态")
    print("\n" + "=" * 60)
    print("[OK] 所有测试通过！")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_payment_failure_and_retry()
    except AssertionError as e:
        print(f"\n[FAIL] 测试断言失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
