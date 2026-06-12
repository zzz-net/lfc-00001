import csv
import io
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import (
    ImportBatch, ImportLine, ImportBatchStatus, ImportLineStatus,
    Reimbursement, ReimbursementStatus, User, AuditLog, ActionType
)
from app.config import MAX_REIMBURSEMENT_AMOUNT, MAX_IMPORT_BATCH_SIZE
from fastapi import HTTPException, UploadFile
from datetime import datetime

logger = logging.getLogger(__name__)


def _validate_import_permission(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role not in ["finance", "manager"]:
        raise HTTPException(status_code=403, detail="只有财务或经理可以导入报销单")
    return user


def _validate_view_batch_permission(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role not in ["finance", "manager"]:
        raise HTTPException(status_code=403, detail="只有财务或经理可以查看导入批次")
    return user


def _validate_row(row: dict, db: Session, seen_external_ids: set, row_num: int) -> tuple[dict, str | None]:
    errors = []
    
    external_id = (row.get("external_id") or "").strip()
    if not external_id:
        errors.append("外部单号不能为空")
    elif external_id in seen_external_ids:
        errors.append("本批内重复外部单号")
    else:
        existing = db.query(Reimbursement).filter(
            Reimbursement.external_id == external_id
        ).first()
        if existing:
            return (row, f"外部单号已存在（报销单ID: {existing.id}）")
    
    employee_id_str = (row.get("employee_id") or "").strip()
    employee_id = None
    if not employee_id_str:
        errors.append("员工ID不能为空")
    else:
        try:
            employee_id = int(employee_id_str)
        except ValueError:
            errors.append("员工ID必须是数字")
        else:
            employee = db.query(User).filter(User.id == employee_id).first()
            if not employee:
                errors.append("员工不存在")
    
    amount_str = (row.get("amount") or "").strip()
    amount = None
    if not amount_str:
        errors.append("金额不能为空")
    else:
        try:
            amount = float(amount_str)
        except ValueError:
            errors.append("金额必须是数字")
        else:
            if amount <= 0:
                errors.append("金额必须大于0")
            elif amount > MAX_REIMBURSEMENT_AMOUNT:
                errors.append(f"金额超过上限 {MAX_REIMBURSEMENT_AMOUNT}")
    
    description = (row.get("description") or "").strip()
    if not description:
        errors.append("描述不能为空")
    
    if errors:
        return (row, "; ".join(errors))
    
    return (row, None)


def batch_import_csv(db: Session, file: UploadFile, operator_id: int) -> ImportBatch:
    _validate_import_permission(db, operator_id)
    
    if not file.filename or not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="请上传CSV文件")
    
    content = file.file.read()
    if isinstance(content, bytes):
        content = content.decode('utf-8')
    
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    
    if not rows:
        raise HTTPException(status_code=400, detail="CSV文件为空或格式错误")
    
    if len(rows) > MAX_IMPORT_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"单次导入最多 {MAX_IMPORT_BATCH_SIZE} 行，当前 {len(rows)} 行"
        )
    
    batch = ImportBatch(
        operator_id=operator_id,
        file_name=file.filename,
        total_count=len(rows),
        success_count=0,
        skipped_count=0,
        failed_count=0,
        status=ImportBatchStatus.PROCESSING
    )
    db.add(batch)
    db.flush()
    
    success_count = 0
    skipped_count = 0
    failed_count = 0
    seen_external_ids = set()
    
    try:
        for idx, row in enumerate(rows, start=1):
            external_id = (row.get("external_id") or "").strip()
            
            validated_row, error = _validate_row(row, db, seen_external_ids, idx)
            
            line = ImportLine(
                batch_id=batch.id,
                line_number=idx,
                external_id=external_id if external_id else None,
                employee_id=int(row.get("employee_id")) if row.get("employee_id") and row.get("employee_id").strip().isdigit() else None,
                amount=float(row.get("amount")) if row.get("amount") and row.get("amount").strip() else None,
                description=row.get("description") if row.get("description") else None,
            )
            
            if error and "已存在" in error:
                line.status = ImportLineStatus.SKIPPED
                line.error_message = error
                skipped_count += 1
            elif error:
                line.status = ImportLineStatus.FAILED
                line.error_message = error
                failed_count += 1
            else:
                employee_id = int(validated_row.get("employee_id"))
                amount = float(validated_row.get("amount"))
                description = validated_row.get("description").strip()
                
                try:
                    reimbursement = Reimbursement(
                        employee_id=employee_id,
                        amount=amount,
                        description=description,
                        status=ReimbursementStatus.DRAFT,
                        external_id=external_id,
                        import_batch_id=batch.id
                    )
                    db.add(reimbursement)
                    db.flush()
                    
                    log = AuditLog(
                        reimbursement_id=reimbursement.id,
                        operator_id=operator_id,
                        action=ActionType.BATCH_IMPORT,
                        before_status=None,
                        after_status=ReimbursementStatus.DRAFT,
                        import_batch_id=batch.id
                    )
                    db.add(log)
                    
                    line.status = ImportLineStatus.SUCCESS
                    line.reimbursement_id = reimbursement.id
                    success_count += 1
                    seen_external_ids.add(external_id)
                except Exception as e:
                    logger.error(f"第 {idx} 行创建报销单失败: {e}")
                    db.rollback()
                    line.status = ImportLineStatus.FAILED
                    line.error_message = f"创建失败: {str(e)}"
                    failed_count += 1
            
            db.add(line)
        
        batch.success_count = success_count
        batch.skipped_count = skipped_count
        batch.failed_count = failed_count
        batch.status = ImportBatchStatus.COMPLETED
        batch.completed_at = datetime.utcnow()
        
        db.commit()
        db.refresh(batch)
        return batch
        
    except Exception as e:
        db.rollback()
        logger.error(f"批量导入失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量导入失败: {str(e)}")


def get_import_batches(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    _validate_view_batch_permission(db, user_id)
    return db.query(ImportBatch).order_by(ImportBatch.id.desc()).offset(skip).limit(limit).all()


def get_import_batch(db: Session, batch_id: int, user_id: int):
    _validate_view_batch_permission(db, user_id)
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return batch


def get_import_lines(db: Session, batch_id: int, user_id: int, status: str | None = None):
    _validate_view_batch_permission(db, user_id)
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    
    query = db.query(ImportLine).filter(ImportLine.batch_id == batch_id)
    if status:
        if status == "success":
            query = query.filter(ImportLine.status == ImportLineStatus.SUCCESS)
        elif status == "skipped":
            query = query.filter(ImportLine.status == ImportLineStatus.SKIPPED)
        elif status == "failed":
            query = query.filter(ImportLine.status == ImportLineStatus.FAILED)
    
    return query.order_by(ImportLine.line_number).all()


def export_failed_lines_csv(db: Session, batch_id: int, user_id: int) -> tuple[str, str]:
    _validate_view_batch_permission(db, user_id)
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    
    failed_lines = db.query(ImportLine).filter(
        ImportLine.batch_id == batch_id,
        ImportLine.status.in_([ImportLineStatus.FAILED, ImportLineStatus.SKIPPED])
    ).order_by(ImportLine.line_number).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["行号", "外部单号", "员工ID", "金额", "描述", "状态", "错误原因"])
    
    for line in failed_lines:
        writer.writerow([
            line.line_number,
            line.external_id or "",
            line.employee_id or "",
            line.amount or "",
            line.description or "",
            line.status.value,
            line.error_message or ""
        ])
    
    filename = f"batch_{batch_id}_failed_lines.csv"
    return filename, output.getvalue()


def get_reimbursements_by_employee(db: Session, employee_id: int, user_id: int, skip: int = 0, limit: int = 100):
    current_user = db.query(User).filter(User.id == user_id).first()
    if not current_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if current_user.role == "employee" and employee_id != user_id:
        raise HTTPException(status_code=403, detail="只能查看自己的报销单")
    
    return db.query(Reimbursement).filter(
        Reimbursement.employee_id == employee_id
    ).order_by(Reimbursement.id.desc()).offset(skip).limit(limit).all()
