from sqlalchemy.orm import Session
from app.models import AuditLog, Reimbursement

def get_audit_logs(db: Session, skip: int = 0, limit: int = 100):
    return db.query(AuditLog).offset(skip).limit(limit).all()

def get_audit_logs_by_reimbursement(db: Session, reimbursement_id: int):
    return db.query(AuditLog).filter(AuditLog.reimbursement_id == reimbursement_id).all()

def get_audit_logs_by_operator(db: Session, operator_id: int):
    return db.query(AuditLog).filter(AuditLog.operator_id == operator_id).all()
