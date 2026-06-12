from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routes import reimbursement, audit, payment, import_batch
from app.database import init_db, SessionLocal
from app.payment_worker import payment_worker
from app.services.payment_service import reset_stuck_processing_tasks
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("正在初始化数据库...")
    init_db()
    logger.info("数据库初始化完成")

    logger.info("正在重置卡住的处理中任务...")
    db = SessionLocal()
    try:
        result = reset_stuck_processing_tasks(db)
        logger.info(f"已重置 {result.get('reset_count', 0)} 个卡住的任务")
    except Exception as e:
        logger.error(f"重置卡住任务失败: {e}")
    finally:
        db.close()

    logger.info("正在启动打款队列处理器...")
    payment_worker.start()
    logger.info("打款队列处理器已启动")

    yield

    logger.info("正在停止打款队列处理器...")
    payment_worker.stop()
    logger.info("打款队列处理器已停止")
    logger.info("服务已关闭")


app = FastAPI(
    title="报销审批系统",
    version="1.0.0",
    description="基于 FastAPI + SQLite 的报销审批后端系统",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reimbursement.router, prefix="/api/reimbursements", tags=["报销单"])
app.include_router(audit.router, prefix="/api/audit", tags=["审计日志"])
app.include_router(payment.router, prefix="/api/payment", tags=["财务打款"])
app.include_router(import_batch.router, prefix="/api/import", tags=["批量导入"])


@app.get("/", tags=["系统"])
async def root():
    return {
        "message": "报销审批系统 API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }


@app.get("/health", tags=["系统"])
async def health_check():
    return {"status": "healthy"}


@app.get("/api/payment/worker/config", tags=["财务打款"])
async def get_worker_config():
    return payment_worker.get_simulate_failure_config()

