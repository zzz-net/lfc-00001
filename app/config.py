MAX_REIMBURSEMENT_AMOUNT = 10000.0

VALID_STATUS_TRANSITIONS = {
    "draft": ["submitted", "draft"],
    "submitted": ["manager_approved", "rejected"],
    "manager_approved": ["paid"],
    "rejected": ["draft"],
    "paid": []
}

PAYMENT_WORKER_INTERVAL = 5
PAYMENT_MAX_RETRIES = 3
PAYMENT_SIMULATE_FAILURE = False
PAYMENT_FAILURE_RATE = 0.0
