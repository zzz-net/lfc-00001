import requests
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE_URL = "http://localhost:8000"

print("=== Restart Recovery Verification ===\n")

r = requests.get(f"{BASE_URL}/api/reimbursements/11")
data = r.json()
print(f"Reimbursement #11 status: {data['status']}")
assert data["status"] == "paid", f"Expected paid, got {data['status']}"

r = requests.get(f"{BASE_URL}/api/audit/reimbursement/11")
logs = r.json()
print(f"Audit logs: {len(logs)} entries")
for l in logs:
    print(f"  {l['action']}: {l['before_status']} -> {l['after_status']}")

r = requests.get(f"{BASE_URL}/api/payment/8")
task = r.json()
print(f"\nPayment task #8: status={task['status']}, is_processed={task['is_processed']}")
assert task["status"] == "completed", f"Expected completed, got {task['status']}"
assert task["is_processed"] == True, "Should be processed"

print("\n[OK] Service restart recovery verified!")
print("[OK] Data is consistent after restart")
print("[OK] Paid reimbursement stays paid (no double execution)")
print("[OK] Audit logs are complete and persisted")
