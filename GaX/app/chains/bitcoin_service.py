"""
Bitcoin adapter — Blockstream (or compatible) REST API for address monitoring.
"""
import logging
from decimal import Decimal

import httpx

from app.chains.base import BaseChainService, IncomingPaymentResult, WalletCreationResult
from app.config import settings
from app.core.security import encrypt_private_key

logger = logging.getLogger(__name__)


class BitcoinService(BaseChainService):
    chain_id = "BTC"

    def __init__(self):
        self.api_base = settings.bitcoin_api_url.rstrip("/")
        self._http = httpx.Client(timeout=30.0)

    def is_connected(self) -> bool:
        try:
            r = self._http.get(f"{self.api_base}/blocks/tip/height")
            return r.status_code == 200
        except Exception:
            return False

    def required_confirmations(self) -> int:
        return settings.btc_required_confirmations

    def supported_currencies(self) -> tuple[str, ...]:
        return ("BTC",)

    def create_wallet(self, currency: str) -> WalletCreationResult:
        try:
            from bitcoinlib.keys import Key

            key = Key(network=settings.bitcoin_network)
            wif = key.wif()
            address = key.address()
        except ImportError:
            # Fallback: derive via bitcoinlib alternative or raise
            raise RuntimeError("bitcoinlib required for BTC wallet generation: pip install bitcoinlib")

        return WalletCreationResult(
            address=address,
            encrypted_private_key=encrypt_private_key(wif),
            chain=self.chain_id,
            currency="BTC",
        )

    def get_confirmations(self, tx_hash: str) -> int:
        try:
            r = self._http.get(f"{self.api_base}/tx/{tx_hash}")
            if r.status_code != 200:
                return 0
            data = r.json()
            status = data.get("status", {})
            if not status.get("confirmed"):
                return 0
            tip = int(self._http.get(f"{self.api_base}/blocks/tip/height").json())
            block_height = status.get("block_height", 0)
            return max(0, tip - block_height + 1)
        except Exception:
            return 0

    def check_payment(self, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None:
        if currency.upper() != "BTC":
            return None
        min_sats = int(amount * Decimal("0.99") * Decimal(100_000_000))

        try:
            r = self._http.get(f"{self.api_base}/address/{address}/txs")
            if r.status_code != 200:
                return None
            txs = r.json()
        except Exception:
            logger.exception("BTC address scan failed for %s", address)
            return None

        for tx in txs:
            txid = tx.get("txid")
            status = tx.get("status", {})
            received = 0
            for vout in tx.get("vout", []):
                if vout.get("scriptpubkey_address") == address:
                    received += int(vout.get("value", 0))
            if received < min_sats:
                continue
            confirmations = 0
            if status.get("confirmed"):
                tip = int(self._http.get(f"{self.api_base}/blocks/tip/height").json())
                confirmations = max(0, tip - status.get("block_height", 0) + 1)
            if confirmations < self.required_confirmations():
                continue
            from_addr = "unknown"
            for vin in tx.get("vin", []):
                prev = vin.get("prevout", {})
                if prev.get("scriptpubkey_address"):
                    from_addr = prev["scriptpubkey_address"]
                    break
            return IncomingPaymentResult(
                tx_hash=txid,
                from_address=from_addr,
                confirmations=confirmations,
                block_number=status.get("block_height"),
            )
        return None
