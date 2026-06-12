import requests
import csv
import io
import time
import pytest

BASE_URL = "http://localhost:8000"

_TEST_ID = int(time.time() * 1000) % 1000000
_seq = 0


def _ext_id(label: str) -> str:
    global _seq
    _seq += 1
    return f"T{_TEST_ID}_{_seq}_{label}"


def _create_user(name: str, role: str, manager_id: int | None = None) -> dict:
    resp = requests.post(
        f"{BASE_URL}/api/reimbursements/users",
        json={"name": name, "role": role, "manager_id": manager_id},
    )
    assert resp.status_code == 200, f"create user failed: {resp.status_code} {resp.text}"
    return resp.json()


def _import_csv(operator_id: int, rows: list[dict], filename: str = "test.csv"):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["external_id", "employee_id", "amount", "description"])
    writer.writeheader()
    writer.writerows(rows)
    files = {"file": (filename, buf.getvalue().encode("utf-8"), "text/csv")}
    return requests.post(
        f"{BASE_URL}/api/import/import?operator_id={operator_id}", files=files
    )


@pytest.fixture(scope="session")
def users():
    manager = _create_user("batch_mgr", "manager")
    employee = _create_user("batch_emp", "employee", manager_id=manager["id"])
    finance = _create_user("batch_fin", "finance")
    return {
        "manager": manager,
        "employee": employee,
        "finance": finance,
    }


@pytest.fixture(scope="session")
def eid(users):
    return users["employee"]["id"]


@pytest.fixture(scope="session")
def fid(users):
    return users["finance"]["id"]


@pytest.fixture(scope="session")
def mid(users):
    return users["manager"]["id"]


class TestBatchImport:
    def test_01_success_import(self, eid, fid):
        rows = [
            {"external_id": _ext_id("A1"), "employee_id": str(eid), "amount": "500", "description": "travel"},
            {"external_id": _ext_id("A2"), "employee_id": str(eid), "amount": "300", "description": "supplies"},
            {"external_id": _ext_id("A3"), "employee_id": str(eid), "amount": "800", "description": "meal"},
        ]
        resp = _import_csv(fid, rows)
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text}"
        result = resp.json()
        batch = result["batch"]
        assert batch["success_count"] == 3, f"expected 3 success, got {batch['success_count']}"
        assert batch["failed_count"] == 0
        assert batch["skipped_count"] == 0
        for line in result["lines"]:
            assert line["status"] == "success", f"line {line['line_number']} unexpected status: {line['status']}"

    def test_02_partial_failure(self, eid, fid):
        rows = [
            {"external_id": _ext_id("B1"), "employee_id": str(eid), "amount": "500", "description": "ok"},
            {"external_id": _ext_id("B2"), "employee_id": "99999", "amount": "300", "description": "bad employee"},
            {"external_id": _ext_id("B3"), "employee_id": str(eid), "amount": "0", "description": "zero amount"},
            {"external_id": _ext_id("B4"), "employee_id": str(eid), "amount": "15000", "description": "over limit"},
            {"external_id": _ext_id("B5"), "employee_id": str(eid), "amount": "200", "description": ""},
            {"external_id": _ext_id("B6"), "employee_id": str(eid), "amount": "-100", "description": "negative"},
        ]
        resp = _import_csv(fid, rows)
        assert resp.status_code == 200
        batch = resp.json()["batch"]
        assert batch["success_count"] == 1, f"expected 1 success, got {batch['success_count']}"
        assert batch["failed_count"] == 5, f"expected 5 failed, got {batch['failed_count']}"

    def test_03_duplicate_external_id(self, eid, fid):
        existing_id = _ext_id("C0")
        create_rows = [
            {"external_id": existing_id, "employee_id": str(eid), "amount": "100", "description": "first"},
        ]
        resp = _import_csv(fid, create_rows)
        assert resp.status_code == 200
        assert resp.json()["batch"]["success_count"] == 1

        dup_id = _ext_id("C_dup")
        dup_rows = [
            {"external_id": existing_id, "employee_id": str(eid), "amount": "200", "description": "cross-batch dup"},
            {"external_id": dup_id, "employee_id": str(eid), "amount": "400", "description": "new one"},
            {"external_id": dup_id, "employee_id": str(eid), "amount": "400", "description": "in-batch dup"},
            {"external_id": _ext_id("C_new"), "employee_id": str(eid), "amount": "300", "description": "another new"},
        ]
        resp = _import_csv(fid, dup_rows)
        assert resp.status_code == 200
        batch = resp.json()["batch"]
        assert batch["success_count"] == 2, f"expected 2 success, got {batch['success_count']}"
        assert batch["skipped_count"] == 1, f"expected 1 skipped, got {batch['skipped_count']}"
        assert batch["failed_count"] == 1, f"expected 1 failed, got {batch['failed_count']}"

    def test_04_permission_denied(self, eid, fid):
        rows = [
            {"external_id": _ext_id("D1"), "employee_id": str(eid), "amount": "500", "description": "perm test"},
        ]
        resp = _import_csv(eid, rows)
        assert resp.status_code == 403, f"expected 403, got {resp.status_code}"

        resp2 = requests.get(f"{BASE_URL}/api/import/batches?user_id={eid}")
        assert resp2.status_code == 403

        resp3 = requests.get(f"{BASE_URL}/api/reimbursements?user_id={eid}")
        assert resp3.status_code == 200

    def test_05_batch_list_and_detail(self, fid):
        resp = requests.get(f"{BASE_URL}/api/import/batches?user_id={fid}&limit=10")
        assert resp.status_code == 200
        batches = resp.json()
        assert len(batches) >= 1

        batch_id = batches[0]["id"]
        resp2 = requests.get(f"{BASE_URL}/api/import/batches/{batch_id}?user_id={fid}")
        assert resp2.status_code == 200
        assert resp2.json()["id"] == batch_id

        resp3 = requests.get(f"{BASE_URL}/api/import/batches/{batch_id}/lines?user_id={fid}")
        assert resp3.status_code == 200
        assert isinstance(resp3.json(), list)

        resp4 = requests.get(f"{BASE_URL}/api/import/batches/{batch_id}/lines?user_id={fid}&status=failed")
        assert resp4.status_code == 200

    def test_06_export_failed(self, eid, fid):
        batches = requests.get(f"{BASE_URL}/api/import/batches?user_id={fid}&limit=10").json()
        target = None
        for b in batches:
            if b["failed_count"] > 0 or b["skipped_count"] > 0:
                target = b
                break
        if not target:
            pytest.skip("no batch with failures to export")

        batch_id = target["id"]
        resp = requests.get(
            f"{BASE_URL}/api/import/batches/{batch_id}/export-failed?user_id={fid}"
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert len(header) >= 2

    def test_07_audit_log_with_batch(self, fid):
        batches = requests.get(f"{BASE_URL}/api/import/batches?user_id={fid}&limit=10").json()
        target = None
        for b in batches:
            if b["success_count"] > 0:
                target = b
                break
        if not target:
            pytest.skip("no successful batch for audit check")

        batch_id = target["id"]
        resp = requests.get(f"{BASE_URL}/api/audit/batch/{batch_id}?user_id={fid}")
        assert resp.status_code == 200
        logs = resp.json()
        assert len(logs) > 0
        assert logs[0]["import_batch_id"] == batch_id
        assert logs[0]["action"] == "batch_import"

    def test_08_max_batch_size(self, eid, fid):
        rows = [
            {"external_id": _ext_id(f"E{i:03d}"), "employee_id": str(eid), "amount": "100", "description": f"row {i}"}
            for i in range(101)
        ]
        resp = _import_csv(fid, rows)
        assert resp.status_code == 400, f"expected 400, got {resp.status_code}"
        assert "100" in resp.json()["detail"]

    def test_09_restart_persistence(self, fid):
        batches = requests.get(f"{BASE_URL}/api/import/batches?user_id={fid}&limit=10").json()
        assert len(batches) > 0, "no batches found - persistence check failed"

    def test_10_draft_status(self, eid, fid):
        ext = _ext_id("F1")
        rows = [
            {"external_id": ext, "employee_id": str(eid), "amount": "200", "description": "draft test"},
        ]
        resp = _import_csv(fid, rows)
        assert resp.status_code == 200
        result = resp.json()
        success_lines = [l for l in result["lines"] if l["status"] == "success"]
        assert len(success_lines) == 1

        reimb_id = success_lines[0]["reimbursement_id"]
        resp2 = requests.get(f"{BASE_URL}/api/reimbursements/{reimb_id}?user_id={fid}")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "draft"
