from app.database import User as UserModel
from app.schemas.wallet import UserCreate
from sqlalchemy.orm import Session

def create_user(db: Session, user: UserCreate):
    db_user = UserModel(username=user.username, hashed_password=user.password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
