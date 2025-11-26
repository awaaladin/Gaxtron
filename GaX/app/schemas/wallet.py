from pydantic import BaseModel
from typing import List

class WalletBalance(BaseModel):
    btc: float
    eth: float
    usdt: float

class Transaction(BaseModel):
    id: int
    type: str  # 'send' or 'receive'
    amount: float
    currency: str  # 'BTC', 'ETH', or 'USDT'
    address: str
    timestamp: str

class SendRequest(BaseModel):
    recipient: str
    amount: float
    currency: str

class SendResponse(BaseModel):
    success: bool
    message: str
    transaction: Transaction = None

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
