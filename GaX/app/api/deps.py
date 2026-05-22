from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.rate_limit import check_auth_rate_limit, check_rate_limit
from app.core.security import decode_access_token, is_valid_api_key_format, verify_api_key
from app.db.models.user import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _apply_rate_limit(user: User) -> None:
    if not check_rate_limit(f"user:{user.id}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )


def get_current_user_api_key(
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
) -> User:
    """Payment endpoints: API key only (production best practice)."""
    if not api_key or not is_valid_api_key_format(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    user = verify_api_key(db, api_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )
    _apply_rate_limit(user)
    return user


def get_current_user(
    db: Session = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
    api_key: str | None = Security(api_key_header),
) -> User:
    """Auth/dashboard routes: JWT or API key."""
    user = None
    if api_key and is_valid_api_key_format(api_key):
        user = verify_api_key(db, api_key)
    elif token:
        email = decode_access_token(token)
        if email:
            user = db.query(User).filter(User.email == email, User.is_active.is_(True)).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _apply_rate_limit(user)
    return user


def get_current_user_jwt(
    db: Session = Depends(get_db),
    token: str | None = Depends(oauth2_scheme),
) -> User:
    """Sensitive operations (API key management): JWT only."""
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    email = decode_access_token(token)
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or suspended")
    _apply_rate_limit(user)
    return user


def rate_limit_auth(request_ip: str = "unknown") -> None:
    if not check_auth_rate_limit(request_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts",
            headers={"Retry-After": "300"},
        )
