"""One-off helper: generate a throwaway Ethereum keypair for manual Sepolia testing.

Writes the private key to scripts/sepolia_test_wallet.json (gitignored) and prints
only the public address to stdout. Re-run refuses to overwrite an existing wallet
file so you don't silently orphan funds already sent to the old address.
"""
import json
import sys
from pathlib import Path

from eth_account import Account

WALLET_FILE = Path(__file__).parent / "sepolia_test_wallet.json"


def main() -> None:
    if WALLET_FILE.exists():
        data = json.loads(WALLET_FILE.read_text())
        print(f"Wallet already exists at {WALLET_FILE}", file=sys.stderr)
        print(f"Address: {data['address']}")
        return

    account = Account.create()
    WALLET_FILE.write_text(json.dumps({"address": account.address, "private_key": account.key.hex()}, indent=2))

    print(f"Address: {account.address}")


if __name__ == "__main__":
    main()
