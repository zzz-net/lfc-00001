from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.audit_service import (
    get_audit_logs,
    get_audit_logs_by_reimbursement,
    get_audit_logs_by_operator,
    get_audit_logs_by_batch
)
from app.schemas import AuditLogResponse

router = APIRouter()

@router.get("", response_model=list[AuditLogResponse])
def get_audit_logs_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_audit_logs(db, skip, limit)

@router.get("/reimbursement/{reimbursement_id}", response_model=list[AuditLogResponse])
def get_audit_logs_by_reimbursement_endpoint(
    reimbursement_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    return get_audit_logs_by_reimbursement(db, reimbursement_id, user_id)

@router.get("/operator/{operator_id}", response_model=list[AuditLogResponse])
def get_audit_logs_by_operator_endpoint(operator_id: int, db: Session = Depends(get_db)):
    return get_audit_logs_by_operator(db, operator_id)

@router.get("/batch/{batch_id}", response_model=list[AuditLogResponse], tags=["审计日志"])
def get_audit_logs_by_batch_endpoint(
    batch_id: int,
    user_id: int = Query(...),
    db: Session = Depends(get_db)
):
    return get_audit_logs_by_batch(db, batch_id, user_id)
