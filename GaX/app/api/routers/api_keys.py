import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_jwt
from app.config import settings
from app.core.security import generate_api_key, hash_api_key
from app.db.models.api_key import ApiKey
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def _count_active_keys(db: Session, user_id: int) -> int:
    return db.query(ApiKey).filter(ApiKey.user_id == user_id, ApiKey.is_active.is_(True)).count()


@router.get("", response_model=list[ApiKeyResponse])
def list_api_keys(db: Session = Depends(get_db), user: User = Depends(get_current_user_jwt)):
    return db.query(ApiKey).filter(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc()).all()


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_jwt),
):
    if _count_active_keys(db, user.id) >= settings.max_api_keys_per_user:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {settings.max_api_keys_per_user} active API keys allowed",
        )

    raw_key = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:12],
        name=data.name,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    logger.info("API key created for user %s prefix=%s", user.id, api_key.key_prefix)
    return ApiKeyCreatedResponse(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        api_key=raw_key,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_jwt),
):
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user.id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.is_active = False
    db.commit()


@router.post("/{key_id}/regenerate", response_model=ApiKeyCreatedResponse)
def regenerate_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_jwt),
):
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user.id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    if _count_active_keys(db, user.id) >= settings.max_api_keys_per_user:
        api_key.is_active = False

    raw_key = generate_api_key()
    new_key = ApiKey(
        user_id=user.id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:12],
        name=api_key.name,
    )
    api_key.is_active = False
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    return ApiKeyCreatedResponse(
        id=new_key.id,
        key_prefix=new_key.key_prefix,
        name=new_key.name,
        is_active=new_key.is_active,
        created_at=new_key.created_at,
        last_used_at=new_key.last_used_at,
        api_key=raw_key,
    )
