"""

Backward-compatible facade — delegates to EthereumService.

New code should use PaymentProcessor + chain adapters.

"""

from decimal import Decimal



from app.chains.ethereum_service import EthereumService





class BlockchainService:

    def __init__(self):

        self._eth = EthereumService()



    @property

    def w3(self):

        return self._eth.w3



    @property

    def required_confirmations(self) -> int:

        return self._eth.required_confirmations()



    @property

    def is_connected(self) -> bool:

        return self._eth.is_connected()



    def get_confirmations(self, tx_hash: str) -> int:

        return self._eth.get_confirmations(tx_hash)



    def get_tx_from_address(self, tx_hash: str) -> str:

        return self._eth._tx_from(tx_hash)



    def get_eth_balance(self, address: str) -> Decimal:

        checksum = self._eth.w3.to_checksum_address(address)

        wei = self._eth.w3.eth.get_balance(checksum)

        return Decimal(str(self._eth.w3.from_wei(wei, "ether")))



    def get_usdt_balance(self, address: str) -> Decimal:

        return self._eth.get_usdt_balance(address) if hasattr(self._eth, "get_usdt_balance") else Decimal(0)



    def find_incoming_eth_tx(self, address: str, min_amount_wei: int) -> tuple[str | None, str]:

        tx_hash, from_addr, _ = self._eth.find_incoming_eth_tx(address, min_amount_wei)

        return tx_hash, from_addr



    def find_incoming_usdt_tx(self, address: str, min_amount: Decimal) -> tuple[str | None, str]:

        tx_hash, from_addr, _ = self._eth.find_incoming_usdt_tx(address, min_amount)

        return tx_hash, from_addr



    def is_tx_confirmed(self, tx_hash: str) -> bool:

        return self._eth.get_confirmations(tx_hash) >= self._eth.required_confirmations()


