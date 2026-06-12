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


def execute_db(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    conn.close()


def setup_users():
    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "测试经理", "role": "manager", "manager_id": None})
    manager_id = r.json()["id"]
    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "测试员工", "role": "employee", "manager_id": manager_id})
    employee_id = r.json()["id"]
    return manager_id, employee_id


def create_and_approve(employee_id, manager_id, amount, desc):
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": amount, "description": desc})
    reim_id = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/approve?manager_id={manager_id}")
    return reim_id


def main():
    if not check_service():
        print("[FAIL] 服务未运行，请先启动: python start.py")
        sys.exit(1)

    manager_id, employee_id = setup_users()
    print(f"测试用户: 经理={manager_id}, 员工={employee_id}")

    # ===== Part 1: 有 system 用户时正常打款 =====
    print_section("Part 1: 有 system 角色用户时，正常自动打款")

    sys_users = query_db("SELECT id, name, role FROM users WHERE role = 'system'")
    print(f"system 角色用户: {sys_users}")
    assert len(sys_users) >= 1, "测试前提：应存在 system 用户"
    system_user_id = sys_users[0]["id"]

    reim_id1 = create_and_approve(employee_id, manager_id, 500, "Part1-有system用户")
    print("等待自动打款（约6秒）...")
    time.sleep(6)

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id1}")
    assert r.json()["status"] == "paid", f"期望 paid，实际 {r.json()['status']}"
    print(f"[实测] 报销单状态: {r.json()['status']}")

    logs = query_db(
        "SELECT * FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id1,)
    )
    auto_pay_log = next((l for l in logs if l["action"].upper() == "AUTO_PAY"), None)
    assert auto_pay_log is not None
    assert auto_pay_log["operator_id"] == system_user_id, \
        f"operator_id 应为 system 用户 {system_user_id}，实际 {auto_pay_log['operator_id']}"
    print(f"[实测] AUTO_PAY operator_id = {auto_pay_log['operator_id']} (system 用户 id={system_user_id})")
    print(f"[实测] 状态: {auto_pay_log['before_status']} -> {auto_pay_log['after_status']}")
    print("[OK] Part 1 通过")

    # ===== Part 2: 删除 system 用户，fallback 到 finance 用户 =====
    print_section("Part 2: 无 system 用户但有 finance 用户时，fallback 到 finance")

    sys_users_backup = query_db("SELECT * FROM users WHERE role = 'system'")
    execute_db("DELETE FROM users WHERE role = 'system'")
    remaining = query_db("SELECT * FROM users WHERE role = 'system'")
    assert len(remaining) == 0
    print("[实测] 已删除所有 system 角色用户")

    fin_users = query_db("SELECT id, name, role FROM users WHERE role = 'finance' ORDER BY id ASC")
    print(f"finance 角色用户: {[(u['id'], u['name']) for u in fin_users]}")
    assert len(fin_users) >= 1, "测试前提：应至少有一个 finance 用户"
    finance_user_id = fin_users[0]["id"]

    reim_id2 = create_and_approve(employee_id, manager_id, 600, "Part2-无system有finance")
    print("等待自动打款（约6秒）...")
    time.sleep(6)

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id2}")
    assert r.json()["status"] == "paid", f"期望 paid，实际 {r.json()['status']}"
    print(f"[实测] 报销单状态: {r.json()['status']}")

    logs2 = query_db(
        "SELECT * FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id2,)
    )
    auto_pay_log2 = next((l for l in logs2 if l["action"].upper() == "AUTO_PAY"), None)
    assert auto_pay_log2 is not None
    assert auto_pay_log2["operator_id"] == finance_user_id, \
        f"fallback operator_id 应为 finance 用户 {finance_user_id}，实际 {auto_pay_log2['operator_id']}"
    print(f"[实测] AUTO_PAY operator_id = {auto_pay_log2['operator_id']} (finance 用户 id={finance_user_id})")
    print("[OK] Part 2 通过")

    # ===== Part 3: 既无 system 也无 finance 用户时，明确失败 =====
    print_section("Part 3: 无可用执行人（无 system 无 finance）时，打款明确失败")

    fin_users_backup = query_db("SELECT * FROM users WHERE role = 'finance'")
    execute_db("DELETE FROM users WHERE role = 'finance'")
    remaining = query_db("SELECT * FROM users WHERE role IN ('system', 'finance')")
    assert len(remaining) == 0
    print("[实测] 已删除所有 system 和 finance 角色用户")

    reim_id3 = create_and_approve(employee_id, manager_id, 700, "Part3-无任何执行人")
    print("等待后台自动打款尝试（约8秒，应失败）...")
    time.sleep(8)

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id3}")
    status = r.json()["status"]
    assert status == "manager_approved", f"应保持 manager_approved，实际 {status}"
    print(f"[实测] 报销单状态保持: {status}")

    tasks = query_db(
        "SELECT * FROM payment_tasks WHERE reimbursement_id = ? ORDER BY id DESC",
        (reim_id3,)
    )
    assert len(tasks) >= 1
    task = tasks[0]
    print(f"[实测] 打款任务: status={task['status']}, retry_count={task['retry_count']}")
    print(f"[实测] 错误信息: {task['error_message']}")
    assert task["status"] == "FAILED"
    assert task["error_message"] is not None
    assert "system" in task["error_message"].lower() or "finance" in task["error_message"].lower() or "执行人" in task["error_message"]

    logs3 = query_db(
        "SELECT action, operator_id FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id3,)
    )
    print(f"[实测] 审计日志: {[(l['action'], l['operator_id']) for l in logs3]}")
    bad_logs = [l for l in logs3 if l["action"].upper() in ("AUTO_PAY", "PAYMENT_FAILED", "PAYMENT_RETRY")]
    assert len(bad_logs) == 0, f"不应写入 operator_id 非法的日志，实际有 {len(bad_logs)} 条"
    print("[实测] 未写入 AUTO_PAY / PAYMENT_FAILED 日志（因为没有合法执行人）")
    print("[OK] Part 3 通过")

    # ===== Part 4: 恢复 system 和 finance 用户，旧流程不受影响 =====
    print_section("Part 4: 恢复用户后，驳回/修改/重提/审批 旧流程正常")

    for u in sys_users_backup:
        keys = ", ".join(u.keys())
        placeholders = ", ".join(["?"] * len(u))
        execute_db(f"INSERT INTO users ({keys}) VALUES ({placeholders})", tuple(u.values()))
    for u in fin_users_backup:
        keys = ", ".join(u.keys())
        placeholders = ", ".join(["?"] * len(u))
        execute_db(f"INSERT OR IGNORE INTO users ({keys}) VALUES ({placeholders})", tuple(u.values()))
    print("[实测] 已恢复 system 和 finance 用户")

    # 创建新报销单，提交后驳回（驳回只能在 submitted 状态）
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 300, "description": "Part4-测试前半段"})
    reim_id4 = r.json()["id"]
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id4}/submit?user_id={employee_id}")
    assert r.json()["status"] == "submitted"
    print(f"[实测] 提交: {r.json()['status']}")
    # 驳回
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id4}/reject?manager_id={manager_id}")
    assert r.json()["status"] == "rejected", f"驳回失败: {r.json()}"
    print(f"[实测] 驳回: {r.json()['status']}")
    # 修改（转回 draft）
    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id4}?user_id={employee_id}",
                     json={"amount": 250, "description": "Part4-驳回后修改"})
    assert r.json()["status"] == "draft"
    assert r.json()["amount"] == 250
    print(f"[实测] 驳回后修改: {r.json()['status']}, amount={r.json()['amount']}")
    # 重新提交
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id4}/submit?user_id={employee_id}")
    assert r.json()["status"] == "submitted"
    print(f"[实测] 重新提交: {r.json()['status']}")
    # 再次审批
    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id4}/approve?manager_id={manager_id}")
    assert r.json()["status"] == "manager_approved"
    print(f"[实测] 再次审批: {r.json()['status']}")

    print("等待自动打款（约6秒）...")
    time.sleep(6)

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id4}")
    assert r.json()["status"] == "paid", f"期望 paid，实际 {r.json()['status']}"
    print(f"[实测] 最终状态: {r.json()['status']}")

    logs4 = query_db(
        "SELECT action, operator_id FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id4,)
    )
    actions = [(l["action"], l["operator_id"]) for l in logs4]
    print(f"[实测] 动作序列: {actions}")

    # 验证 API 和 SQLite 一致
    api_logs = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id4}").json()
    assert len(api_logs) == len(logs4)
    for api_l, db_l in zip(api_logs, logs4):
        assert api_l["action"].upper() == db_l["action"].upper()
        assert api_l["operator_id"] == db_l["operator_id"]
    print("[实测] API 返回与 SQLite 数据一致")
    print("[OK] Part 4 通过")

    print_section("测试总结（仅实测结果）")
    print("[实测] Part1: 有 system 用户时，AUTO_PAY operator_id = system 用户ID")
    print("[实测] Part2: 无 system 但有 finance 时，AUTO_PAY operator_id = finance 用户ID（fallback）")
    print("[实测] Part3: 无任何执行人时，任务 FAILED，错误信息明确，报销单保持 manager_approved，不写非法日志")
    print("[实测] Part4: 驳回/修改/重提/审批 全流程正常，API 与 SQLite 一致")
    print("\n" + "=" * 60)
    print("[OK] 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
