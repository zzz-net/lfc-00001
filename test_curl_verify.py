import requests
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8000"

print("=== 接口验证脚本（curl 风格）===\n")

print("[1] 创建报销单")
r = requests.post(f"{BASE_URL}/api/reimbursements",
                  json={"employee_id": 2, "amount": 800, "description": "curl测试-差旅"})
print(f"    POST /api/reimbursements -> {r.status_code}")
reim_id = r.json()["id"]
print(f"    结果: id={reim_id}, status={r.json()['status']}")
assert r.status_code == 200

print("\n[2] 提交报销单")
r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id=2")
print(f"    POST /api/reimbursements/{reim_id}/submit -> {r.status_code}")
print(f"    结果: status={r.json()['status']}")
assert r.status_code == 200
assert r.json()["status"] == "submitted"

print("\n[3] 经理驳回")
r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/reject?manager_id=1")
print(f"    POST /api/reimbursements/{reim_id}/reject -> {r.status_code}")
print(f"    结果: status={r.json()['status']}")
assert r.status_code == 200
assert r.json()["status"] == "rejected"

print("\n[4] 员工修改驳回单（自动转回 draft）")
r = requests.put(f"{BASE_URL}/api/reimbursements/{reim_id}?user_id=2",
                  json={"amount": 600, "description": "curl测试-差旅（调整）"})
print(f"    PUT /api/reimbursements/{reim_id} -> {r.status_code}")
print(f"    结果: amount={r.json()['amount']}, status={r.json()['status']}")
assert r.status_code == 200
assert r.json()["status"] == "draft"
assert r.json()["amount"] == 600

print("\n[5] 重新提交")
r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/submit?user_id=2")
print(f"    POST /api/reimbursements/{reim_id}/submit -> {r.status_code}")
print(f"    结果: status={r.json()['status']}")
assert r.status_code == 200
assert r.json()["status"] == "submitted"

print("\n[6] 经理审批通过")
r = requests.post(f"{BASE_URL}/api/reimbursements/{reim_id}/approve?manager_id=1")
print(f"    POST /api/reimbursements/{reim_id}/approve -> {r.status_code}")
print(f"    结果: status={r.json()['status']}")
assert r.status_code == 200
assert r.json()["status"] == "manager_approved"

print("\n[7] 查看审计日志")
r = requests.get(f"{BASE_URL}/api/audit/reimbursement/{reim_id}")
print(f"    GET /api/audit/reimbursement/{reim_id} -> {r.status_code}")
logs = r.json()
print(f"    日志 {len(logs)} 条:")
actions = []
for l in logs:
    actions.append(l["action"])
    print(f"      {l['action']}: {l['before_status']} -> {l['after_status']}")

assert "reject" in actions
assert "update" in actions

update_log = next(l for l in logs if l["action"] == "update")
assert update_log["before_status"] == "rejected"
assert update_log["after_status"] == "draft"
print("\n    [OK] update 日志: rejected -> draft 正确！")

print("\n" + "=" * 50)
print("[OK] 所有 curl 风格接口测试通过！")
print("=" * 50)
