from sqlalchemy import Column, Integer, String, Float
from app.database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class Wallet(Base):
    __tablename__ = 'wallets'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    btc = Column(Float, default=0)
    eth = Column(Float, default=0)
    usdt = Column(Float, default=0)
    sol = Column(Float, default=0)

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    type = Column(String, nullable=False)  # 'send' or 'receive'
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=False)
    address = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)
