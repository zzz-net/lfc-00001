import requests
import sqlite3
import time
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8000"
DB_PATH = "./reimbursement.db"


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


def query_db(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def main():
    if not check_service():
        print("[FAIL] 服务未运行，请先启动: python start.py")
        sys.exit(1)

    print_section("Step 0: 验证系统用户存在")
    users = query_db("SELECT * FROM users WHERE id = 0")
    if users:
        print(f"[OK] 系统用户存在: id={users[0]['id']}, name={users[0]['name']}, role={users[0]['role']}")
        assert users[0]["name"] == "系统"
        assert users[0]["role"] == "system"
    else:
        print("[FAIL] 系统用户不存在")
        sys.exit(1)

    print_section("Step 1: 创建多个财务用户（新旧各一个）")
    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "旧财务", "role": "finance", "manager_id": None})
    old_finance_id = r.json()["id"]
    print(f"创建旧财务: id={old_finance_id}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "新财务", "role": "finance", "manager_id": None})
    new_finance_id = r.json()["id"]
    print(f"创建新财务: id={new_finance_id}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "张经理", "role": "manager", "manager_id": None})
    manager_id = r.json()["id"]
    print(f"创建经理: id={manager_id}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "李员工", "role": "employee", "manager_id": manager_id})
    employee_id = r.json()["id"]
    print(f"创建员工: id={employee_id}")

    all_users = query_db("SELECT id, name, role FROM users ORDER BY id")
    print(f"\n数据库中所有用户 ({len(all_users)}):")
    for u in all_users:
        print(f"  id={u['id']}, name={u['name']}, role={u['role']}")

    print_section("Step 2: 员工创建并提交报销单")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 500, "description": "自动打款测试"})
    reim_id = r.json()["id"]
    print(f"创建报销单: id={reim_id}, status={r.json()['status']}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id={employee_id}")
    print(f"提交报销单: status={r.json()['status']}")

    print_section("Step 3: 经理审批（触发自动打款任务）")
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/approve?manager_id={manager_id}")
    print(f"审批通过: status={r.json()['status']}")

    print("\n等待后台自动打款（约6秒）...")
    time.sleep(6)

    print_section("Step 4: 通过 API 验证结果")
    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id}")
    reim_data = r.json()
    print(f"报销单状态: {reim_data['status']}")
    assert reim_data["status"] == "paid", f"期望 paid，实际 {reim_data['status']}"
    print("[OK] 报销单状态为 paid")

    r = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id}")
    logs_api = r.json()
    print(f"\nAPI 返回审计日志 ({len(logs_api)} 条):")
    for log in logs_api:
        print(f"  action={log['action']}, operator_id={log['operator_id']}, "
              f"{log['before_status']} -> {log['after_status']}")

    print_section("Step 5: 直接查询 SQLite 验证审计日志")
    logs_db = query_db(
        "SELECT * FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id,)
    )
    print(f"数据库审计日志 ({len(logs_db)} 条):")
    for log in logs_db:
        print(f"  id={log['id']}, action={log['action']}, operator_id={log['operator_id']}, "
              f"{log['before_status']} -> {log['after_status']}")

    print_section("Step 6: 验证自动打款的 operator_id 是系统用户(0)，不是任何财务用户")
    auto_pay_log = next(
        (l for l in logs_db if l["action"].upper() == "AUTO_PAY"), None
    )

    if auto_pay_log:
        print(f"找到自动打款日志: action={auto_pay_log['action']}, operator_id={auto_pay_log['operator_id']}")
        assert auto_pay_log["operator_id"] == 0, f"期望 operator_id=0，实际 {auto_pay_log['operator_id']}"
        assert auto_pay_log["operator_id"] != old_finance_id, "operator_id 不应该是旧财务"
        assert auto_pay_log["operator_id"] != new_finance_id, "operator_id 不应该是新财务"
        print("[OK] operator_id = 0 (系统用户)，不是任何财务用户")
        print(f"[OK] 动作类型为: {auto_pay_log['action']}")
    else:
        print("[FAIL] 未找到自动打款日志")
        all_actions = [l["action"] for l in logs_db]
        print(f"实际动作: {all_actions}")
        sys.exit(1)

    print_section("Step 7: 手动打款验证（使用真实财务用户）")
    requests.post(f"{BASE_URL}/api/payment/simulate-failure",
                  json={"enabled": True, "failure_rate": 1.0})
    print("已开启打款模拟失败模式 (failure_rate=1.0)")

    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 300, "description": "手动打款测试"})
    reim_id2 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id2}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id2}/approve?manager_id={manager_id}")

    print("等待自动打款尝试失败（约6秒）...")
    time.sleep(6)

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id2}")
    print(f"自动打款失败后状态: {r.json()['status']}")
    assert r.json()["status"] == "manager_approved", "自动打款失败后状态应保持 manager_approved"

    tasks = query_db("SELECT * FROM payment_tasks WHERE reimbursement_id = ? ORDER BY id DESC", (reim_id2,))
    if tasks:
        print(f"打款任务状态: {tasks[0]['status']}, 重试次数: {tasks[0]['retry_count']}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id2}/pay?finance_id={old_finance_id}")
    print(f"手动打款结果: status={r.json()['status']}")
    assert r.json()["status"] == "paid", f"手动打款后应为 paid，实际 {r.json()['status']}"

    logs_manual = query_db(
        "SELECT * FROM audit_logs WHERE reimbursement_id = ? AND action = 'PAY'",
        (reim_id2,)
    )
    if logs_manual:
        log = logs_manual[0]
        print(f"手动打款日志: action={log['action']}, operator_id={log['operator_id']}")
        assert log["operator_id"] == old_finance_id, f"手动打款应该使用财务用户 {old_finance_id}"
        print(f"[OK] 手动打款 operator_id = {old_finance_id} (旧财务用户)")
    else:
        print("[FAIL] 未找到手动打款日志")
        all_acts = query_db("SELECT action, operator_id FROM audit_logs WHERE reimbursement_id = ?", (reim_id2,))
        print(f"实际动作: {[(a['action'], a['operator_id']) for a in all_acts]}")
        sys.exit(1)

    logs_failed = query_db(
        "SELECT * FROM audit_logs WHERE reimbursement_id = ? AND action = 'PAYMENT_FAILED'",
        (reim_id2,)
    )
    if logs_failed:
        print(f"自动打款失败日志: action={logs_failed[0]['action']}, operator_id={logs_failed[0]['operator_id']}")
        assert logs_failed[0]["operator_id"] == 0, "自动打款失败日志 operator_id 应为系统用户(0)"
        print("[OK] PAYMENT_FAILED operator_id = 0 (系统用户)")

    requests.post(f"{BASE_URL}/api/payment/simulate-failure",
                  json={"enabled": False, "failure_rate": 0.0})
    print("已关闭打款模拟失败模式")

    print_section("Step 8: 验证驳回、修改、重提流程不受影响")
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 400, "description": "驳回重提测试"})
    reim_id3 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/submit?user_id={employee_id}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/reject?manager_id={manager_id}")
    print(f"驳回: status={r.json()['status']}")
    assert r.json()["status"] == "rejected"

    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id3}?user_id={employee_id}",
                     json={"amount": 350, "description": "驳回后修改"})
    print(f"驳回后修改: status={r.json()['status']}, amount={r.json()['amount']}")
    assert r.json()["status"] == "draft"
    assert r.json()["amount"] == 350

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/submit?user_id={employee_id}")
    print(f"重新提交: status={r.json()['status']}")
    assert r.json()["status"] == "submitted"

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/approve?manager_id={manager_id}")
    print(f"再次审批: status={r.json()['status']}")
    assert r.json()["status"] == "manager_approved"

    print("等待自动打款（约6秒）...")
    time.sleep(6)

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id3}")
    assert r.json()["status"] == "paid", f"期望 paid，实际 {r.json()['status']}"
    print("[OK] 驳回重提流程正常，最终状态为 paid")

    logs3 = query_db(
        "SELECT action, operator_id FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id3,)
    )
    print(f"\n驳回重提审计日志:")
    for log in logs3:
        print(f"  {log['action']} (operator={log['operator_id']})")

    auto_pay_log3 = next((l for l in logs3 if l["action"].upper() == "AUTO_PAY"), None)
    if auto_pay_log3:
        assert auto_pay_log3["operator_id"] == 0, "驳回重提后的自动打款也应该用系统用户"
        print("[OK] 驳回重提后的自动打款 operator_id = 0")

    print_section("Step 9: 验证 API 和数据库数据完全一致")
    logs_api = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id}").json()
    logs_db = query_db("SELECT * FROM audit_logs WHERE reimbursement_id = ? ORDER BY id", (reim_id,))

    assert len(logs_api) == len(logs_db), f"API返回{len(logs_api)}条，数据库{len(logs_db)}条"
    for api_log, db_log in zip(logs_api, logs_db):
        assert api_log["action"].upper() == db_log["action"].upper(), f"action不一致: {api_log['action']} vs {db_log['action']}"
        assert api_log["operator_id"] == db_log["operator_id"], f"operator_id不一致"
        api_before = api_log["before_status"].upper() if api_log["before_status"] else None
        db_before = db_log["before_status"].upper() if db_log["before_status"] else None
        assert api_before == db_before, f"before_status不一致: {api_log['before_status']} vs {db_log['before_status']}"
        api_after = api_log["after_status"].upper() if api_log["after_status"] else None
        db_after = db_log["after_status"].upper() if db_log["after_status"] else None
        assert api_after == db_after, f"after_status不一致: {api_log['after_status']} vs {db_log['after_status']}"
    print("[OK] API 返回与 SQLite 数据完全一致")

    print_section("测试总结")
    print("[OK] 系统用户 (id=0, name='系统', role='system') 存在")
    print(f"[OK] 自动打款 operator_id = 0（系统），不是旧财务({old_finance_id})或新财务({new_finance_id})")
    print(f"[OK] 手动打款 operator_id = {old_finance_id}（实际财务用户）")
    print("[OK] 驳回、修改、重提流程不受影响")
    print("[OK] API 返回与 SQLite 数据完全一致")
    print("[OK] 审计归因正确：自动打款明确标识为系统执行")
    print("\n" + "=" * 60)
    print("[OK] 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
