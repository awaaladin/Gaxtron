"""
TRON adapter — TRX + TRC-20 USDT via tronpy.
"""
import logging
from decimal import Decimal

from app.chains.base import BaseChainService, IncomingPaymentResult, WalletCreationResult
from app.config import settings
from app.core.security import encrypt_private_key

logger = logging.getLogger(__name__)

TRC20_TRANSFER_SELECTOR = "a9059cbb"  # transfer(address,uint256)


class TronService(BaseChainService):
    chain_id = "TRON"

    def __init__(self):
        self._client = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            from tronpy import Tron
            from tronpy.providers import HTTPProvider

            network = settings.tron_network
            if settings.tron_api_url:
                provider = HTTPProvider(settings.tron_api_url)
                self._client = Tron(provider=provider, network=network)
            else:
                self._client = Tron(network=network)
        except Exception:
            logger.exception("TronPy client init failed")
            self._client = None

    def is_connected(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.get_latest_block_number()
            return True
        except Exception:
            return False

    def required_confirmations(self) -> int:
        return settings.tron_required_confirmations

    def supported_currencies(self) -> tuple[str, ...]:
        return ("TRX", "USDT")

    def create_wallet(self, currency: str) -> WalletCreationResult:
        if not self._client:
            raise RuntimeError("TRON client unavailable")
        wallet = self._client.generate_address()
        priv = wallet.get("private_key")
        if hasattr(priv, "hex"):
            secret = priv.hex()
        else:
            secret = str(priv)
        return WalletCreationResult(
            address=wallet["base58check_address"],
            encrypted_private_key=encrypt_private_key(secret),
            chain=self.chain_id,
            currency=currency.upper(),
        )

    def get_confirmations(self, tx_hash: str) -> int:
        if not self._client:
            return 0
        try:
            info = self._client.get_transaction_info(tx_hash)
            block = info.get("blockNumber")
            if not block:
                return 0
            latest = self._client.get_latest_block_number()
            return max(0, latest - block + 1)
        except Exception:
            return 0

    def _check_trx(self, address: str, min_sun: int) -> tuple[str | None, str]:
        if not self._client:
            return None, "unknown"
        try:
            acct = self._client.get_account(address)
            balance = acct.get("balance", 0)
            if balance >= min_sun:
                # Scan recent txs to address
                txs = self._client.get_account_transactions(address, only_to=True, limit=20)
                for tx in txs:
                    txid = tx.get("txID") or tx.get("txid")
                    if txid:
                        return txid, tx.get("raw_data", {}).get("contract", [{}])[0].get("parameter", {}).get("value", {}).get("owner_address", "unknown")
        except Exception:
            logger.exception("TRX check failed for %s", address)
        return None, "unknown"

    def _check_trc20_usdt(self, address: str, min_amount: Decimal) -> tuple[str | None, str]:
        if not self._client:
            return None, "unknown"
        try:
            contract = self._client.get_contract(settings.tron_usdt_contract)
            balance = contract.functions.balanceOf(address)
            min_units = int(min_amount * Decimal(10**6))
            if int(balance) < min_units:
                return None, "unknown"
            # TRC20 transfers via account resource / events — use tronpy contract events
            events = contract.events.Transfer.scan(min_block_timestamp=0, limit=50)
            for ev in reversed(list(events)):
                if ev.get("result", {}).get("to", "").lower() == address.lower():
                    val = int(ev["result"].get("value", 0))
                    if val >= min_units:
                        return ev.get("transaction_id") or ev.get("transaction"), ev["result"].get("from", "unknown")
        except Exception:
            logger.exception("TRC20 USDT check failed for %s", address)
        return None, "unknown"

    def check_payment(self, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None:
        if not self._client:
            return None
        currency = currency.upper()
        min_amount = amount * Decimal("0.99")

        if currency == "TRX":
            min_sun = int(min_amount * Decimal(1_000_000))
            tx_hash, from_addr = self._check_trx(address, min_sun)
        elif currency == "USDT":
            tx_hash, from_addr = self._check_trc20_usdt(address, min_amount)
        else:
            return None

        if not tx_hash:
            return None

        confirmations = self.get_confirmations(tx_hash)
        if confirmations < self.required_confirmations():
            return None

        return IncomingPaymentResult(
            tx_hash=tx_hash,
            from_address=from_addr,
            confirmations=confirmations,
        )
