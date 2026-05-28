import logging
import secrets

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, rate_limit_auth
from app.core.security import create_access_token, hash_password, verify_password
from app.core.wallet_auth import (
    build_sign_message,
    generate_nonce,
    is_valid_eth_address,
    normalize_address,
    nonce_expires_at,
    verify_wallet_signature,
)
from app.db.models.user import User
from app.db.models.wallet_auth_nonce import WalletAuthNonce
from app.db.session import get_db
from app.schemas.auth import (
    TokenResponse,
    UserRegister,
    UserResponse,
    WalletNonceResponse,
    WalletVerifyRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _token_payload(user: User) -> dict:
    token = create_access_token(user.email)
    return {
        "access_token": token,
        "token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "is_active": user.is_active,
            "wallet_address": user.wallet_address,
        },
    }


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, request: Request, db: Session = Depends(get_db)):
    rate_limit_auth(_client_ip(request))

    if db.query(User).filter((User.email == data.email) | (User.username == data.username)).first():
        raise HTTPException(status_code=400, detail="Email or username already registered")

    user = User(
        email=data.email.lower().strip(),
        username=data.username.strip(),
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("User registered: %s", user.id)
    return _token_payload(user)


@router.post("/login", response_model=TokenResponse)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    rate_limit_auth(_client_ip(request))

    email = form.username.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account suspended")
    return _token_payload(user)


@router.get("/wallet/nonce", response_model=WalletNonceResponse)
def wallet_nonce(request: Request, db: Session = Depends(get_db)):
    """Issue a single-use nonce for wallet signature login."""
    rate_limit_auth(_client_ip(request))

    db.query(WalletAuthNonce).filter(
        WalletAuthNonce.expires_at < datetime.utcnow(),
    ).delete(synchronize_session=False)

    nonce = generate_nonce()
    record = WalletAuthNonce(
        nonce=nonce,
        expires_at=nonce_expires_at(),
    )
    db.add(record)
    db.commit()
    message = build_sign_message(nonce)
    return WalletNonceResponse(nonce=nonce, message=message)


@router.post("/wallet/verify", response_model=TokenResponse)
def wallet_verify(
    body: WalletVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Verify signed nonce and issue JWT (optional auth alongside email login)."""
    rate_limit_auth(_client_ip(request))

    if not is_valid_eth_address(body.address):
        raise HTTPException(status_code=400, detail="Invalid wallet address")

    address = normalize_address(body.address)
    message = build_sign_message(body.nonce.strip())

    if not verify_wallet_signature(body.address, body.signature, message):
        raise HTTPException(status_code=401, detail="Invalid signature")

    record = (
        db.query(WalletAuthNonce)
        .filter(WalletAuthNonce.nonce == body.nonce.strip(), WalletAuthNonce.used_at.is_(None))
        .first()
    )
    if not record or record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Nonce expired or invalid")

    record.used_at = datetime.utcnow()

    user = db.query(User).filter(User.wallet_address == address).first()
    if not user:
        short = address[2:10]
        email = f"{address}@wallet.gaxtron"
        username = f"wallet_{short}"
        base_username = username
        n = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}_{n}"
            n += 1
        user = User(
            email=email,
            username=username,
            wallet_address=address,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        logger.info("Wallet user created: %s (%s)", "pending", address)
    elif not user.is_active:
        raise HTTPException(status_code=403, detail="Account suspended")

    db.commit()
    db.refresh(user)
    logger.info("Wallet login: user %s", user.id)
    return _token_payload(user)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user
