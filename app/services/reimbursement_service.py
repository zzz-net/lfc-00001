from sqlalchemy.orm import Session
from app.models import Reimbursement, ReimbursementStatus, ActionType, AuditLog, User, PaymentTask, PaymentTaskStatus
from app.schemas import ReimbursementCreate, ReimbursementUpdate
from app.config import MAX_REIMBURSEMENT_AMOUNT, VALID_STATUS_TRANSITIONS, PAYMENT_MAX_RETRIES
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)


def create_reimbursement(db: Session, data: ReimbursementCreate):
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="金额必须大于0")

    if data.amount > MAX_REIMBURSEMENT_AMOUNT:
        raise HTTPException(status_code=400, detail=f"金额超过上限 {MAX_REIMBURSEMENT_AMOUNT}")

    employee = db.query(User).filter(User.id == data.employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="员工不存在")

    try:
        reimbursement = Reimbursement(
            employee_id=data.employee_id,
            amount=data.amount,
            description=data.description,
            status=ReimbursementStatus.DRAFT
        )
        db.add(reimbursement)
        db.flush()

        log = AuditLog(
            reimbursement_id=reimbursement.id,
            operator_id=data.employee_id,
            action=ActionType.CREATE,
            before_status=None,
            after_status=ReimbursementStatus.DRAFT
        )
        db.add(log)
        db.commit()
        db.refresh(reimbursement)
        return reimbursement
    except Exception as e:
        db.rollback()
        logger.error(f"创建报销单失败: {e}")
        raise HTTPException(status_code=500, detail="创建报销单失败")


def get_reimbursement(db: Session, reimbursement_id: int):
    return db.query(Reimbursement).filter(Reimbursement.id == reimbursement_id).first()


def _validate_status_transition(current_status: ReimbursementStatus, target_status: ReimbursementStatus):
    current = current_status.value if isinstance(current_status, ReimbursementStatus) else current_status
    target = target_status.value if isinstance(target_status, ReimbursementStatus) else target_status

    if target not in VALID_STATUS_TRANSITIONS.get(current, []):
        raise HTTPException(status_code=400, detail=f"无法从 {current} 状态转换到 {target} 状态")


def _record_audit_log(db: Session, reimbursement_id: int, operator_id: int,
                      action: ActionType, before_status, after_status):
    log = AuditLog(
        reimbursement_id=reimbursement_id,
        operator_id=operator_id,
        action=action,
        before_status=before_status,
        after_status=after_status
    )
    db.add(log)


def update_reimbursement(db: Session, reimbursement_id: int, data: ReimbursementUpdate, user_id: int):
    try:
        reimbursement = db.query(Reimbursement).filter(
            Reimbursement.id == reimbursement_id
        ).with_for_update().first()

        if not reimbursement:
            raise HTTPException(status_code=404, detail="报销单不存在")

        if reimbursement.employee_id != user_id:
            raise HTTPException(status_code=403, detail="无权修改他人报销单")

        if reimbursement.status != ReimbursementStatus.DRAFT:
            raise HTTPException(status_code=400, detail="只能修改草稿状态的报销单")

        before_status = reimbursement.status
        before_amount = reimbursement.amount
        before_desc = reimbursement.description

        if data.amount is not None:
            if data.amount <= 0:
                raise HTTPException(status_code=400, detail="金额必须大于0")
            if data.amount > MAX_REIMBURSEMENT_AMOUNT:
                raise HTTPException(status_code=400, detail=f"金额超过上限 {MAX_REIMBURSEMENT_AMOUNT}")
            reimbursement.amount = data.amount

        if data.description is not None:
            reimbursement.description = data.description

        if data.amount is not None or data.description is not None:
            _record_audit_log(db, reimbursement.id, user_id, ActionType.UPDATE, before_status, reimbursement.status)

        db.commit()
        db.refresh(reimbursement)
        return reimbursement
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"更新报销单失败: {e}")
        raise HTTPException(status_code=500, detail="更新报销单失败")


def submit_reimbursement(db: Session, reimbursement_id: int, user_id: int):
    try:
        reimbursement = db.query(Reimbursement).filter(
            Reimbursement.id == reimbursement_id
        ).with_for_update().first()

        if not reimbursement:
            raise HTTPException(status_code=404, detail="报销单不存在")

        if reimbursement.employee_id != user_id:
            raise HTTPException(status_code=403, detail="无权提交他人报销单")

        _validate_status_transition(reimbursement.status, ReimbursementStatus.SUBMITTED)

        if reimbursement.amount <= 0:
            raise HTTPException(status_code=400, detail="金额必须大于0")
        if reimbursement.amount > MAX_REIMBURSEMENT_AMOUNT:
            raise HTTPException(status_code=400, detail=f"金额超过上限 {MAX_REIMBURSEMENT_AMOUNT}")

        before_status = reimbursement.status
        reimbursement.status = ReimbursementStatus.SUBMITTED
        db.flush()

        _record_audit_log(db, reimbursement.id, user_id, ActionType.SUBMIT, before_status, reimbursement.status)

        db.commit()
        db.refresh(reimbursement)
        return reimbursement
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"提交报销单失败: {e}")
        raise HTTPException(status_code=500, detail="提交报销单失败")


def manager_approve(db: Session, reimbursement_id: int, manager_id: int):
    try:
        reimbursement = db.query(Reimbursement).filter(
            Reimbursement.id == reimbursement_id
        ).with_for_update().first()

        if not reimbursement:
            raise HTTPException(status_code=404, detail="报销单不存在")

        manager = db.query(User).filter(User.id == manager_id).first()
        if not manager or manager.role != "manager":
            raise HTTPException(status_code=403, detail="用户不是经理")

        employee = db.query(User).filter(User.id == reimbursement.employee_id).first()
        if not employee:
            raise HTTPException(status_code=404, detail="员工不存在")

        if employee.manager_id != manager_id:
            raise HTTPException(status_code=403, detail="只能审批下属的报销单")

        if reimbursement.employee_id == manager_id:
            raise HTTPException(status_code=400, detail="不能审批自己的报销单")

        _validate_status_transition(reimbursement.status, ReimbursementStatus.MANAGER_APPROVED)

        before_status = reimbursement.status
        reimbursement.status = ReimbursementStatus.MANAGER_APPROVED
        db.flush()

        _record_audit_log(db, reimbursement.id, manager_id, ActionType.APPROVE, before_status, reimbursement.status)

        existing_task = db.query(PaymentTask).filter(
            PaymentTask.reimbursement_id == reimbursement_id
        ).first()

        if not existing_task:
            task = PaymentTask(
                reimbursement_id=reimbursement.id,
                status=PaymentTaskStatus.PENDING,
                retry_count=0,
                max_retries=PAYMENT_MAX_RETRIES,
                is_processed=False
            )
            db.add(task)
            db.flush()
        else:
            if existing_task.is_processed:
                raise HTTPException(status_code=400, detail="该报销单已有已处理的打款任务")
            existing_task.status = PaymentTaskStatus.PENDING
            existing_task.retry_count = 0
            existing_task.is_processed = False
            existing_task.error_message = None

        db.commit()
        db.refresh(reimbursement)
        return reimbursement
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"审批报销单失败: {e}")
        raise HTTPException(status_code=500, detail="审批报销单失败")


def manager_reject(db: Session, reimbursement_id: int, manager_id: int):
    try:
        reimbursement = db.query(Reimbursement).filter(
            Reimbursement.id == reimbursement_id
        ).with_for_update().first()

        if not reimbursement:
            raise HTTPException(status_code=404, detail="报销单不存在")

        manager = db.query(User).filter(User.id == manager_id).first()
        if not manager or manager.role != "manager":
            raise HTTPException(status_code=403, detail="用户不是经理")

        employee = db.query(User).filter(User.id == reimbursement.employee_id).first()
        if not employee:
            raise HTTPException(status_code=404, detail="员工不存在")

        if employee.manager_id != manager_id:
            raise HTTPException(status_code=403, detail="只能审批下属的报销单")

        if reimbursement.employee_id == manager_id:
            raise HTTPException(status_code=400, detail="不能驳回自己的报销单")

        _validate_status_transition(reimbursement.status, ReimbursementStatus.REJECTED)

        before_status = reimbursement.status
        reimbursement.status = ReimbursementStatus.REJECTED
        db.flush()

        _record_audit_log(db, reimbursement.id, manager_id, ActionType.REJECT, before_status, reimbursement.status)

        existing_task = db.query(PaymentTask).filter(
            PaymentTask.reimbursement_id == reimbursement_id
        ).first()
        if existing_task and not existing_task.is_processed:
            existing_task.status = PaymentTaskStatus.CANCELLED
            existing_task.is_processed = True
            existing_task.error_message = "报销单已驳回"

        db.commit()
        db.refresh(reimbursement)
        return reimbursement
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"驳回报销单失败: {e}")
        raise HTTPException(status_code=500, detail="驳回报销单失败")


def finance_pay(db: Session, reimbursement_id: int, finance_id: int):
    try:
        reimbursement = db.query(Reimbursement).filter(
            Reimbursement.id == reimbursement_id
        ).with_for_update().first()

        if not reimbursement:
            raise HTTPException(status_code=404, detail="报销单不存在")

        finance = db.query(User).filter(User.id == finance_id).first()
        if not finance or finance.role != "finance":
            raise HTTPException(status_code=403, detail="用户不是财务人员")

        _validate_status_transition(reimbursement.status, ReimbursementStatus.PAID)

        payment_task = db.query(PaymentTask).filter(
            PaymentTask.reimbursement_id == reimbursement_id
        ).with_for_update().first()

        if not payment_task:
            raise HTTPException(status_code=400, detail="没有待处理的打款任务")

        if payment_task.is_processed and payment_task.status == PaymentTaskStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="该报销单已打款，不能重复打款")

        if reimbursement.status == ReimbursementStatus.PAID:
            raise HTTPException(status_code=400, detail="该报销单已打款，不能重复打款")

        before_status = reimbursement.status
        reimbursement.status = ReimbursementStatus.PAID
        db.flush()

        payment_task.status = PaymentTaskStatus.COMPLETED
        payment_task.is_processed = True
        payment_task.retry_count += 1
        db.flush()

        _record_audit_log(db, reimbursement.id, finance_id, ActionType.PAY, before_status, reimbursement.status)

        db.commit()
        db.refresh(reimbursement)
        return reimbursement
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"打款失败: {e}")
        raise HTTPException(status_code=500, detail="打款失败")
