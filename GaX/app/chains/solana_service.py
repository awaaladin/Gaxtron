"""
Solana adapter — native SOL via JSON-RPC (solana-py when available).
"""
import logging
from decimal import Decimal

import httpx

from app.chains.base import BaseChainService, IncomingPaymentResult, WalletCreationResult
from app.config import settings
from app.core.security import encrypt_private_key

logger = logging.getLogger(__name__)

LAMPORTS_PER_SOL = 1_000_000_000


class SolanaService(BaseChainService):
    chain_id = "SOL"

    def __init__(self):
        self.rpc_url = settings.solana_rpc_url
        self._http = httpx.Client(timeout=30.0)

    def _rpc(self, method: str, params: list) -> dict | None:
        try:
            r = self._http.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                logger.warning("Solana RPC error: %s", body["error"])
                return None
            return body.get("result")
        except Exception:
            logger.exception("Solana RPC %s failed", method)
            return None

    def is_connected(self) -> bool:
        result = self._rpc("getHealth", [])
        return result == "ok" or result is not None

    def required_confirmations(self) -> int:
        return settings.sol_required_confirmations

    def supported_currencies(self) -> tuple[str, ...]:
        return ("SOL",)

    def create_wallet(self, currency: str) -> WalletCreationResult:
        try:
            from solders.keypair import Keypair

            kp = Keypair()
            address = str(kp.pubkey())
            secret = bytes(kp).hex()
        except ImportError:
            try:
                from solana.keypair import Keypair

                kp = Keypair()
                address = str(kp.public_key)
                secret = kp.secret_key.hex()
            except ImportError as e:
                raise RuntimeError("Install solana or solders: pip install solana solders") from e

        return WalletCreationResult(
            address=address,
            encrypted_private_key=encrypt_private_key(secret),
            chain=self.chain_id,
            currency="SOL",
        )

    def get_confirmations(self, tx_hash: str) -> int:
        result = self._rpc("getSignatureStatuses", [[tx_hash], {"searchTransactionHistory": True}])
        if not result or not result.get("value"):
            return 0
        status = result["value"][0]
        if not status:
            return 0
        conf = status.get("confirmations")
        if conf is None and status.get("confirmationStatus") == "finalized":
            return self.required_confirmations()
        return conf or 0

    def check_payment(self, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None:
        if currency.upper() != "SOL":
            return None
        min_lamports = int(amount * Decimal("0.99") * LAMPORTS_PER_SOL)

        balance_result = self._rpc("getBalance", [address])
        if balance_result is None:
            return None
        lamports = balance_result.get("value", 0)
        if lamports < min_lamports:
            return None

        sigs = self._rpc("getSignaturesForAddress", [address, {"limit": 20}])
        if not sigs:
            return None

        for sig_info in sigs:
            tx_sig = sig_info.get("signature")
            if not tx_sig:
                continue
            tx = self._rpc("getTransaction", [tx_sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
            if not tx:
                continue
            meta = tx.get("meta", {})
            if meta.get("err"):
                continue
            # Verify this tx credited our address
            post = meta.get("postBalances", [])
            pre = meta.get("preBalances", [])
            account_keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
            for i, key in enumerate(account_keys):
                key_str = key if isinstance(key, str) else key.get("pubkey", "")
                if key_str == address and i < len(post) and i < len(pre):
                    delta = post[i] - pre[i]
                    if delta >= min_lamports:
                        confirmations = self.get_confirmations(tx_sig)
                        if confirmations >= self.required_confirmations():
                            return IncomingPaymentResult(
                                tx_hash=tx_sig,
                                from_address="unknown",
                                confirmations=confirmations,
                                block_number=tx.get("slot"),
                            )
        return None
