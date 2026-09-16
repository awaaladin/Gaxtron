"""Create a test payment against our own local API to get a real ETH deposit address."""
import json
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8002"
SCRIPT_DIR = Path(__file__).parent
API_KEY = (SCRIPT_DIR / "test_api_key.txt").read_text().strip()

OUT_FILE = SCRIPT_DIR / "sepolia_test_payment.json"


def main() -> None:
    resp = httpx.post(
        f"{BASE_URL}/create-payment",
        json={"amount": "0.005", "callback_url": "https://httpbin.org/post"},
        headers={"X-API-Key": API_KEY},
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    OUT_FILE.write_text(json.dumps(data, indent=2))

    print(f"Payment ID: {data['payment_id']}")
    print(f"Deposit address: {data['wallet_address']}")
    print(f"Amount: {data['amount']} {data['currency']}")
    print(f"Status: {data['status']}")


if __name__ == "__main__":
    main()
