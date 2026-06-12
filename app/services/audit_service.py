from sqlalchemy.orm import Session
from app.models import AuditLog, Reimbursement, User, ImportBatch
from fastapi import HTTPException

def get_audit_logs(db: Session, skip: int = 0, limit: int = 100):
    return db.query(AuditLog).order_by(AuditLog.id.desc()).offset(skip).limit(limit).all()

def get_audit_logs_by_reimbursement(db: Session, reimbursement_id: int, user_id: int | None = None):
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        reimbursement = db.query(Reimbursement).filter(Reimbursement.id == reimbursement_id).first()
        if not reimbursement:
            raise HTTPException(status_code=404, detail="报销单不存在")
        if user.role == "employee" and reimbursement.employee_id != user_id:
            raise HTTPException(status_code=403, detail="只能查看自己报销单的审计日志")
    
    return db.query(AuditLog).filter(AuditLog.reimbursement_id == reimbursement_id).order_by(AuditLog.id).all()

def get_audit_logs_by_operator(db: Session, operator_id: int):
    return db.query(AuditLog).filter(AuditLog.operator_id == operator_id).order_by(AuditLog.id.desc()).all()

def get_audit_logs_by_batch(db: Session, batch_id: int, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role not in ["finance", "manager"]:
        raise HTTPException(status_code=403, detail="只有财务或经理可以查看导入批次的审计日志")
    
    batch = db.query(ImportBatch).filter(ImportBatch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    
    return db.query(AuditLog).filter(
        AuditLog.import_batch_id == batch_id
    ).order_by(AuditLog.id).all()
