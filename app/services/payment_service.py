from sqlalchemy.orm import Session
from app.models import PaymentTask, PaymentTaskStatus, Reimbursement, ReimbursementStatus, AuditLog, ActionType, User
from app.config import PAYMENT_MAX_RETRIES
from fastapi import HTTPException
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def get_payment_tasks(db: Session, skip: int = 0, limit: int = 100):
    return db.query(PaymentTask).offset(skip).limit(limit).all()


def get_payment_task(db: Session, task_id: int):
    return db.query(PaymentTask).filter(PaymentTask.id == task_id).first()


def get_pending_payment_tasks(db: Session):
    return db.query(PaymentTask).filter(
        PaymentTask.is_processed == False,
        PaymentTask.retry_count < PAYMENT_MAX_RETRIES,
        PaymentTask.status.in_([
            PaymentTaskStatus.PENDING,
            PaymentTaskStatus.FAILED
        ])
    ).all()


def get_payment_tasks_by_reimbursement(db: Session, reimbursement_id: int):
    return db.query(PaymentTask).filter(PaymentTask.reimbursement_id == reimbursement_id).all()


def process_payment_task(db: Session, task_id: int, finance_id: int):
    try:
        task = db.query(PaymentTask).filter(
            PaymentTask.id == task_id
        ).with_for_update().first()

        if not task:
            raise HTTPException(status_code=404, detail="打款任务不存在")

        if task.is_processed:
            raise HTTPException(status_code=400, detail="任务已处理，不能重复执行")

        finance = db.query(User).filter(User.id == finance_id).first()
        if not finance or finance.role != "finance":
            raise HTTPException(status_code=403, detail="用户不是财务人员")

        reimbursement = db.query(Reimbursement).filter(
            Reimbursement.id == task.reimbursement_id
        ).with_for_update().first()

        if not reimbursement:
            raise HTTPException(status_code=404, detail="报销单不存在")

        if reimbursement.status == ReimbursementStatus.PAID:
            task.status = PaymentTaskStatus.COMPLETED
            task.is_processed = True
            db.commit()
            raise HTTPException(status_code=400, detail="该报销单已打款，不能重复打款")

        if reimbursement.status != ReimbursementStatus.MANAGER_APPROVED:
            raise HTTPException(status_code=400, detail=f"报销单状态不正确，当前状态: {reimbursement.status.value}")

        task.status = PaymentTaskStatus.PROCESSING
        task.last_attempt_at = datetime.utcnow()
        db.flush()

        before_status = reimbursement.status
        reimbursement.status = ReimbursementStatus.PAID
        db.flush()

        task.status = PaymentTaskStatus.COMPLETED
        task.is_processed = True
        task.retry_count += 1
        db.flush()

        log = AuditLog(
            reimbursement_id=reimbursement.id,
            operator_id=finance_id,
            action=ActionType.PAY,
            before_status=before_status,
            after_status=ReimbursementStatus.PAID
        )
        db.add(log)

        db.commit()
        db.refresh(reimbursement)
        return reimbursement

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"处理打款任务失败: {e}")
        raise HTTPException(status_code=500, detail="处理打款任务失败")


def retry_payment_task(db: Session, task_id: int):
    from app.payment_worker import payment_worker
    return payment_worker.manual_retry_task(task_id)


def get_failed_payment_tasks(db: Session):
    return db.query(PaymentTask).filter(
        PaymentTask.status == PaymentTaskStatus.FAILED,
        PaymentTask.is_processed == False
    ).all()


def get_processing_payment_tasks(db: Session):
    return db.query(PaymentTask).filter(
        PaymentTask.status == PaymentTaskStatus.PROCESSING
    ).all()


def cancel_payment_task(db: Session, task_id: int, operator_id: int):
    try:
        task = db.query(PaymentTask).filter(
            PaymentTask.id == task_id
        ).with_for_update().first()

        if not task:
            raise HTTPException(status_code=404, detail="打款任务不存在")

        if task.is_processed:
            raise HTTPException(status_code=400, detail="任务已处理，无法取消")

        if task.status == PaymentTaskStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="任务已完成，无法取消")

        operator = db.query(User).filter(User.id == operator_id).first()
        if not operator or operator.role not in ["finance", "manager"]:
            raise HTTPException(status_code=403, detail="无权限取消打款任务")

        task.status = PaymentTaskStatus.CANCELLED
        task.is_processed = True
        task.error_message = f"任务被用户 {operator_id} 取消"
        db.commit()
        db.refresh(task)
        return task

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"取消打款任务失败: {e}")
        raise HTTPException(status_code=500, detail="取消打款任务失败")


def reset_stuck_processing_tasks(db: Session):
    try:
        stuck_tasks = db.query(PaymentTask).filter(
            PaymentTask.status == PaymentTaskStatus.PROCESSING,
            PaymentTask.is_processed == False
        ).all()

        count = 0
        for task in stuck_tasks:
            task.status = PaymentTaskStatus.PENDING
            count += 1
            logger.warning(f"Reset stuck processing task {task.id} to pending")

        db.commit()
        return {"reset_count": count, "tasks_reset": count}

    except Exception as e:
        db.rollback()
        logger.error(f"重置卡住的任务失败: {e}")
        raise HTTPException(status_code=500, detail="重置卡住的任务失败")
