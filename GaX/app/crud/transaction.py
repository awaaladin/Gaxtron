from app.database import Transaction as TransactionModel
from sqlalchemy.orm import Session

def create_transaction(db: Session, tx: TransactionModel):
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx

def get_transactions_by_user(db: Session, user_id: int):
    return db.query(TransactionModel).filter(TransactionModel.user_id == user_id).order_by(TransactionModel.timestamp.desc()).all()
