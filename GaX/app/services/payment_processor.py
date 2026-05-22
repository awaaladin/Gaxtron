"""
Central payment router — Adapter Pattern.

Frontend → FastAPI → PaymentProcessor → Chain Service → RPC/API
"""
import logging
from decimal import Decimal
from functools import lru_cache

from app.chains.base import BaseChainService, IncomingPaymentResult, WalletCreationResult
from app.chains.bitcoin_service import BitcoinService
from app.chains.ethereum_service import EthereumService
from app.chains.solana_service import SolanaService
from app.chains.tron_service import TronService
from app.chains.registry import CHAIN_CURRENCIES
from app.config import settings

logger = logging.getLogger(__name__)


class PaymentProcessor:
    """
    Routes payment creation and verification to the correct blockchain adapter.
    """

    def __init__(self):
        registry: dict[str, type[BaseChainService]] = {
            "ETH": EthereumService,
            "TRON": TronService,
            "BTC": BitcoinService,
            "SOL": SolanaService,
        }
        enabled = settings.enabled_chain_list
        self.services: dict[str, BaseChainService] = {}
        for chain in enabled:
            cls = registry.get(chain.upper())
            if cls:
                self.services[chain.upper()] = cls()

    def get_service(self, chain: str) -> BaseChainService:
        chain = chain.upper()
        service = self.services.get(chain)
        if not service:
            raise ValueError(f"Unsupported chain: {chain}. Supported: {list(self.services.keys())}")
        return service

    @staticmethod
    def validate_chain_currency(chain: str, currency: str) -> None:
        chain = chain.upper()
        currency = currency.upper()
        allowed = CHAIN_CURRENCIES.get(chain)
        if not allowed:
            raise ValueError(f"Unsupported chain: {chain}")
        if currency not in allowed:
            raise ValueError(f"Currency {currency} not supported on {chain}. Allowed: {allowed}")

    def create_payment_wallet(self, chain: str, currency: str) -> WalletCreationResult:
        self.validate_chain_currency(chain, currency)
        service = self.get_service(chain)
        if not service.supports_currency(currency):
            raise ValueError(f"{service.chain_id} does not support {currency}")
        return service.create_wallet(currency)

    def detect_payment(
        self, chain: str, address: str, amount: Decimal, currency: str
    ) -> IncomingPaymentResult | None:
        self.validate_chain_currency(chain, currency)
        service = self.get_service(chain)
        if hasattr(service, "detect_incoming"):
            return service.detect_incoming(address, amount, currency)
        return service.check_payment(address, amount, currency)

    def check_payment(
        self, chain: str, address: str, amount: Decimal, currency: str
    ) -> IncomingPaymentResult | None:
        self.validate_chain_currency(chain, currency)
        service = self.get_service(chain)
        return service.check_payment(address, amount, currency)

    def get_confirmations(self, chain: str, tx_hash: str) -> int:
        return self.get_service(chain).get_confirmations(tx_hash)

    def chain_health(self) -> dict[str, bool]:
        return {chain: svc.is_connected() for chain, svc in self.services.items()}


@lru_cache
def get_payment_processor() -> PaymentProcessor:
    return PaymentProcessor()
