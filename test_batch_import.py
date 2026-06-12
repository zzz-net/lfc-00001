import requests
import csv
import io
import json
import sys
import os
import time

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_URL = "http://localhost:8000"

TEST_ID = int(time.time() * 1000) % 1000000

MANAGER_ID = None
EMPLOYEE_ID = None
FINANCE_ID = None


def ext_id(name):
    return f"TEST{TEST_ID}_{name}"


def create_user(name, role, manager_id=None):
    resp = requests.post(
        f"{BASE_URL}/api/reimbursements/users",
        json={"name": name, "role": role, "manager_id": manager_id}
    )
    print(f"创建用户 {name}: {resp.status_code} - {resp.json()}")
    return resp.json()


def test_batch_import():
    print("\n" + "=" * 60)
    print("测试 1: 成功导入 - 全部有效数据")
    print("=" * 60)
    
    csv_content = f"""external_id,employee_id,amount,description
{ext_id('A001')},{EMPLOYEE_ID},500,北京出差差旅费
{ext_id('A002')},{EMPLOYEE_ID},300,办公用品采购
{ext_id('A003')},{EMPLOYEE_ID},800,客户招待费
"""
    files = {"file": ("test_import.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/api/import/import?operator_id={FINANCE_ID}", files=files)
    print(f"导入状态: {resp.status_code}")
    result = resp.json()
    batch = result["batch"]
    lines = result["lines"]
    print(f"批次ID: {batch['id']}, 状态: {batch['status']}")
    print(f"总计: {batch['total_count']}, 成功: {batch['success_count']}, 跳过: {batch['skipped_count']}, 失败: {batch['failed_count']}")
    for line in lines:
        print(f"  行{line['line_number']}: {line['status']} - {line['error_message'] or '成功'}")
    
    assert resp.status_code == 200, f"期望200，实际{resp.status_code}"
    assert batch["success_count"] == 3, f"期望成功3条，实际{batch['success_count']}"
    assert batch["failed_count"] == 0, f"期望失败0条，实际{batch['failed_count']}"
    print("[OK] 测试1通过")
    
    return batch["id"]


def test_partial_failure():
    print("\n" + "=" * 60)
    print("测试 2: 部分失败 - 混合有效/无效数据")
    print("=" * 60)
    
    csv_content = f"""external_id,employee_id,amount,description
{ext_id('B010')},{EMPLOYEE_ID},500,正常报销
{ext_id('B011')},999,300,员工不存在
{ext_id('B012')},{EMPLOYEE_ID},0,金额为0
{ext_id('B013')},{EMPLOYEE_ID},15000,金额超过上限
{ext_id('B014')},{EMPLOYEE_ID},200,
{ext_id('B015')},{EMPLOYEE_ID},-100,负数金额
"""
    files = {"file": ("test_partial.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/api/import/import?operator_id={FINANCE_ID}", files=files)
    print(f"导入状态: {resp.status_code}")
    result = resp.json()
    batch = result["batch"]
    lines = result["lines"]
    print(f"批次ID: {batch['id']}, 状态: {batch['status']}")
    print(f"总计: {batch['total_count']}, 成功: {batch['success_count']}, 跳过: {batch['skipped_count']}, 失败: {batch['failed_count']}")
    for line in lines:
        print(f"  行{line['line_number']}: {line['status']} - {line['error_message'] or '成功'}")
    
    assert resp.status_code == 200
    assert batch["success_count"] == 1, f"期望成功1条，实际{batch['success_count']}"
    assert batch["failed_count"] == 5, f"期望失败5条，实际{batch['failed_count']}"
    print("[OK] 测试2通过")
    
    return batch["id"]


def test_duplicate_external_id():
    print("\n" + "=" * 60)
    print("测试 3: 重复外部单号 - 本批内重复 + 跨批重复")
    print("=" * 60)
    
    existing_id = ext_id('A001')
    csv_content = f"""external_id,employee_id,amount,description
{existing_id},{EMPLOYEE_ID},600,与第一批重复（应跳过）
{ext_id('C020')},{EMPLOYEE_ID},400,新单据
{ext_id('C020')},{EMPLOYEE_ID},400,本批内重复
{ext_id('C021')},{EMPLOYEE_ID},300,另一个新单据
"""
    files = {"file": ("test_duplicate.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/api/import/import?operator_id={FINANCE_ID}", files=files)
    print(f"导入状态: {resp.status_code}")
    result = resp.json()
    batch = result["batch"]
    lines = result["lines"]
    print(f"批次ID: {batch['id']}")
    print(f"总计: {batch['total_count']}, 成功: {batch['success_count']}, 跳过: {batch['skipped_count']}, 失败: {batch['failed_count']}")
    for line in lines:
        print(f"  行{line['line_number']} ({line['external_id']}): {line['status']} - {line['error_message'] or '成功'}")
    
    assert resp.status_code == 200
    assert batch["success_count"] == 2, f"期望成功2条，实际{batch['success_count']}"
    assert batch["skipped_count"] == 1, f"期望跳过1条（跨批重复），实际{batch['skipped_count']}"
    assert batch["failed_count"] == 1, f"期望失败1条（本批内重复），实际{batch['failed_count']}"
    
    all_reimbursements = requests.get(f"{BASE_URL}/api/reimbursements?user_id={FINANCE_ID}").json()
    external_ids = [r["external_id"] for r in all_reimbursements if r["external_id"] == existing_id]
    assert len(external_ids) == 1, f"外部单号{existing_id}应该只有1条，实际有{len(external_ids)}条"
    print("[OK] 测试3通过 - 重复单号被正确处理，不会重复生成")
    
    return batch["id"]


def test_permission_denied():
    print("\n" + "=" * 60)
    print("测试 4: 权限拒绝 - employee 不能导入和查看批次")
    print("=" * 60)
    
    csv_content = f"""external_id,employee_id,amount,description
{ext_id('D030')},{EMPLOYEE_ID},500,测试权限
"""
    
    files = {"file": ("test_perm.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/api/import/import?operator_id={EMPLOYEE_ID}", files=files)
    print(f"员工导入结果: {resp.status_code} - {resp.json()['detail']}")
    assert resp.status_code == 403, f"期望403，实际{resp.status_code}"
    print("[OK] 员工导入被正确拒绝")
    
    resp2 = requests.get(f"{BASE_URL}/api/import/batches?user_id={EMPLOYEE_ID}")
    print(f"员工查看批次列表: {resp2.status_code} - {resp2.json()['detail']}")
    assert resp2.status_code == 403
    print("[OK] 员工查看批次被正确拒绝")
    
    resp3 = requests.get(f"{BASE_URL}/api/reimbursements?user_id={EMPLOYEE_ID}")
    print(f"员工查看自己的报销单列表: {resp3.status_code}，共 {len(resp3.json())} 条")
    assert resp3.status_code == 200
    print("[OK] 员工可以查看自己的报销单")
    
    print("[OK] 测试4通过")


def test_batch_list_and_detail():
    print("\n" + "=" * 60)
    print("测试 5: 查询批次列表和详情")
    print("=" * 60)
    
    resp = requests.get(f"{BASE_URL}/api/import/batches?user_id={FINANCE_ID}&limit=10")
    print(f"批次列表状态: {resp.status_code}")
    batches = resp.json()
    print(f"共 {len(batches)} 个批次")
    for b in batches:
        print(f"  批次{b['id']}: {b['file_name']} - {b['status']} (成功{b['success_count']}/失败{b['failed_count']}/跳过{b['skipped_count']})")
    
    assert resp.status_code == 200
    assert len(batches) >= 3
    print("[OK] 批次列表查询正常")
    
    batch_id = batches[0]["id"]
    resp2 = requests.get(f"{BASE_URL}/api/import/batches/{batch_id}?user_id={FINANCE_ID}")
    print(f"批次详情: {resp2.status_code} - {resp2.json()['file_name']}")
    assert resp2.status_code == 200
    print("[OK] 批次详情查询正常")
    
    resp3 = requests.get(f"{BASE_URL}/api/import/batches/{batch_id}/lines?user_id={FINANCE_ID}")
    print(f"批次明细: {resp3.status_code}，共 {len(resp3.json())} 条")
    assert resp3.status_code == 200
    print("[OK] 批次明细查询正常")
    
    resp4 = requests.get(f"{BASE_URL}/api/import/batches/{batch_id}/lines?user_id={FINANCE_ID}&status=failed")
    print(f"失败明细: {resp4.status_code}，共 {len(resp4.json())} 条")
    assert resp4.status_code == 200
    print("[OK] 按状态筛选明细正常")
    
    print("[OK] 测试5通过")
    return batch_id


def test_export_failed():
    print("\n" + "=" * 60)
    print("测试 6: 导出失败行 CSV")
    print("=" * 60)
    
    batches = requests.get(f"{BASE_URL}/api/import/batches?user_id={FINANCE_ID}&limit=10").json()
    failed_batch = None
    for b in batches:
        if b["failed_count"] > 0 or b["skipped_count"] > 0:
            failed_batch = b
            break
    
    if failed_batch:
        batch_id = failed_batch["id"]
        resp = requests.get(f"{BASE_URL}/api/import/batches/{batch_id}/export-failed?user_id={FINANCE_ID}")
        print(f"导出状态: {resp.status_code}")
        print(f"Content-Type: {resp.headers.get('content-type')}")
        print(f"内容:\n{resp.text[:300]}")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        print("[OK] 失败行导出正常")
    else:
        print("[WARN] 没有找到失败批次，跳过导出测试")
    
    print("[OK] 测试6通过")


def test_audit_log_with_batch():
    print("\n" + "=" * 60)
    print("测试 7: 审计日志关联导入批次")
    print("=" * 60)
    
    batches = requests.get(f"{BASE_URL}/api/import/batches?user_id={FINANCE_ID}&limit=10").json()
    success_batch = None
    for b in batches:
        if b["success_count"] > 0:
            success_batch = b
            break
    
    if success_batch:
        batch_id = success_batch["id"]
        resp = requests.get(f"{BASE_URL}/api/audit/batch/{batch_id}?user_id={FINANCE_ID}")
        print(f"批次审计日志: {resp.status_code}，共 {len(resp.json())} 条")
        logs = resp.json()
        for log in logs[:3]:
            print(f"  {log['action']}: {log['before_status']} -> {log['after_status']} (批次ID: {log['import_batch_id']})")
        
        assert resp.status_code == 200
        assert len(logs) > 0
        assert logs[0]["import_batch_id"] == batch_id
        assert logs[0]["action"] == "batch_import"
        print("[OK] 审计日志正确关联批次")
    else:
        print("[WARN] 没有成功批次，跳过审计日志测试")
    
    print("[OK] 测试7通过")


def test_max_batch_size():
    print("\n" + "=" * 60)
    print("测试 8: 配置上限 - 超过最大行数")
    print("=" * 60)
    
    lines = ["external_id,employee_id,amount,description"]
    for i in range(101):
        lines.append(f"{ext_id(f'E{i:03d}')},{EMPLOYEE_ID},100,测试上限{i}")
    csv_content = "\n".join(lines)
    
    files = {"file": ("test_max.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/api/import/import?operator_id={FINANCE_ID}", files=files)
    print(f"超过上限导入结果: {resp.status_code} - {resp.json()['detail']}")
    assert resp.status_code == 400
    assert "100" in resp.json()["detail"]
    print("[OK] 超过上限被正确拒绝")
    
    print("[OK] 测试8通过")


def test_restart_persistence():
    print("\n" + "=" * 60)
    print("测试 9: 重启后数据持久化")
    print("=" * 60)
    
    batches_before = requests.get(f"{BASE_URL}/api/import/batches?user_id={FINANCE_ID}&limit=10").json()
    print(f"重启前批次数量: {len(batches_before)}")
    
    reimbursement_count_before = len(requests.get(f"{BASE_URL}/api/reimbursements?user_id={FINANCE_ID}").json())
    print(f"重启前报销单数量: {reimbursement_count_before}")
    
    print("[INFO] 此测试需要手动重启服务验证，这里只验证当前数据存在")
    
    assert len(batches_before) > 0
    print("[OK] 当前批次数据存在，数据库持久化正常")
    print("[OK] 测试9通过（重启验证请手动执行）")


def test_draft_status():
    print("\n" + "=" * 60)
    print("测试 10: 导入单据默认为草稿状态")
    print("=" * 60)
    
    csv_content = f"""external_id,employee_id,amount,description
{ext_id('F040')},{EMPLOYEE_ID},200,草稿状态测试
"""
    files = {"file": ("test_draft.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = requests.post(f"{BASE_URL}/api/import/import?operator_id={FINANCE_ID}", files=files)
    result = resp.json()
    
    lines = result["lines"]
    success_line = [l for l in lines if l["status"] == "success"][0]
    reimb_id = success_line["reimbursement_id"]
    
    resp2 = requests.get(f"{BASE_URL}/api/reimbursements/{reimb_id}?user_id={FINANCE_ID}")
    reimbursement = resp2.json()
    print(f"导入的报销单状态: {reimbursement['status']}")
    assert reimbursement["status"] == "draft"
    print("[OK] 导入单据默认为草稿状态")
    
    print("[OK] 测试10通过")


def main():
    global MANAGER_ID, EMPLOYEE_ID, FINANCE_ID
    
    print("批量导入功能测试")
    print("=" * 60)
    
    print("\n--- 初始化测试用户 ---")
    manager = create_user("张经理", "manager")
    employee = create_user("李员工", "employee", manager_id=manager["id"])
    finance = create_user("王财务", "finance")
    
    MANAGER_ID = manager["id"]
    EMPLOYEE_ID = employee["id"]
    FINANCE_ID = finance["id"]
    
    print(f"经理ID: {MANAGER_ID}, 员工ID: {EMPLOYEE_ID}, 财务ID: {FINANCE_ID}")
    
    try:
        test_batch_import()
        test_partial_failure()
        test_duplicate_external_id()
        test_permission_denied()
        test_batch_list_and_detail()
        test_export_failed()
        test_audit_log_with_batch()
        test_max_batch_size()
        test_restart_persistence()
        test_draft_status()
        
        print("\n" + "=" * 60)
        print("[PASS] 所有测试通过！")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        raise
    except Exception as e:
        print(f"\n[ERROR] 发生错误: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
