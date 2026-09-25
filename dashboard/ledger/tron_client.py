"""Thin TronGrid HTTP client. The API key is only ever sent to *.trongrid.io hosts."""
from urllib.parse import urlparse

import httpx
from django.conf import settings

from . import tron


class TronAPIError(Exception):
    pass


def _auth_headers(base_url: str) -> dict:
    host = urlparse(base_url).hostname or ""
    if settings.TRONGRID_API_KEY and (host == "trongrid.io" or host.endswith(".trongrid.io")):
        return {"TRON-PRO-API-KEY": settings.TRONGRID_API_KEY}
    return {}


class TronClient:
    def __init__(self, base_url: str | None = None, transport=None):
        base = (base_url or settings.TRON_API_URL).rstrip("/")
        self.http = httpx.Client(
            base_url=base, headers=_auth_headers(base), timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=False, transport=transport,
        )

    def _json(self, response: httpx.Response) -> dict:
        if response.status_code != 200:
            raise TronAPIError(f"TronGrid returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise TronAPIError("TronGrid returned invalid JSON") from exc

    def _get(self, path, params=None) -> dict:
        try:
            return self._json(self.http.get(path, params=params))
        except httpx.HTTPError as exc:
            raise TronAPIError(str(exc)) from exc

    def _post(self, path, body) -> dict:
        try:
            return self._json(self.http.post(path, json=body))
        except httpx.HTTPError as exc:
            raise TronAPIError(str(exc)) from exc

    def trc20_transfers_to(self, address: str, min_timestamp_ms: int, max_pages: int = 5) -> list[dict]:
        """Irreversible (solidified) TRC-20 transfers into `address`, oldest first."""
        params = {
            "only_to": "true", "only_confirmed": "true", "limit": 200, "order_by": "block_timestamp,asc",
            "contract_address": settings.USDT_TRC20_CONTRACT, "min_timestamp": max(0, min_timestamp_ms),
        }
        items = []
        for _ in range(max_pages):
            page = self._get(f"/v1/accounts/{address}/transactions/trc20", params)
            items.extend(page.get("data") or [])
            fingerprint = (page.get("meta") or {}).get("fingerprint")
            if not fingerprint:
                return items
            params["fingerprint"] = fingerprint
        raise TronAPIError("too many pages of transfers; will resume next scan")

    def build_trc20_transfer(self, owner: str, contract: str, parameter_hex: str, fee_limit: int) -> dict:
        response = self._post("/wallet/triggersmartcontract", {
            "owner_address": tron.address_to_bytes(owner).hex(),
            "contract_address": tron.address_to_bytes(contract).hex(),
            "function_selector": "transfer(address,uint256)",
            "parameter": parameter_hex, "fee_limit": fee_limit, "call_value": 0, "visible": False,
        })
        if not (response.get("result") or {}).get("result") or "transaction" not in response:
            raise TronAPIError("TronGrid refused to build the transfer")
        return response["transaction"]

    def broadcast(self, signed_transaction: dict) -> dict:
        return self._post("/wallet/broadcasttransaction", signed_transaction)

    def solidified_transaction_info(self, tx_id: str) -> dict:
        """Empty dict until the transaction is irreversible."""
        return self._post("/walletsolidity/gettransactioninfobyid", {"value": tx_id})

    def transaction_on_full_node(self, tx_id: str) -> dict:
        return self._post("/wallet/gettransactionbyid", {"value": tx_id})
