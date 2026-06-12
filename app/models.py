from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean
from sqlalchemy.sql import func
from app.database import Base
from enum import Enum as PyEnum

class ReimbursementStatus(PyEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    MANAGER_APPROVED = "manager_approved"
    REJECTED = "rejected"
    PAID = "paid"

class ActionType(PyEnum):
    CREATE = "create"
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    PAY = "pay"
    UPDATE = "update"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_RETRY = "payment_retry"
    AUTO_PAY = "auto_pay"

class PaymentTaskStatus(PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    role = Column(String, index=True)
    manager_id = Column(Integer, ForeignKey("users.id"))

class Reimbursement(Base):
    __tablename__ = "reimbursements"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"))
    amount = Column(Float)
    description = Column(String)
    status = Column(Enum(ReimbursementStatus))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    reimbursement_id = Column(Integer, ForeignKey("reimbursements.id"))
    operator_id = Column(Integer, ForeignKey("users.id"))
    action = Column(Enum(ActionType))
    before_status = Column(Enum(ReimbursementStatus))
    after_status = Column(Enum(ReimbursementStatus))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PaymentTask(Base):
    __tablename__ = "payment_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    reimbursement_id = Column(Integer, ForeignKey("reimbursements.id"))
    status = Column(Enum(PaymentTaskStatus), default=PaymentTaskStatus.PENDING)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_processed = Column(Boolean, default=False)
    error_message = Column(String, nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
