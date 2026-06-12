from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Boolean, Text
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
    BATCH_IMPORT = "batch_import"

class PaymentTaskStatus(PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ImportBatchStatus(PyEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ImportLineStatus(PyEnum):
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"

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
    external_id = Column(String, index=True, nullable=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True)
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
    import_batch_id = Column(Integer, ForeignKey("import_batches.id"), nullable=True)
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

class ImportBatch(Base):
    __tablename__ = "import_batches"
    
    id = Column(Integer, primary_key=True, index=True)
    operator_id = Column(Integer, ForeignKey("users.id"))
    file_name = Column(String)
    total_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    status = Column(Enum(ImportBatchStatus), default=ImportBatchStatus.PROCESSING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

class ImportLine(Base):
    __tablename__ = "import_lines"
    
    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("import_batches.id"), index=True)
    line_number = Column(Integer)
    external_id = Column(String, index=True, nullable=True)
    employee_id = Column(Integer, nullable=True)
    amount = Column(Float, nullable=True)
    description = Column(String, nullable=True)
    status = Column(Enum(ImportLineStatus))
    error_message = Column(String, nullable=True)
    reimbursement_id = Column(Integer, ForeignKey("reimbursements.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
