from app.database import Wallet as WalletModel, Transaction as TransactionModel
from sqlalchemy.orm import Session
from app.schemas.wallet import Transaction

def get_wallet_by_user(db: Session, user_id: int):
    return db.query(WalletModel).filter(WalletModel.user_id == user_id).first()

def get_transactions_by_user(db: Session, user_id: int):
    return db.query(TransactionModel).filter(TransactionModel.user_id == user_id).order_by(TransactionModel.timestamp.desc()).all()

def create_transaction(db: Session, tx: TransactionModel):
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx
