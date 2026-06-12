from sqlalchemy.orm import Session
from app.models import User
from app.schemas import UserCreate
from fastapi import HTTPException

def create_user(db: Session, data: UserCreate):
    user = User(
        name=data.name,
        role=data.role,
        manager_id=data.manager_id
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(User).offset(skip).limit(limit).all()

def get_users_by_role(db: Session, role: str):
    return db.query(User).filter(User.role == role).all()

def get_users_by_manager(db: Session, manager_id: int):
    return db.query(User).filter(User.manager_id == manager_id).all()
