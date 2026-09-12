"""Ported from GaX/app/services/wallet_service.py — Django ORM instead of SQLAlchemy."""
import logging
from decimal import Decimal

from .models import Wallet
from .payment_processor import get_payment_processor

logger = logging.getLogger(__name__)


class WalletService:
    @staticmethod
    def generate_wallet(chain: str, currency: str, user_id: int | None = None, payment_id: int | None = None) -> Wallet:
        processor = get_payment_processor()
        created = processor.create_payment_wallet(chain, currency)

        wallet = Wallet.objects.create(
            user_id=user_id,
            payment_id=payment_id,
            address=created.address,
            encrypted_private_key=created.encrypted_private_key,
            chain=created.chain,
            currency=created.currency,
            balance=Decimal("0"),
        )
        logger.info("Generated %s wallet %s for %s", chain, created.address, currency)
        return wallet

    @staticmethod
    def get_balance(address: str) -> Decimal:
        wallet = Wallet.objects.filter(address=address).first()
        return wallet.balance if wallet else Decimal("0")
