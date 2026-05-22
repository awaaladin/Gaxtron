#!/usr/bin/env python3
"""
End-to-end merchant onboarding flow for Gaxtron.

Steps:
  1. Register merchant (JWT)
  2. Create API key (JWT)
  3. Create payment (API key)
  4. Verify payment (API key)
  5. Print dashboard URL

Usage:
  python scripts/merchant_flow.py
  python scripts/merchant_flow.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    sys.exit(1)

DEFAULT_BASE = "http://localhost:8000"
MERCHANT_EMAIL = f"merchant_{uuid.uuid4().hex[:8]}@gaxtron.dev"
MERCHANT_USER = "demo_merchant"
MERCHANT_PASS = "SecureMerchantP@ss1"
CALLBACK_URL = "https://httpbin.org/post"


def step(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Gaxtron merchant API flow")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--email", default=MERCHANT_EMAIL)
    parser.add_argument("--username", default=MERCHANT_USER)
    parser.add_argument("--password", default=MERCHANT_PASS)
    parser.add_argument("--callback-url", default=CALLBACK_URL)
    parser.add_argument("--amount", default="0.001")
    parser.add_argument("--currency", choices=["ETH", "USDT"], default="ETH")
    parser.add_argument("--sync-dashboard", action="store_true", help="Create Django login for same email")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(base_url=base, timeout=30.0) as client:
        # Health check
        step("0. Health check")
        try:
            r = client.get("/health")
            r.raise_for_status()
            print(json.dumps(r.json(), indent=2))
        except httpx.HTTPError as e:
            print(f"API not reachable at {base}: {e}")
            print("Start stack: docker compose up -d && cd GaX && uvicorn app.main:app --port 8000")
            return 1

        # 1. Register
        step("1. Register merchant -> JWT")
        r = client.post(
            "/auth/register",
            json={
                "email": args.email,
                "username": args.username,
                "password": args.password,
            },
        )
        if r.status_code == 400 and "already" in r.text.lower():
            print("User exists, logging in instead...")
            r = client.post(
                "/auth/login",
                data={"username": args.email, "password": args.password},
            )
        r.raise_for_status()
        token = r.json()["access_token"]
        print(f"  email:    {args.email}")
        print(f"  username: {args.username}")
        print(f"  JWT:      {token[:40]}...")

        headers_jwt = {"Authorization": f"Bearer {token}"}

        # 2. Me
        step("2. Verify JWT - GET /auth/me")
        r = client.get("/auth/me", headers=headers_jwt)
        r.raise_for_status()
        me = r.json()
        print(json.dumps(me, indent=2))

        # 3. API key
        step("3. Create API key (JWT only)")
        r = client.post("/api-keys", headers=headers_jwt, json={"name": "production-key"})
        r.raise_for_status()
        key_data = r.json()
        api_key = key_data["api_key"]
        print(f"  key_prefix: {key_data['key_prefix']}")
        print(f"  API KEY (save now): {api_key}")

        headers_api = {"X-API-Key": api_key}

        # 4. Create payment
        step("4. Create payment (API key only)")
        idem = f"idem_{uuid.uuid4().hex}"
        r = client.post(
            "/create-payment",
            headers=headers_api,
            json={
                "amount": args.amount,
                "currency": args.currency,
                "callback_url": args.callback_url,
                "idempotency_key": idem,
            },
        )
        r.raise_for_status()
        payment = r.json()
        payment_id = payment["id"]
        print(json.dumps(payment, indent=2, default=str))
        print(f"\n  >> Send {args.amount} {args.currency} to:")
        print(f"     {payment['wallet_address']}")

        # 5. Idempotent retry
        step("5. Idempotency - same key returns same payment")
        r = client.post(
            "/create-payment",
            headers=headers_api,
            json={
                "amount": args.amount,
                "currency": args.currency,
                "callback_url": args.callback_url,
                "idempotency_key": idem,
            },
        )
        r.raise_for_status()
        payment2 = r.json()
        assert payment2["id"] == payment_id, "Idempotency failed"
        print(f"  Same payment id: {payment2['id']} OK")

        # 6. Verify payment
        step("6. Verify payment status")
        r = client.get(f"/verify-payment/{payment_id}", headers=headers_api)
        r.raise_for_status()
        verify = r.json()
        print(json.dumps(verify, indent=2, default=str))

        # 7. List API keys (prefix only)
        step("7. List API keys (no secret exposed)")
        r = client.get("/api-keys", headers=headers_jwt)
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2, default=str))

    if args.sync_dashboard:
        step("8. Sync Django dashboard login")
        import subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        dashboard = root / "dashboard"
        cmd = [
            sys.executable,
            "manage.py",
            "sync_merchant",
            "--email",
            args.email,
            "--username",
            args.username,
            "--password",
            args.password,
        ]
        import os
        env = {**os.environ}
        try:
            from dotenv import load_dotenv
            load_dotenv(root / ".env")
        except ImportError:
            pass
        # Use same DB as API when running local SQLite flow
        sqlite_path = root / "GaX" / "gaxtron_dev.db"
        if sqlite_path.exists():
            env["DATABASE_URL"] = f"sqlite:///{sqlite_path.resolve().as_posix()}"
        subprocess.run(
            [sys.executable, "manage.py", "migrate", "--run-syncdb"],
            cwd=dashboard,
            env=env,
            capture_output=True,
        )
        result = subprocess.run(cmd, cwd=dashboard, env=env, capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout.strip())
            print("  Dashboard login ready OK")
        else:
            print("  Dashboard sync failed:")
            if result.stderr:
                print(result.stderr.strip()[:500])
            print(f"  Manual: cd dashboard && python manage.py migrate && python manage.py sync_merchant --email {args.email} --username {args.username} --password <password>")

    step("Flow complete")
    print(f"""
  Merchant credentials (save these):
    Email:    {args.email}
    Password: {args.password}
    API Key:  {api_key}

  Dashboard:  http://localhost:8001/login/
    Login with the email and password above.

  API docs:   {base}/docs
  Payment ID: {payment_id}
  Status:     {verify['status']} (worker confirms after on-chain payment)
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
