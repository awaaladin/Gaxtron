"""Check the Sepolia test wallet's balance via our configured BLOCKCHAIN_RPC_URL."""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

WALLET_FILE = Path(__file__).parent / "sepolia_test_wallet.json"


def main() -> None:
    wallet = json.loads(WALLET_FILE.read_text())
    address = wallet["address"]

    rpc_url = os.environ["BLOCKCHAIN_RPC_URL"]
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))

    if not w3.is_connected():
        raise SystemExit(f"Could not connect to RPC")

    chain_id = w3.eth.chain_id
    balance_wei = w3.eth.get_balance(Web3.to_checksum_address(address))
    balance_eth = Web3.from_wei(balance_wei, "ether")

    print(f"Chain ID: {chain_id}")
    print(f"Address: {address}")
    print(f"Balance: {balance_eth} ETH")


if __name__ == "__main__":
    main()
