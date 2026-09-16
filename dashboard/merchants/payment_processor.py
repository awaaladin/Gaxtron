"""Central payment router (Adapter Pattern) — ported from GaX/app/services/payment_processor.py.
Only ETH is registered — see merchants/chains.py for why."""
import logging
from decimal import Decimal
from functools import lru_cache

from django.conf import settings

from .chains import BaseChainService, CHAIN_CURRENCIES, EthereumService, IncomingPaymentResult, WalletCreationResult

logger = logging.getLogger(__name__)


class PaymentProcessor:
    def __init__(self):
        registry: dict[str, type[BaseChainService]] = {"ETH": EthereumService}
        enabled = [c.strip().upper() for c in settings.ENABLED_CHAINS.split(",") if c.strip()]
        self.services: dict[str, BaseChainService] = {}
        for chain in enabled:
            cls = registry.get(chain)
            if cls:
                self.services[chain] = cls()

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
        self, chain: str, address: str, amount: Decimal, currency: str, last_scanned_block: int | None = None
    ) -> tuple[IncomingPaymentResult | None, int | None]:
        """Returns (match_or_None, scanned_to_block) — see EthereumService.detect_incoming."""
        self.validate_chain_currency(chain, currency)
        service = self.get_service(chain)
        if hasattr(service, "detect_incoming"):
            return service.detect_incoming(address, amount, currency, last_scanned_block)
        return service.check_payment(address, amount, currency), None

    def check_payment(self, chain: str, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None:
        self.validate_chain_currency(chain, currency)
        return self.get_service(chain).check_payment(address, amount, currency)

    def get_confirmations(self, chain: str, tx_hash: str) -> int:
        return self.get_service(chain).get_confirmations(tx_hash)

    def chain_health(self) -> dict[str, bool]:
        return {chain: svc.is_connected() for chain, svc in self.services.items()}

    def chain_errors(self) -> dict[str, str | None]:
        """Populated by chain_health()'s is_connected() calls — call that first for
        fresh values, since this only reads each service's last recorded error."""
        return {chain: getattr(svc, "last_error", None) for chain, svc in self.services.items()}


@lru_cache
def get_payment_processor() -> PaymentProcessor:
    return PaymentProcessor()
