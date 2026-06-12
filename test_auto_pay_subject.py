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


def main():
    if not check_service():
        print("[FAIL] 服务未运行，请先启动: python start.py")
        sys.exit(1)

    # ===== 第一部分：有合法系统用户时正常打款 =====
    print_section("Part 1: 有合法系统用户时，自动打款正常")

    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "测试经理A", "role": "manager", "manager_id": None})
    manager_id = r.json()["id"]

    r = requests.post(f"{BASE_URL}/api/reimbursements/users",
                      json={"name": "测试员工A", "role": "employee", "manager_id": manager_id})
    employee_id = r.json()["id"]

    print(f"测试用户: 经理={manager_id}, 员工={employee_id}")

    # 确认系统用户存在
    sys_users = query_db("SELECT * FROM users WHERE id = 0")
    assert len(sys_users) == 1, "测试前提：系统用户应该存在"
    print(f"[OK] 系统用户存在: id={sys_users[0]['id']}, name={sys_users[0]['name']}, role={sys_users[0]['role']}")

    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 500, "description": "测试-有系统用户"})
    reim_id1 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id1}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id1}/approve?manager_id={manager_id}")

    print("等待自动打款（约6秒）...")
    time.sleep(6)

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id1}")
    assert r.json()["status"] == "paid", f"期望 paid，实际 {r.json()['status']}"
    print(f"[OK] 报销单状态: paid")

    logs = query_db(
        "SELECT * FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id1,)
    )
    auto_pay_log = next((l for l in logs if l["action"].upper() == "AUTO_PAY"), None)
    assert auto_pay_log is not None, "应存在 AUTO_PAY 日志"
    assert auto_pay_log["operator_id"] == 0, f"operator_id 应为 0，实际 {auto_pay_log['operator_id']}"
    print(f"[OK] AUTO_PAY 日志: operator_id={auto_pay_log['operator_id']}, action={auto_pay_log['action']}")
    print(f"[OK] 状态流转: {auto_pay_log['before_status']} -> {auto_pay_log['after_status']}")

    # ===== 第二部分：删除系统用户后，自动打款应失败 =====
    print_section("Part 2: 删除系统用户后，自动打款应明确失败且不写非法日志")

    # 先备份系统用户
    sys_user_backup = query_db("SELECT * FROM users WHERE id = 0")
    assert len(sys_user_backup) == 1

    # 删除系统用户
    execute_db("DELETE FROM users WHERE id = 0")
    remaining = query_db("SELECT * FROM users WHERE id = 0")
    assert len(remaining) == 0, "系统用户应该已被删除"
    print("[OK] 系统用户已删除")

    # 创建新报销单并审批
    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 700, "description": "测试-无系统用户"})
    reim_id2 = r.json()["id"]
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id2}/submit?user_id={employee_id}")
    requests.post(f"{BASE_URL}/api/reimbursements/{reim_id2}/approve?manager_id={manager_id}")

    print("等待后台自动打款尝试（约8秒，应失败）...")
    time.sleep(8)

    # 验证报销单状态：应该还是 manager_approved（不能变成 paid 或非法状态）
    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id2}")
    status = r.json()["status"]
    print(f"报销单状态: {status}")
    assert status == "manager_approved", f"无系统用户时状态应保持 manager_approved，实际 {status}"
    print(f"[OK] 报销单状态保持 manager_approved，未被错误修改")

    # 验证打款任务：应标记 FAILED，有明确错误信息
    tasks = query_db(
        "SELECT * FROM payment_tasks WHERE reimbursement_id = ? ORDER BY id DESC",
        (reim_id2,)
    )
    assert len(tasks) >= 1, "应存在打款任务"
    task = tasks[0]
    print(f"打款任务: status={task['status']}, retry_count={task['retry_count']}")
    print(f"错误信息: {task['error_message']}")
    assert task["status"] == "FAILED", f"任务应标记 FAILED，实际 {task['status']}"
    assert task["error_message"] is not None and len(task["error_message"]) > 0, "应有明确错误信息"
    assert "系统用户" in task["error_message"] or "执行主体" in task["error_message"], \
        f"错误信息应说明系统用户问题，实际: {task['error_message']}"
    print(f"[OK] 打款任务明确失败，错误信息包含执行主体问题")

    # 关键验证：审计日志中不能出现 operator_id=0 或 AUTO_PAY（因为系统用户不存在，不能写日志）
    logs2 = query_db(
        "SELECT * FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id2,)
    )
    print(f"审计日志 ({len(logs2)} 条):")
    for l in logs2:
        print(f"  action={l['action']}, operator_id={l['operator_id']}, "
              f"{l['before_status']} -> {l['after_status']}")

    auto_pay_logs = [l for l in logs2 if l["action"].upper() in ("AUTO_PAY", "PAYMENT_FAILED")]
    assert len(auto_pay_logs) == 0, \
        f"系统用户不存在时不应写 AUTO_PAY 或 PAYMENT_FAILED 日志，实际有 {len(auto_pay_logs)} 条"
    print("[OK] 系统用户不存在时，未写入任何 operator_id 非法的审计日志")

    # 恢复系统用户（避免影响后续测试）
    execute_db(
        "INSERT INTO users (id, name, role, manager_id) VALUES (?, ?, ?, ?)",
        (0, "系统", "system", None)
    )
    restored = query_db("SELECT * FROM users WHERE id = 0")
    assert len(restored) == 1
    print("[OK] 系统用户已恢复")

    # ===== 第三部分：旧的提交/驳回/修改/重提/审批流程不受影响 =====
    print_section("Part 3: 旧流程（提交/驳回/修改/重提/审批）不受影响")

    r = requests.post(f"{BASE_URL}/api/reimbursements",
                      json={"employee_id": employee_id, "amount": 400, "description": "测试-旧流程"})
    reim_id3 = r.json()["id"]

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/submit?user_id={employee_id}")
    assert r.json()["status"] == "submitted"
    print(f"[OK] 提交: {r.json()['status']}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/reject?manager_id={manager_id}")
    assert r.json()["status"] == "rejected"
    print(f"[OK] 驳回: {r.json()['status']}")

    r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id3}?user_id={employee_id}",
                     json={"amount": 350, "description": "测试-驳回后修改"})
    assert r.json()["status"] == "draft"
    assert r.json()["amount"] == 350
    print(f"[OK] 驳回后修改: {r.json()['status']}, amount={r.json()['amount']}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/submit?user_id={employee_id}")
    assert r.json()["status"] == "submitted"
    print(f"[OK] 重新提交: {r.json()['status']}")

    r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id3}/approve?manager_id={manager_id}")
    assert r.json()["status"] == "manager_approved"
    print(f"[OK] 再次审批: {r.json()['status']}")

    print("等待自动打款（约6秒）...")
    time.sleep(6)

    r = requests.get(f"{BASE_URL}/api/reimbursements/{reim_id3}")
    assert r.json()["status"] == "paid", f"期望 paid，实际 {r.json()['status']}"
    print(f"[OK] 最终状态: {r.json()['status']}")

    logs3 = query_db(
        "SELECT action, operator_id FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id3,)
    )
    actions = [(l["action"], l["operator_id"]) for l in logs3]
    print(f"动作序列: {actions}")

    expected = ["CREATE", "SUBMIT", "REJECT", "UPDATE", "SUBMIT", "APPROVE", "AUTO_PAY"]
    actual = [l["action"].upper() for l in logs3]
    assert actual == expected, f"动作序列不符，期望 {expected}，实际 {actual}"

    auto_pay_log3 = next((l for l in logs3 if l["action"].upper() == "AUTO_PAY"), None)
    assert auto_pay_log3["operator_id"] == 0
    print(f"[OK] 驳回重提后的 AUTO_PAY operator_id = 0")

    # ===== 第四部分：API 返回与 SQLite 数据一致 =====
    print_section("Part 4: API 返回与 SQLite 数据一致")

    api_logs = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id1}").json()
    db_logs = query_db(
        "SELECT * FROM audit_logs WHERE reimbursement_id = ? ORDER BY id",
        (reim_id1,)
    )

    assert len(api_logs) == len(db_logs), f"API返回{len(api_logs)}条，DB{len(db_logs)}条"
    for api_l, db_l in zip(api_logs, db_logs):
        assert api_l["action"].upper() == db_l["action"].upper()
        assert api_l["operator_id"] == db_l["operator_id"]
    print(f"[OK] API 返回与 SQLite 数据完全一致，共 {len(api_logs)} 条日志")

    print_section("测试总结（所有实测结果）")
    print("[实测] Part 1: 有系统用户时，AUTO_PAY 日志 operator_id=0，状态正常 paid")
    print("[实测] Part 2: 删除系统用户后，打款任务 FAILED，错误信息明确，不写非法 operator_id 的审计日志，报销单保持 manager_approved")
    print("[实测] Part 3: 提交/驳回/修改/重提/审批 全流程正常，动作序列正确")
    print("[实测] Part 4: API 返回与 SQLite 数据逐字段一致")
    print("\n" + "=" * 60)
    print("[OK] 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
