"""
Ethereum adapter — native ETH + ERC-20 USDT via web3.py.
"""
import logging
from decimal import Decimal

from eth_account import Account
from web3 import Web3
from web3.exceptions import Web3Exception

from app.chains.base import BaseChainService, IncomingPaymentResult, WalletCreationResult
from app.config import settings
from app.core.security import encrypt_private_key

logger = logging.getLogger(__name__)

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
        self.w3 = Web3(Web3.HTTPProvider(settings.blockchain_rpc_url, request_kwargs={"timeout": 30}))
        self._usdt_contract = None
        Account.enable_unaudited_hdwallet_features()

    @property
    def usdt_contract(self):
        if self._usdt_contract is None:
            self._usdt_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.usdt_contract_address),
                abi=ERC20_ABI,
            )
        return self._usdt_contract

    def is_connected(self) -> bool:
        try:
            return self.w3.is_connected()
        except Web3Exception:
            return False

    def required_confirmations(self) -> int:
        return getattr(settings, "eth_required_confirmations", settings.required_confirmations)

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
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if not receipt or receipt.get("blockNumber") is None:
                return 0
            latest = self.w3.eth.block_number
            return max(0, latest - receipt["blockNumber"] + 1)
        except Exception:
            logger.exception("ETH confirmations failed for %s", tx_hash)
            return 0

    def _tx_from(self, tx_hash: str) -> str:
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            return tx.get("from", "unknown") if tx else "unknown"
        except Exception:
            return "unknown"

    def find_incoming_eth_tx(self, address: str, min_amount_wei: int) -> tuple[str | None, str, int | None]:
        checksum = Web3.to_checksum_address(address)
        latest = self.w3.eth.block_number
        scan_blocks = min(settings.blockchain_scan_blocks, latest)

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
        latest = self.w3.eth.block_number
        scan_blocks = min(settings.blockchain_scan_blocks, latest)
        from_block = max(0, latest - scan_blocks)

        try:
            logs = self.usdt_contract.events.Transfer.get_logs(
                from_block=from_block,
                to_block=latest,
                argument_filters={"to": checksum},
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
        """Find matching tx on Sepolia (any confirmation count)."""
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
            tx_hash=tx_hash,
            from_address=from_addr,
            confirmations=confirmations,
            block_number=block_num,
        )

    def check_payment(self, address: str, amount: Decimal, currency: str) -> IncomingPaymentResult | None:
        detected = self.detect_incoming(address, amount, currency)
        if not detected:
            return None
        if detected.confirmations < self.required_confirmations():
            logger.debug(
                "ETH %s: %s/%s confirmations",
                address,
                detected.confirmations,
                self.required_confirmations(),
            )
            return None
        return detected
