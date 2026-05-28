"""Ethereum wallet signature verification for optional login."""
import re
import secrets
from datetime import datetime, timedelta

from eth_account import Account
from eth_account.messages import encode_defunct

ETH_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
NONCE_TTL_MINUTES = 5


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)


def build_sign_message(nonce: str) -> str:
    return f"Sign in to Gaxtron\n\nNonce: {nonce}\n"


def is_valid_eth_address(address: str) -> bool:
    return bool(address and ETH_ADDRESS_RE.match(address.strip()))


def normalize_address(address: str) -> str:
    return address.strip().lower()


def verify_wallet_signature(address: str, signature: str, message: str) -> bool:
    if not is_valid_eth_address(address):
        return False
    try:
        msg = encode_defunct(text=message)
        recovered = Account.recover_message(msg, signature=signature)
        return normalize_address(recovered) == normalize_address(address)
    except (ValueError, TypeError):
        return False


def nonce_expires_at() -> datetime:
    return datetime.utcnow() + timedelta(minutes=NONCE_TTL_MINUTES)
