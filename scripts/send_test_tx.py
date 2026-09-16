"""Send a small ETH amount from the throwaway test wallet to our app's deposit address."""
import json
import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

ROOT = Path(__file__).parent.parent
SCRIPT_DIR = Path(__file__).parent
load_dotenv(ROOT / ".env")

SEND_AMOUNT_ETH = Decimal("0.005")


def main() -> None:
    wallet = json.loads((SCRIPT_DIR / "sepolia_test_wallet.json").read_text())
    payment = json.loads((SCRIPT_DIR / "sepolia_test_payment.json").read_text())

    from_address = wallet["address"]
    private_key = wallet["private_key"]
    to_address = payment["wallet_address"]

    rpc_url = os.environ["BLOCKCHAIN_RPC_URL"]
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise SystemExit("Could not connect to RPC")

    checksum_from = Web3.to_checksum_address(from_address)
    checksum_to = Web3.to_checksum_address(to_address)

    balance_wei = w3.eth.get_balance(checksum_from)
    send_wei = w3.to_wei(SEND_AMOUNT_ETH, "ether")

    gas_price = w3.eth.gas_price
    gas_limit = 21000
    gas_cost = gas_price * gas_limit

    if balance_wei < send_wei + gas_cost:
        raise SystemExit(
            f"Insufficient balance: have {w3.from_wei(balance_wei, 'ether')} ETH, "
            f"need {w3.from_wei(send_wei + gas_cost, 'ether')} ETH (incl. gas)"
        )

    tx = {
        "from": checksum_from,
        "to": checksum_to,
        "value": send_wei,
        "gas": gas_limit,
        "gasPrice": gas_price,
        "nonce": w3.eth.get_transaction_count(checksum_from),
        "chainId": w3.eth.chain_id,
    }

    signed = Account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hash_hex = tx_hash.hex()
    if not tx_hash_hex.startswith("0x"):
        tx_hash_hex = "0x" + tx_hash_hex

    print(f"From: {checksum_from}")
    print(f"To: {checksum_to}")
    print(f"Amount: {SEND_AMOUNT_ETH} ETH")
    print(f"Tx hash: {tx_hash_hex}")
    print(f"Explorer: https://sepolia.etherscan.io/tx/{tx_hash_hex}")


if __name__ == "__main__":
    main()
