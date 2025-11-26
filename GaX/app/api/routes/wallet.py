from app.database import Wallet as WalletModel, Transaction as TransactionModel
from sqlalchemy.orm import Session
from app.schemas.wallet import WalletBalance, Transaction, SendRequest, SendResponse
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.database import SessionLocal
from typing import List
from datetime import datetime

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/api/wallet/balance", response_model=WalletBalance)
def get_balance(db: Session = Depends(get_db), user=Depends(get_current_user)):
    wallet = db.query(WalletModel).filter(WalletModel.user_id == user.id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {"btc": wallet.btc, "eth": wallet.eth, "usdt": wallet.usdt}

@router.get("/api/wallet/transactions", response_model=List[Transaction])
def get_transactions(db: Session = Depends(get_db), user=Depends(get_current_user)):
    txs = db.query(TransactionModel).filter(TransactionModel.user_id == user.id).order_by(TransactionModel.timestamp.desc()).all()
    return [Transaction(
        id=tx.id,
        type=tx.type,
        amount=tx.amount,
        currency=tx.currency,
        address=tx.address,
        timestamp=tx.timestamp.strftime("%Y-%m-%d")
    ) for tx in txs]

@router.post("/api/wallet/send")
def send_crypto(req: Transaction, db: Session = Depends(get_db), user=Depends(get_current_user)):
    wallet = db.query(WalletModel).filter(WalletModel.user_id == user.id).first()
    if req.currency == "BTC":
        if wallet.btc < req.amount:
            raise HTTPException(status_code=400, detail="Insufficient BTC balance")
        wallet.btc -= req.amount
    elif req.currency == "ETH":
        if wallet.eth < req.amount:
            raise HTTPException(status_code=400, detail="Insufficient ETH balance")
        wallet.eth -= req.amount
    elif req.currency == "USDT":
        if wallet.usdt < req.amount:
            raise HTTPException(status_code=400, detail="Insufficient USDT balance")
        wallet.usdt -= req.amount
    else:
        raise HTTPException(status_code=400, detail="Unsupported currency")
    tx = TransactionModel(
        user_id=user.id,
        type="send",
        amount=req.amount,
        currency=req.currency,
        address=req.address,
        timestamp=datetime.utcnow()
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    db.commit()
    return {"success": True, "message": "Transaction sent!", "transaction": req}
