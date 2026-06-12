from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.payment_service import (
    get_payment_tasks,
    get_payment_task,
    get_pending_payment_tasks,
    process_payment_task,
    retry_payment_task,
    get_payment_tasks_by_reimbursement,
    get_failed_payment_tasks,
    get_processing_payment_tasks,
    cancel_payment_task,
    reset_stuck_processing_tasks
)
from app.schemas import (
    PaymentTaskResponse,
    SimulateFailureConfig,
    SimulateFailureResponse,
    WorkerStatusResponse
)
from app.payment_worker import payment_worker
from app.models import PaymentTaskStatus

router = APIRouter()


@router.get("", response_model=list[PaymentTaskResponse])
def get_payment_tasks_endpoint(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return get_payment_tasks(db, skip, limit)


@router.get("/pending", response_model=list[PaymentTaskResponse])
def get_pending_payment_tasks_endpoint(db: Session = Depends(get_db)):
    return get_pending_payment_tasks(db)


@router.get("/failed", response_model=list[PaymentTaskResponse])
def get_failed_payment_tasks_endpoint(db: Session = Depends(get_db)):
    return get_failed_payment_tasks(db)


@router.get("/processing", response_model=list[PaymentTaskResponse])
def get_processing_payment_tasks_endpoint(db: Session = Depends(get_db)):
    return get_processing_payment_tasks(db)


@router.get("/{task_id}", response_model=PaymentTaskResponse)
def get_payment_task_endpoint(task_id: int, db: Session = Depends(get_db)):
    task = get_payment_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="打款任务不存在")
    return task


@router.post("/{task_id}/process")
def process_payment_task_endpoint(task_id: int, finance_id: int, db: Session = Depends(get_db)):
    return process_payment_task(db, task_id, finance_id)


@router.post("/{task_id}/retry", response_model=PaymentTaskResponse)
def retry_payment_task_endpoint(task_id: int, db: Session = Depends(get_db)):
    return retry_payment_task(db, task_id)


@router.post("/{task_id}/cancel", response_model=PaymentTaskResponse)
def cancel_payment_task_endpoint(task_id: int, operator_id: int, db: Session = Depends(get_db)):
    return cancel_payment_task(db, task_id, operator_id)


@router.post("/reset-stuck", tags=["财务打款"])
def reset_stuck_tasks_endpoint(db: Session = Depends(get_db)):
    return reset_stuck_processing_tasks(db)


@router.get("/reimbursement/{reimbursement_id}", response_model=list[PaymentTaskResponse])
def get_payment_tasks_by_reimbursement_endpoint(reimbursement_id: int, db: Session = Depends(get_db)):
    return get_payment_tasks_by_reimbursement(db, reimbursement_id)


@router.post("/simulate-failure", response_model=SimulateFailureResponse, tags=["财务打款"])
def set_simulate_failure(config: SimulateFailureConfig):
    payment_worker.set_simulate_failure(config.enabled, config.failure_rate)
    current_config = payment_worker.get_simulate_failure_config()
    return {
        "simulate_failure": current_config["simulate_failure"],
        "failure_rate": current_config["failure_rate"],
        "message": f"模拟失败已{'开启' if config.enabled else '关闭'}，失败率: {config.failure_rate}"
    }


@router.get("/worker/status", response_model=WorkerStatusResponse, tags=["财务打款"])
def get_worker_status():
    config = payment_worker.get_simulate_failure_config()
    return {
        "status": "running",
        "simulate_failure": config["simulate_failure"],
        "failure_rate": config["failure_rate"]
    }
