"""
Blockchain adapter — ported from GaX/app/chains/{base,ethereum_service,registry}.py.
Only ETH is ported: settings.ENABLED_CHAINS defaults to "ETH" and the TRON/BTC/SOL adapters
in the original codebase need third-party packages (tronpy, bitcoinlib, solders) that were
never actually installed there either — this app has only ever run ETH-only in practice.
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

import requests
from django.conf import settings
from eth_account import Account
from web3 import Web3
from web3.exceptions import Web3Exception

from .security import encrypt_private_key

logger = logging.getLogger(__name__)

RPC_MAX_ATTEMPTS = 3
RPC_BACKOFF_BASE_SECONDS = 0.5
RPC_RETRYABLE_EXCEPTIONS = (Web3Exception, requests.exceptions.RequestException, OSError, ValueError)

CHAIN_CURRENCIES = {
    "ETH": ("ETH", "USDT"),
    "TRON": ("TRX", "USDT"),
    "BTC": ("BTC",),
    "SOL": ("SOL",),
}


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
    chain_id: str

    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    def required_confirmations(self) -> int: ...

    @abstractmethod
    def create_wallet(self, currency: str) -> WalletCreationResult: ...

    @abstractmethod
    def check_payment(self, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None: ...

    @abstractmethod
    def get_confirmations(self, tx_hash: str) -> int: ...

    def supports_currency(self, currency: str) -> bool:
        return currency.upper() in self.supported_currencies()

    @abstractmethod
    def supported_currencies(self) -> tuple[str, ...]: ...


ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
        "name": "Transfer",
        "type": "event",
    },
]

USDT_DECIMALS = 6


class EthereumService(BaseChainService):
    chain_id = "ETH"

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL, request_kwargs={"timeout": 30}))
        self._usdt_contract = None
        self.last_error: str | None = None
        Account.enable_unaudited_hdwallet_features()

    def _with_retry(self, fn, *, attempts: int = RPC_MAX_ATTEMPTS, base_delay: float = RPC_BACKOFF_BASE_SECONDS):
        """Retry an RPC call with exponential backoff. Sets self.last_error on final
        failure instead of letting callers silently treat an outage as 'no result'."""
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                result = fn()
                self.last_error = None
                return result
            except RPC_RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(base_delay * (2**attempt))
        self.last_error = f"{type(last_exc).__name__}: {last_exc}"
        logger.warning("ETH RPC call failed after %s attempts: %s", attempts, self.last_error)
        raise last_exc

    @property
    def usdt_contract(self):
        if self._usdt_contract is None:
            self._usdt_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.USDT_CONTRACT_ADDRESS),
                abi=ERC20_ABI,
            )
        return self._usdt_contract

    def is_connected(self) -> bool:
        # w3.is_connected() swallows the underlying exception and returns a bare bool,
        # which is exactly the "silent failure" we don't want — call a real RPC method
        # instead so a network/timeout error surfaces through _with_retry into last_error.
        try:
            self._with_retry(lambda: self.w3.eth.chain_id)
            return True
        except RPC_RETRYABLE_EXCEPTIONS:
            return False

    def required_confirmations(self) -> int:
        return settings.ETH_REQUIRED_CONFIRMATIONS

    def supported_currencies(self) -> tuple[str, ...]:
        return ("ETH", "USDT")

    def create_wallet(self, currency: str) -> WalletCreationResult:
        account = Account.create()
        return WalletCreationResult(
            address=account.address,
            encrypted_private_key=encrypt_private_key(account.key.hex()),
            chain=self.chain_id,
            currency=currency.upper(),
        )

    def get_usdt_balance(self, address: str) -> Decimal:
        checksum = Web3.to_checksum_address(address)
        balance = self.usdt_contract.functions.balanceOf(checksum).call()
        return Decimal(balance) / Decimal(10**USDT_DECIMALS)

    def get_confirmations(self, tx_hash: str) -> int:
        try:
            receipt = self._with_retry(lambda: self.w3.eth.get_transaction_receipt(tx_hash))
            if not receipt or receipt.get("blockNumber") is None:
                return 0
            latest = self._with_retry(lambda: self.w3.eth.block_number)
            return max(0, latest - receipt["blockNumber"] + 1)
        except RPC_RETRYABLE_EXCEPTIONS:
            logger.warning("ETH confirmations failed for %s: %s", tx_hash, self.last_error)
            return 0
        except Exception:
            logger.exception("ETH confirmations failed for %s", tx_hash)
            return 0

    def find_incoming_eth_tx(self, address: str, min_amount_wei: int) -> tuple[str | None, str, int | None]:
        checksum = Web3.to_checksum_address(address)
        latest = self._with_retry(lambda: self.w3.eth.block_number)
        scan_blocks = min(settings.BLOCKCHAIN_SCAN_BLOCKS, latest)

        for block_num in range(latest, max(0, latest - scan_blocks), -1):
            block = self.w3.eth.get_block(block_num, full_transactions=True)
            for tx in block.transactions:
                to_addr = tx.get("to")
                if to_addr and to_addr.lower() == checksum.lower():
                    if tx.get("value", 0) >= min_amount_wei:
                        tx_hash = tx["hash"].hex() if hasattr(tx["hash"], "hex") else tx["hash"]
                        return tx_hash, tx.get("from", "unknown"), block_num
        return None, "unknown", None

    def find_incoming_usdt_tx(self, address: str, min_amount: Decimal) -> tuple[str | None, str, int | None]:
        checksum = Web3.to_checksum_address(address)
        min_units = int(min_amount * Decimal(10**USDT_DECIMALS))
        latest = self._with_retry(lambda: self.w3.eth.block_number)
        scan_blocks = min(settings.BLOCKCHAIN_SCAN_BLOCKS, latest)
        from_block = max(0, latest - scan_blocks)

        try:
            logs = self._with_retry(
                lambda: self.usdt_contract.events.Transfer.get_logs(
                    from_block=from_block,
                    to_block=latest,
                    argument_filters={"to": checksum},
                )
            )
        except Exception:
            logger.exception("USDT log scan failed for %s", address)
            return None, "unknown", None

        for log in reversed(logs):
            value = log["args"]["value"]
            if value >= min_units:
                tx_hash = log["transactionHash"].hex()
                block_number = log.get("blockNumber")
                return tx_hash, log["args"]["from"], block_number
        return None, "unknown", None

    def detect_incoming(self, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None:
        currency = currency.upper()
        min_amount = amount * Decimal("0.99")

        if currency == "ETH":
            min_wei = Web3.to_wei(float(min_amount), "ether")
            tx_hash, from_addr, block_num = self.find_incoming_eth_tx(address, int(min_wei))
        elif currency == "USDT":
            tx_hash, from_addr, block_num = self.find_incoming_usdt_tx(address, min_amount)
        else:
            return None

        if not tx_hash:
            return None

        confirmations = self.get_confirmations(tx_hash)
        return IncomingPaymentResult(
            tx_hash=tx_hash, from_address=from_addr, confirmations=confirmations, block_number=block_num
        )

    def check_payment(self, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None:
        detected = self.detect_incoming(address, amount, currency)
        if not detected:
            return None
        if detected.confirmations < self.required_confirmations():
            return None
        return detected
