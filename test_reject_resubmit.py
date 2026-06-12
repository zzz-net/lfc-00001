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

def setup_test_users():
    print("--- 设置测试用户 ---")
    r = requests.get(f"{BASE_URL}/api/reimbursements/users")
    users = r.json()
    if len(users) >= 3:
        manager = next((u for u in users if u["role"] == "manager"), None)
        employee = next((u for u in users if u["role"] == "employee"), None)
        finance = next((u for u in users if u["role"] == "finance"), None)
        if manager and employee and finance:
            print(f"复用已有用户 - 经理:{manager['id']}, 员工:{employee['id']}, 财务:{finance['id']}")
            return manager["id"], employee["id"], finance["id"]

    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "张经理", "role": "manager", "manager_id": None})
    manager_id = r.json()["id"]

    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "李员工", "role": "employee", "manager_id": manager_id})
    employee_id = r.json()["id"]

    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "王财务", "role": "finance", "manager_id": None})
    finance_id = r.json()["id"]

    print(f"创建用户 - 经理:{manager_id}, 员工:{employee_id}, 财务:{finance_id}")
    return manager_id, employee_id, finance_id


def test_reject_and_resubmit_flow(manager_id, employee_id, finance_id):
    print_section("主流程测试：驳回 -> 修改 -> 重新提交 -> 审批 -> 打款")

    print("[Step 1] 员工创建报销单")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 800, "description": "差旅费-上海"})
    reim_id = r.json()["id"]
    print(f"  创建成功: ID={reim_id}, 金额=800, 状态={r.json()['status']}")
    assert r.json()["status"] == "draft"

    print("\n[Step 2] 员工提交报销单")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id={employee_id}")
    print(f"  提交成功: 状态={r.json()['status']}")
    assert r.json()["status"] == "submitted"

    print("\n[Step 3] 经理驳回")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/reject?manager_id={manager_id}")
    print(f"  驳回成功: 状态={r.json()['status']}")
    assert r.json()["status"] == "rejected"

    print("\n[Step 4] 员工修改金额和描述（rejected -> draft）")
    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id}?user_id={employee_id}",
                      json={"amount": 600, "description": "差旅费-上海（调整后）"})
    print(f"  修改成功: 金额={r.json()['amount']}, 描述={r.json()['description']}, 状态={r.json()['status']}")
    assert r.json()["amount"] == 600
    assert r.json()["status"] == "draft"
    assert "调整后" in r.json()["description"]

    print("\n[Step 5] 员工重新提交")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id={employee_id}")
    print(f"  提交成功: 状态={r.json()['status']}")
    assert r.json()["status"] == "submitted"

    print("\n[Step 6] 经理审批通过")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/approve?manager_id={manager_id}")
    print(f"  审批通过: 状态={r.json()['status']}")
    assert r.json()["status"] == "manager_approved"

    print("\n[Step 7] 等待后台打款（约6秒）")
    time.sleep(6)

    print("\n[Step 8] 验证最终状态")
    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id}")
    print(f"  报销单状态: {r.json()['status']}")
    assert r.json()["status"] == "paid"

    print("\n[Step 9] 查看审计日志")
    r = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id}")
    logs = r.json()
    print(f"  日志条数: {len(logs)}")
    for log in logs:
        print(f"    [{log['created_at']}] 操作人={log['operator_id']}, 动作={log['action']}, "
              f"{log['before_status']} -> {log['after_status']}")

    actions = [log["action"] for log in logs]
    print(f"\n  动作序列: {actions}")

    assert "create" in actions, "缺少 create 日志"
    assert "submit" in actions, "缺少 submit 日志"
    assert "reject" in actions, "缺少 reject 日志"
    assert "update" in actions, "缺少 update 日志"
    assert "approve" in actions, "缺少 approve 日志"
    assert "pay" in actions, "缺少 pay 日志"

    update_log = next((l for l in logs if l["action"] == "update"), None)
    assert update_log["before_status"] == "rejected", "update 前状态应为 rejected"
    assert update_log["after_status"] == "draft", "update 后状态应为 draft"

    print("\n[OK] 驳回-修改-重提-审批-打款 完整链路通过！")
    return reim_id


def test_boundary_cases(manager_id, employee_id, finance_id):
    print_section("边界情况测试")

    print("--- [边界1] 重复驳回再重提（多轮驳回循环） ---")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 500, "description": "多轮驳回测试"})
    reim_id = r.json()["id"]

    for round_num in range(1, 4):
        print(f"  第{round_num}轮:")
        requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id={employee_id}")
        r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/reject?manager_id={manager_id}")
        assert r.json()["status"] == "rejected", f"第{round_num}轮驳回失败"

        r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id}?user_id={employee_id}",
                          json={"description": f"第{round_num}次修改"})
        assert r.json()["status"] == "draft", f"第{round_num}轮转草稿失败"
        print(f"    驳回 -> 修改 -> 草稿: OK")

    print("  [OK] 多轮驳回循环通过")

    print("\n--- [边界2] 未授权修改（别人不能修改我的驳回单） ---")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 300, "description": "越权测试"})
    reim_id2 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id2}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id2}/reject?manager_id={manager_id}")

    other_user_r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                                 json={"name": "其他员工", "role": "employee", "manager_id": manager_id})
    other_user_id = other_user_r.json()["id"]

    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id2}?user_id={other_user_id}",
                      json={"amount": 200})
    print(f"  越权修改结果: 状态码={r.status_code}, 错误={r.json().get('detail')}")
    assert r.status_code == 403, "越权修改应该返回403"
    print("  [OK] 未授权修改被拒绝")

    print("\n--- [边界3] 已打款单据不能修改回退 ---")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 200, "description": "已打款回退测试"})
    reim_id3 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/approve?manager_id={manager_id}")
    print("  等待打款完成...")
    time.sleep(6)

    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id3}?user_id={employee_id}",
                      json={"amount": 150})
    print(f"  修改已打款单据: 状态码={r.status_code}, 错误={r.json().get('detail')}")
    assert r.status_code == 400, "已打款单据不能修改"
    print("  [OK] 已打款单据不能修改")

    print("\n--- [边界4] 已提交状态不能直接修改（需要先驳回） ---")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 250, "description": "已提交修改测试"})
    reim_id4 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id4}/submit?user_id={employee_id}")

    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id4}?user_id={employee_id}",
                      json={"amount": 200})
    print(f"  修改已提交单据: 状态码={r.status_code}, 错误={r.json().get('detail')}")
    assert r.status_code == 400, "已提交单据不能直接修改"
    print("  [OK] 已提交单据不能直接修改")

    print("\n--- [边界5] 经理不能修改员工的报销单 ---")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 180, "description": "经理修改测试"})
    reim_id5 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id5}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id5}/reject?manager_id={manager_id}")

    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id5}?user_id={manager_id}",
                      json={"amount": 100})
    print(f"  经理修改员工驳回单: 状态码={r.status_code}, 错误={r.json().get('detail')}")
    assert r.status_code == 403, "经理不能修改员工的报销单"
    print("  [OK] 经理不能修改员工报销单")

    print("\n--- [边界6] 驳回后不修改内容直接修改（应该失败，至少修改一项） ---")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 220, "description": "空修改测试"})
    reim_id6 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id6}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id6}/reject?manager_id={manager_id}")

    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id6}?user_id={employee_id}",
                      json={})
    print(f"  空修改: 状态码={r.status_code}, 错误={r.json().get('detail')}")
    assert r.status_code == 400, "空修改应该失败"
    print("  [OK] 空修改被拒绝")

    print("\n" + "=" * 60)
    print("[OK] 所有边界测试通过！")
    print("=" * 60)


def main():
    if not check_service():
        print("[FAIL] 服务未运行，请先启动: python start.py")
        sys.exit(1)

    print_section("报销驳回重提功能测试")

    try:
        manager_id, employee_id, finance_id = setup_test_users()
        test_reject_and_resubmit_flow(manager_id, employee_id, finance_id)
        test_boundary_cases(manager_id, employee_id, finance_id)
    except AssertionError as e:
        print(f"\n[FAIL] 断言失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
