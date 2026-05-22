"""
Chain adapter interface — each blockchain implements this contract.
PaymentProcessor routes create/check operations to the correct adapter.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class WalletCreationResult:
    address: str
    encrypted_private_key: str
    chain: str
    currency: str


@dataclass
class IncomingPaymentResult:
    tx_hash: str
    from_address: str
    confirmations: int
    block_number: int | None = None


class BaseChainService(ABC):
    chain_id: str  # ETH, TRON, BTC, SOL

    @abstractmethod
    def is_connected(self) -> bool:
        """RPC/API reachable."""

    @abstractmethod
    def required_confirmations(self) -> int:
        pass

    @abstractmethod
    def create_wallet(self, currency: str) -> WalletCreationResult:
        """Generate deposit address + encrypted secret for storage."""

    @abstractmethod
    def check_payment(self, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None:
        """
        Return incoming tx when amount received AND confirmations >= required.
        Return None if nothing found yet.
        """

    @abstractmethod
    def get_confirmations(self, tx_hash: str) -> int:
        pass

    def supports_currency(self, currency: str) -> bool:
        return currency.upper() in self.supported_currencies()

    @abstractmethod
    def supported_currencies(self) -> tuple[str, ...]:
        pass
