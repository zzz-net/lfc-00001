from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./reimbursement.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

SYSTEM_USER_ID = 0
SYSTEM_USER_NAME = "系统"
SYSTEM_USER_ROLE = "system"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app import models
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        system_user = db.query(models.User).filter(
            models.User.id == SYSTEM_USER_ID
        ).first()
        if not system_user:
            system_user = models.User(
                id=SYSTEM_USER_ID,
                name=SYSTEM_USER_NAME,
                role=SYSTEM_USER_ROLE,
                manager_id=None
            )
            db.add(system_user)
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"创建系统用户失败: {e}")
    finally:
        db.close()
