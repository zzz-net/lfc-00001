import threading
import time
import random
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import (
    PaymentTask,
    PaymentTaskStatus,
    Reimbursement,
    ReimbursementStatus,
    AuditLog,
    ActionType,
    User
)
from app.config import (
    PAYMENT_WORKER_INTERVAL,
    PAYMENT_MAX_RETRIES,
    PAYMENT_SIMULATE_FAILURE,
    PAYMENT_FAILURE_RATE
)
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class PaymentWorker:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._simulate_failure = PAYMENT_SIMULATE_FAILURE
        self._failure_rate = PAYMENT_FAILURE_RATE
        self._lock = threading.Lock()

    def set_simulate_failure(self, enabled: bool, failure_rate: float = 0.5):
        with self._lock:
            self._simulate_failure = enabled
            self._failure_rate = min(max(failure_rate, 0.0), 1.0)

    def get_simulate_failure_config(self):
        with self._lock:
            return {
                "simulate_failure": self._simulate_failure,
                "failure_rate": self._failure_rate
            }

    def start(self):
        if self._thread and self._thread.is_alive():
            logger.info("Payment worker is already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Payment worker started")

    def stop(self):
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=10)
            logger.info("Payment worker stopped")

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._process_pending_tasks()
            except Exception as e:
                logger.error(f"Error in payment worker loop: {e}")

            self._stop_event.wait(PAYMENT_WORKER_INTERVAL)

    def _process_pending_tasks(self):
        db = SessionLocal()
        try:
            tasks = self._get_recoverable_tasks(db)
            for task in tasks:
                if self._stop_event.is_set():
                    break
                self._process_single_task(db, task)
                db.commit()
        finally:
            db.close()

    def _get_recoverable_tasks(self, db: Session):
        return db.query(PaymentTask).filter(
            PaymentTask.is_processed == False,
            PaymentTask.retry_count < PAYMENT_MAX_RETRIES,
            PaymentTask.status.in_([
                PaymentTaskStatus.PENDING,
                PaymentTaskStatus.FAILED,
                PaymentTaskStatus.PROCESSING
            ])
        ).order_by(PaymentTask.created_at.asc()).all()

    def _process_single_task(self, db: Session, task: PaymentTask):
        with self._lock:
            simulate_failure = self._simulate_failure
            failure_rate = self._failure_rate

        if task.status == PaymentTaskStatus.PROCESSING:
            task.status = PaymentTaskStatus.PENDING
            db.flush()
            logger.warning(f"Recovered task {task.id} from PROCESSING state")

        reimbursement = db.query(Reimbursement).filter(
            Reimbursement.id == task.reimbursement_id
        ).with_for_update().first()

        if not reimbursement:
            task.status = PaymentTaskStatus.CANCELLED
            task.is_processed = True
            task.error_message = "报销单不存在"
            logger.error(f"Task {task.id}: reimbursement {task.reimbursement_id} not found")
            return

        if reimbursement.status == ReimbursementStatus.PAID:
            task.status = PaymentTaskStatus.COMPLETED
            task.is_processed = True
            logger.warning(f"Task {task.id}: reimbursement {task.reimbursement_id} already paid, marking as completed")
            return

        if reimbursement.status != ReimbursementStatus.MANAGER_APPROVED:
            task.status = PaymentTaskStatus.CANCELLED
            task.is_processed = True
            task.error_message = f"报销单状态不正确: {reimbursement.status.value}"
            logger.error(f"Task {task.id}: invalid status {reimbursement.status.value}")
            return

        task.status = PaymentTaskStatus.PROCESSING
        task.last_attempt_at = datetime.utcnow()
        db.flush()

        try:
            success = self._execute_payment(task, reimbursement, simulate_failure, failure_rate)
            if success:
                self._mark_payment_successful(db, task, reimbursement)
                logger.info(f"Task {task.id}: payment completed successfully")
            else:
                self._mark_payment_failed(db, task, reimbursement, "模拟打款失败")
                logger.warning(f"Task {task.id}: payment failed (simulated)")

        except Exception as e:
            db.rollback()
            db.refresh(task)
            self._mark_payment_failed(db, task, reimbursement, str(e))
            logger.error(f"Task {task.id}: payment failed with exception: {e}")

    def _execute_payment(self, task: PaymentTask, reimbursement: Reimbursement,
                         simulate_failure: bool, failure_rate: float) -> bool:
        if simulate_failure and random.random() < failure_rate:
            return False

        time.sleep(0.5)
        return True

    def _mark_payment_successful(self, db: Session, task: PaymentTask, reimbursement: Reimbursement):
        before_status = reimbursement.status

        task.status = PaymentTaskStatus.COMPLETED
        task.is_processed = True
        db.flush()

        reimbursement.status = ReimbursementStatus.PAID
        db.flush()

        finance_user = db.query(User).filter(User.role == "finance").first()
        operator_id = finance_user.id if finance_user else 0

        log = AuditLog(
            reimbursement_id=reimbursement.id,
            operator_id=operator_id,
            action=ActionType.PAY,
            before_status=before_status,
            after_status=ReimbursementStatus.PAID
        )
        db.add(log)
        db.commit()

    def _mark_payment_failed(self, db: Session, task: PaymentTask, reimbursement: Reimbursement, error_msg: str):
        task.retry_count += 1
        task.error_message = error_msg
        task.last_attempt_at = datetime.utcnow()

        if task.retry_count >= PAYMENT_MAX_RETRIES:
            task.status = PaymentTaskStatus.FAILED
        else:
            task.status = PaymentTaskStatus.FAILED

        db.flush()

        finance_user = db.query(User).filter(User.role == "finance").first()
        operator_id = finance_user.id if finance_user else 0

        log = AuditLog(
            reimbursement_id=reimbursement.id,
            operator_id=operator_id,
            action=ActionType.PAYMENT_FAILED,
            before_status=reimbursement.status,
            after_status=reimbursement.status
        )
        db.add(log)
        db.commit()

    def manual_retry_task(self, task_id: int) -> PaymentTask:
        db = SessionLocal()
        try:
            task = db.query(PaymentTask).filter(PaymentTask.id == task_id).first()
            if not task:
                raise HTTPException(status_code=404, detail="打款任务不存在")

            if task.is_processed:
                raise HTTPException(status_code=400, detail="任务已处理，无法重试")

            if task.retry_count >= PAYMENT_MAX_RETRIES:
                task.retry_count = 0

            task.status = PaymentTaskStatus.PENDING
            task.error_message = None
            task.last_attempt_at = None
            db.flush()

            reimbursement = db.query(Reimbursement).filter(
                Reimbursement.id == task.reimbursement_id
            ).first()

            if reimbursement:
                log = AuditLog(
                    reimbursement_id=reimbursement.id,
                    operator_id=0,
                    action=ActionType.PAYMENT_RETRY,
                    before_status=reimbursement.status,
                    after_status=reimbursement.status
                )
                db.add(log)

            db.commit()
            db.refresh(task)
            return task
        finally:
            db.close()


payment_worker = PaymentWorker()
