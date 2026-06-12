from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.audit_service import (
    get_audit_logs,
    get_audit_logs_by_reimbursement,
    get_audit_logs_by_operator
)
from app.schemas import AuditLogResponse

router = APIRouter()

@router.get("", response_model=list[AuditLogResponse])
def get_audit_logs_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_audit_logs(db, skip, limit)

@router.get("/reimbursement/{reimbursement_id}", response_model=list[AuditLogResponse])
def get_audit_logs_by_reimbursement_endpoint(reimbursement_id: int, db: Session = Depends(get_db)):
    return get_audit_logs_by_reimbursement(db, reimbursement_id)

@router.get("/operator/{operator_id}", response_model=list[AuditLogResponse])
def get_audit_logs_by_operator_endpoint(operator_id: int, db: Session = Depends(get_db)):
    return get_audit_logs_by_operator(db, operator_id)
