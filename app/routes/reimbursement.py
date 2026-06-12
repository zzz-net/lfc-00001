from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.reimbursement_service import (
    create_reimbursement,
    get_reimbursement,
    update_reimbursement,
    submit_reimbursement,
    manager_approve,
    manager_reject,
    finance_pay
)
from app.services.user_service import create_user, get_users, get_user
from app.schemas import (
    ReimbursementCreate,
    ReimbursementUpdate,
    ReimbursementResponse,
    UserCreate,
    UserResponse,
    ApprovalRequest,
    RejectionRequest,
    PaymentRequest
)

router = APIRouter()

@router.post("/users", response_model=UserResponse, tags=["用户"])
def create_user_endpoint(data: UserCreate, db: Session = Depends(get_db)):
    return create_user(db, data)

@router.get("/users", response_model=list[UserResponse], tags=["用户"])
def get_users_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_users(db, skip, limit)

@router.get("/users/{user_id}", response_model=UserResponse, tags=["用户"])
def get_user_endpoint(user_id: int, db: Session = Depends(get_db)):
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

@router.post("", response_model=ReimbursementResponse)
def create_reimbursement_endpoint(data: ReimbursementCreate, db: Session = Depends(get_db)):
    return create_reimbursement(db, data)

@router.get("/{reimbursement_id}", response_model=ReimbursementResponse)
def get_reimbursement_endpoint(reimbursement_id: int, db: Session = Depends(get_db)):
    reimbursement = get_reimbursement(db, reimbursement_id)
    if not reimbursement:
        raise HTTPException(status_code=404, detail="报销单不存在")
    return reimbursement

@router.put("/{reimbursement_id}", response_model=ReimbursementResponse)
def update_reimbursement_endpoint(reimbursement_id: int, data: ReimbursementUpdate, user_id: int, db: Session = Depends(get_db)):
    return update_reimbursement(db, reimbursement_id, data, user_id)

@router.post("/{reimbursement_id}/submit")
def submit_reimbursement_endpoint(reimbursement_id: int, user_id: int, db: Session = Depends(get_db)):
    return submit_reimbursement(db, reimbursement_id, user_id)

@router.post("/{reimbursement_id}/approve")
def approve_reimbursement_endpoint(reimbursement_id: int, manager_id: int, db: Session = Depends(get_db)):
    return manager_approve(db, reimbursement_id, manager_id)

@router.post("/{reimbursement_id}/reject")
def reject_reimbursement_endpoint(reimbursement_id: int, manager_id: int, db: Session = Depends(get_db)):
    return manager_reject(db, reimbursement_id, manager_id)

@router.post("/{reimbursement_id}/pay")
def pay_reimbursement_endpoint(reimbursement_id: int, finance_id: int, db: Session = Depends(get_db)):
    return finance_pay(db, reimbursement_id, finance_id)
