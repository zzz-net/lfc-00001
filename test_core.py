import requests
import time
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8000"

def test_health():
    print("=== 1. 健康检查 ===")
    r = requests.get(f"{BASE_URL}/health")
    print(f"状态码: {r.status_code}, 响应: {r.json()}")
    assert r.status_code == 200, "健康检查失败"
    print("[OK] 健康检查通过\n")

def test_create_users():
    print("=== 2. 创建测试用户 ===")
    r = requests.post(f"{BASE_URL}/api/reimbursements/users", 
                      json={"name": "张经理", "role": "manager", "manager_id": None})
    print(f"创建经理: {r.status_code}")
    manager_id = r.json()["id"]
    assert r.status_code == 200

    r = requests.post(f"{BASE_URL}/api/reimbursements/users", 
                      json={"name": "李员工", "role": "employee", "manager_id": manager_id})
    print(f"创建员工: {r.status_code}")
    employee_id = r.json()["id"]
    assert r.status_code == 200

    r = requests.post(f"{BASE_URL}/api/reimbursements/users", 
                      json={"name": "王财务", "role": "finance", "manager_id": None})
    print(f"创建财务: {r.status_code}")
    finance_id = r.json()["id"]
    assert r.status_code == 200

    print("[OK] 用户创建通过\n")
    return manager_id, employee_id, finance_id

def test_reimbursement_flow(manager_id, employee_id, finance_id):
    print("=== 3. 报销主流程 ===")
    
    print("3.1 创建报销单")
    r = requests.post(f"{BASE_URL}/api/reimbursements", 
                      json={"employee_id": employee_id, "amount": 500.0, "description": "差旅费"})
    print(f"  状态码: {r.status_code}, 状态: {r.json()['status']}")
    reim_id = r.json()["id"]
    assert r.status_code == 200
    assert r.json()["status"] == "draft"

    print("3.2 提交报销单")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id={employee_id}")
    print(f"  状态码: {r.status_code}, 状态: {r.json()['status']}")
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"

    print("3.3 经理审批")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/approve?manager_id={manager_id}")
    print(f"  状态码: {r.status_code}, 状态: {r.json()['status']}")
    assert r.status_code == 200
    assert r.json()["status"] == "manager_approved"

    print("3.4 等待后台打款（约6秒）...")
    time.sleep(6)

    print("3.5 查询最终状态")
    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id}")
    print(f"  状态码: {r.status_code}, 状态: {r.json()['status']}")
    assert r.status_code == 200
    assert r.json()["status"] == "paid", f"期望 paid，实际 {r.json()['status']}"

    print("3.6 查询审计日志")
    r = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id}")
    logs = r.json()
    print(f"  日志条数: {len(logs)}")
    for log in logs:
        print(f"    [{log['created_at']}] 操作人={log['operator_id']}, 动作={log['action']}, "
              f"{log['before_status']} -> {log['after_status']}")
    assert len(logs) >= 4

    print("[OK] 主流程通过\n")
    return reim_id

def test_boundary_cases(manager_id, employee_id, finance_id):
    print("=== 4. 边界情况测试 ===")
    
    print("4.1 金额为0（应失败）")
    r = requests.post(f"{BASE_URL}/api/reimbursements", 
                      json={"employee_id": employee_id, "amount": 0, "description": "测试"})
    print(f"  状态码: {r.status_code}")
    assert r.status_code in [400, 422], f"期望400或422，实际{r.status_code}"

    print("4.2 负数金额（应失败）")
    r = requests.post(f"{BASE_URL}/api/reimbursements", 
                      json={"employee_id": employee_id, "amount": -100, "description": "测试"})
    print(f"  状态码: {r.status_code}")
    assert r.status_code in [400, 422], f"期望400或422，实际{r.status_code}"

    print("4.3 超过金额上限（应失败）")
    r = requests.post(f"{BASE_URL}/api/reimbursements", 
                      json={"employee_id": employee_id, "amount": 15000, "description": "测试"})
    print(f"  状态码: {r.status_code}, 错误: {r.json().get('detail')}")
    assert r.status_code == 400

    print("4.4 员工越权打款（应失败）")
    r2 = requests.post(f"{BASE_URL}/api/reimbursements", 
                       json={"employee_id": employee_id, "amount": 200, "description": "测试越权"})
    r2_id = r2.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{r2_id}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{r2_id}/approve?manager_id={manager_id}")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{r2_id}/pay?finance_id={employee_id}")
    print(f"  状态码: {r.status_code}, 错误: {r.json().get('detail')}")
    assert r.status_code == 403

    print("4.5 经理审批自己的（应失败）")
    r3 = requests.post(f"{BASE_URL}/api/reimbursements", 
                       json={"employee_id": manager_id, "amount": 100, "description": "自己报销"})
    r3_id = r3.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{r3_id}/submit?user_id={manager_id}")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{r3_id}/approve?manager_id={manager_id}")
    print(f"  状态码: {r.status_code}, 错误: {r.json().get('detail')}")
    assert r.status_code in [400, 403], f"期望400或403，实际{r.status_code}"

    print("4.6 重复审批（应失败）")
    r4 = requests.post(f"{BASE_URL}/api/reimbursements", 
                       json={"employee_id": employee_id, "amount": 150, "description": "测试重复审批"})
    r4_id = r4.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{r4_id}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{r4_id}/approve?manager_id={manager_id}")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{r4_id}/approve?manager_id={manager_id}")
    print(f"  状态码: {r.status_code}, 错误: {r.json().get('detail')}")
    assert r.status_code == 400

    print("4.7 从驳回直接打款（应失败）")
    r5 = requests.post(f"{BASE_URL}/api/reimbursements", 
                       json={"employee_id": employee_id, "amount": 250, "description": "测试驳回打款"})
    r5_id = r5.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{r5_id}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{r5_id}/reject?manager_id={manager_id}")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{r5_id}/pay?finance_id={finance_id}")
    print(f"  状态码: {r.status_code}, 错误: {r.json().get('detail')}")
    assert r.status_code == 400

    print("4.8 重复打款（应失败）")
    r = requests.post(f"{BASE_URL}/api/reimbursements/1/pay?finance_id={finance_id}")
    print(f"  状态码: {r.status_code}, 错误: {r.json().get('detail')}")
    assert r.status_code == 400

    print("[OK] 边界情况测试通过\n")

def test_idempotency(reim_id, finance_id):
    print("=== 5. 幂等性验证 ===")
    print("5.1 对已打款的报销单再次打款（应失败）")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/pay?finance_id={finance_id}")
    print(f"  状态码: {r.status_code}, 错误: {r.json().get('detail')}")
    assert r.status_code == 400

    print("5.2 查询打款任务状态")
    r = requests.get(f"{BASE_URL}/api/payment/reimbursement/{reim_id}")
    tasks = r.json()
    for task in tasks:
        print(f"  任务ID={task['id']}, 状态={task['status']}, 已处理={task['is_processed']}")
        assert task["is_processed"] == True
        assert task["status"] == "completed"

    print("[OK] 幂等性验证通过\n")

def main():
    try:
        requests.get(f"{BASE_URL}/health")
    except requests.exceptions.ConnectionError:
        print("[FAIL] 无法连接到服务，请先运行: python start.py")
        sys.exit(1)

    print("=" * 60)
    print("报销审批系统 - 核心功能测试")
    print("=" * 60 + "\n")

    try:
        test_health()
        manager_id, employee_id, finance_id = test_create_users()
        reim_id = test_reimbursement_flow(manager_id, employee_id, finance_id)
        test_boundary_cases(manager_id, employee_id, finance_id)
        test_idempotency(reim_id, finance_id)

        print("=" * 60)
        print("[OK] 所有测试通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
