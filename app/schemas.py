from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from app.models import ReimbursementStatus, ActionType, PaymentTaskStatus
from typing import Optional

class UserCreate(BaseModel):
    name: str
    role: str
    manager_id: int | None = None

class UserResponse(BaseModel):
    id: int
    name: str
    role: str
    manager_id: int | None

    class Config:
        from_attributes = True

class ReimbursementCreate(BaseModel):
    employee_id: int
    amount: float = Field(gt=0, description="金额必须大于0")
    description: str

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('金额必须大于0')
        return v

class ReimbursementUpdate(BaseModel):
    amount: float | None = None
    description: str | None = None

    @field_validator('amount')
    @classmethod
    def amount_must_be_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError('金额必须大于0')
        return v

class ReimbursementResponse(BaseModel):
    id: int
    employee_id: int
    amount: float
    description: str
    status: ReimbursementStatus
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True

class AuditLogResponse(BaseModel):
    id: int
    reimbursement_id: int
    operator_id: int
    action: ActionType
    before_status: ReimbursementStatus | None
    after_status: ReimbursementStatus | None
    created_at: datetime

    class Config:
        from_attributes = True

class PaymentTaskResponse(BaseModel):
    id: int
    reimbursement_id: int
    status: PaymentTaskStatus
    retry_count: int
    max_retries: int
    is_processed: bool
    error_message: str | None
    last_attempt_at: datetime | None
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True

class SimulateFailureConfig(BaseModel):
    enabled: bool
    failure_rate: float = Field(ge=0.0, le=1.0, default=0.5)

class SimulateFailureResponse(BaseModel):
    simulate_failure: bool
    failure_rate: float
    message: str

class WorkerStatusResponse(BaseModel):
    status: str
    simulate_failure: bool
    failure_rate: float

class ApprovalRequest(BaseModel):
    reimbursement_id: int
    manager_id: int

class RejectionRequest(BaseModel):
    reimbursement_id: int
    manager_id: int

class PaymentRequest(BaseModel):
    reimbursement_id: int
    finance_id: int
