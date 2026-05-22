"""Chain registry — currency matrix (no service imports)."""

CHAIN_CURRENCIES: dict[str, tuple[str, ...]] = {
    "ETH": ("ETH", "USDT"),
    "TRON": ("TRX", "USDT"),
    "BTC": ("BTC",),
    "SOL": ("SOL",),
}
