import sys
import io
import requests
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8000"


def create_user(name, role, manager_id=None):
    url = f"{BASE_URL}/api/reimbursements/users"
    data = {"name": name, "role": role, "manager_id": manager_id}
    response = requests.post(url, json=data)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 创建用户成功: {result['name']} (ID: {result['id']}, 角色: {result['role']})")
        return result
    else:
        print(f"✗ 创建用户失败: {response.status_code} - {response.text}")
        return None


def create_reimbursement(employee_id, amount, description):
    url = f"{BASE_URL}/api/reimbursements"
    data = {"employee_id": employee_id, "amount": amount, "description": description}
    response = requests.post(url, json=data)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 创建报销单成功: ID={result['id']}, 金额={result['amount']}, 状态={result['status']}")
        return result
    else:
        print(f"✗ 创建报销单失败: {response.status_code} - {response.text}")
        return None


def submit_reimbursement(reimbursement_id, user_id):
    url = f"{BASE_URL}/api/reimbursements/{reimbursement_id}/submit?user_id={user_id}"
    response = requests.post(url)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 提交报销单成功: ID={result['id']}, 状态={result['status']}")
        return result
    else:
        print(f"✗ 提交报销单失败: {response.status_code} - {response.text}")
        return None


def approve_reimbursement(reimbursement_id, manager_id):
    url = f"{BASE_URL}/api/reimbursements/{reimbursement_id}/approve?manager_id={manager_id}"
    response = requests.post(url)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 审批报销单成功: ID={result['id']}, 状态={result['status']}")
        return result
    else:
        print(f"✗ 审批报销单失败: {response.status_code} - {response.text}")
        return None


def reject_reimbursement(reimbursement_id, manager_id):
    url = f"{BASE_URL}/api/reimbursements/{reimbursement_id}/reject?manager_id={manager_id}"
    response = requests.post(url)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 驳回报销单成功: ID={result['id']}, 状态={result['status']}")
        return result
    else:
        print(f"✗ 驳回报销单失败: {response.status_code} - {response.text}")
        return None


def pay_reimbursement(reimbursement_id, finance_id):
    url = f"{BASE_URL}/api/reimbursements/{reimbursement_id}/pay?finance_id={finance_id}"
    response = requests.post(url)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 打款成功: ID={result['id']}, 状态={result['status']}")
        return result
    else:
        print(f"✗ 打款失败: {response.status_code} - {response.text}")
        return None


def get_reimbursement(reimbursement_id):
    url = f"{BASE_URL}/api/reimbursements/{reimbursement_id}"
    response = requests.get(url)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 查询报销单: ID={result['id']}, 金额={result['amount']}, 状态={result['status']}")
        return result
    else:
        print(f"✗ 查询报销单失败: {response.status_code} - {response.text}")
        return None


def get_audit_logs(reimbursement_id):
    url = f"{BASE_URL}/api/audit/reimbursement/{reimbursement_id}"
    response = requests.get(url)
    if response.status_code == 200:
        logs = response.json()
        print(f"\n=== 报销单 {reimbursement_id} 审计日志 ===")
        for log in logs:
            print(f"  [{log['created_at']}] 操作人={log['operator_id']}, 动作={log['action']}, "
                  f"{log['before_status']} → {log['after_status']}")
        return logs
    else:
        print(f"✗ 查询审计日志失败: {response.status_code} - {response.text}")
        return None


def get_payment_tasks():
    url = f"{BASE_URL}/api/payment/pending"
    response = requests.get(url)
    if response.status_code == 200:
        tasks = response.json()
        print(f"\n=== 待处理打款任务 ===")
        for task in tasks:
            print(f"  任务ID={task['id']}, 报销单ID={task['reimbursement_id']}, "
                  f"状态={task['status']}, 重试次数={task['retry_count']}")
        return tasks
    else:
        print(f"✗ 查询打款任务失败: {response.status_code} - {response.text}")
        return None


def set_simulate_failure(enabled, failure_rate=1.0):
    url = f"{BASE_URL}/api/payment/simulate-failure"
    data = {"enabled": enabled, "failure_rate": failure_rate}
    response = requests.post(url, json=data)
    if response.status_code == 200:
        result = response.json()
        print(f"✓ 设置模拟失败: 启用={result['simulate_failure']}, 失败率={result['failure_rate']}")
        return result
    else:
        print(f"✗ 设置模拟失败失败: {response.status_code} - {response.text}")
        return None


def init_complete_flow():
    print("\n" + "=" * 60)
    print("初始化完整测试流程: 创建用户 → 报销 → 审批 → 打款")
    print("=" * 60 + "\n")

    print("--- 第1步: 创建用户 ---")
    manager = create_user("张经理", "manager")
    employee = create_user("李员工", "employee", manager_id=manager["id"])
    finance = create_user("王财务", "finance")

    if not all([manager, employee, finance]):
        print("\n用户创建失败，退出测试")
        return

    print("\n--- 第2步: 创建报销单 ---")
    reimbursement = create_reimbursement(employee["id"], 500.0, "差旅费-北京出差")
    if not reimbursement:
        return

    print("\n--- 第3步: 提交报销单 ---")
    submit_reimbursement(reimbursement["id"], employee["id"])

    print("\n--- 第4步: 经理审批 ---")
    approve_reimbursement(reimbursement["id"], manager["id"])

    print("\n--- 第5步: 财务打款 ---")
    pay_reimbursement(reimbursement["id"], finance["id"])

    print("\n--- 第6步: 查询报销单详情 ---")
    get_reimbursement(reimbursement["id"])

    print("\n--- 第7步: 查询审计日志 ---")
    get_audit_logs(reimbursement["id"])

    print("\n" + "=" * 60)
    print("✓ 完整流程测试完成！")
    print("=" * 60 + "\n")

    return {
        "manager": manager,
        "employee": employee,
        "finance": finance,
        "reimbursement": reimbursement
    }


def test_boundary_cases(users):
    print("\n" + "=" * 60)
    print("边界情况测试")
    print("=" * 60 + "\n")

    manager = users["manager"]
    employee = users["employee"]
    finance = users["finance"]

    print("--- 测试1: 金额为0 (应该失败) ---")
    create_reimbursement(employee["id"], 0, "测试金额为0")

    print("\n--- 测试2: 负数金额 (应该失败) ---")
    create_reimbursement(employee["id"], -100, "测试负数金额")

    print("\n--- 测试3: 超过金额上限10000 (应该失败) ---")
    create_reimbursement(employee["id"], 15000, "测试超上限")

    print("\n--- 测试4: 员工越权打款 (应该失败) ---")
    r2 = create_reimbursement(employee["id"], 200, "测试越权打款")
    if r2:
        submit_reimbursement(r2["id"], employee["id"])
        approve_reimbursement(r2["id"], manager["id"])
        pay_reimbursement(r2["id"], employee["id"])

    print("\n--- 测试5: 经理审批自己的报销单 (应该失败) ---")
    r3 = create_reimbursement(manager["id"], 100, "自己报销")
    if r3:
        submit_reimbursement(r3["id"], manager["id"])
        approve_reimbursement(r3["id"], manager["id"])

    print("\n--- 测试6: 重复审批 (应该失败) ---")
    r4 = create_reimbursement(employee["id"], 150, "测试重复审批")
    if r4:
        submit_reimbursement(r4["id"], employee["id"])
        approve_reimbursement(r4["id"], manager["id"])
        approve_reimbursement(r4["id"], manager["id"])

    print("\n--- 测试7: 从驳回直接打款 (应该失败) ---")
    r5 = create_reimbursement(employee["id"], 250, "测试驳回后打款")
    if r5:
        submit_reimbursement(r5["id"], employee["id"])
        reject_reimbursement(r5["id"], manager["id"])
        pay_reimbursement(r5["id"], finance["id"])

    print("\n" + "=" * 60)
    print("✓ 边界情况测试完成！")
    print("=" * 60 + "\n")


def test_payment_failure_retry(users):
    print("\n" + "=" * 60)
    print("打款失败重试测试")
    print("=" * 60 + "\n")

    manager = users["manager"]
    employee = users["employee"]
    finance = users["finance"]

    print("--- 第1步: 开启100%模拟失败 ---")
    set_simulate_failure(True, 1.0)

    print("\n--- 第2步: 创建并审批报销单 ---")
    r = create_reimbursement(employee["id"], 300, "测试失败重试")
    if not r:
        return
    submit_reimbursement(r["id"], employee["id"])
    approve_reimbursement(r["id"], manager["id"])

    print("\n--- 第3步: 查看待处理任务 (状态应为 pending) ---")
    get_payment_tasks()

    print("\n--- 第4步: 等待约6秒让后台worker尝试打款 (会失败) ---")
    import time
    time.sleep(6)

    print("\n--- 第5步: 查看任务状态 (应为 failed，重试次数=1) ---")
    get_payment_tasks()

    print("\n--- 第6步: 查看审计日志 (应有 payment_failed 记录) ---")
    get_audit_logs(r["id"])

    print("\n--- 第7步: 关闭模拟失败 ---")
    set_simulate_failure(False)

    print("\n--- 第8步: 手动重试任务 ---")
    url = f"{BASE_URL}/api/payment/1/retry"
    response = requests.post(url)
    print(f"重试结果: {response.status_code} - {response.json() if response.status_code == 200 else response.text}")

    print("\n--- 第9步: 等待约6秒让后台worker处理 ---")
    time.sleep(6)

    print("\n--- 第10步: 查看任务状态 (应为 completed) ---")
    get_payment_tasks()

    print("\n--- 第11步: 查看报销单状态 (应为 paid) ---")
    get_reimbursement(r["id"])

    print("\n--- 第12步: 尝试重复打款 (应该失败) ---")
    pay_reimbursement(r["id"], finance["id"])

    print("\n--- 第13步: 查看完整审计日志 ---")
    get_audit_logs(r["id"])

    print("\n" + "=" * 60)
    print("✓ 打款失败重试测试完成！")
    print("=" * 60 + "\n")


def main():
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code != 200:
            print("✗ 服务未启动，请先运行: python start.py")
            sys.exit(1)
        print("✓ 服务运行正常\n")
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到服务，请先运行: python start.py")
        sys.exit(1)

    if len(sys.argv) > 1:
        if sys.argv[1] == "init":
            init_complete_flow()
        elif sys.argv[1] == "boundary":
            users = init_complete_flow()
            if users:
                test_boundary_cases(users)
        elif sys.argv[1] == "retry":
            users = init_complete_flow()
            if users:
                test_payment_failure_retry(users)
        elif sys.argv[1] == "all":
            users = init_complete_flow()
            if users:
                test_boundary_cases(users)
                test_payment_failure_retry(users)
        else:
            print("用法: python init_test_data.py [init|boundary|retry|all]")
    else:
        users = init_complete_flow()
        if users:
            test_boundary_cases(users)
            test_payment_failure_retry(users)


if __name__ == "__main__":
    main()
