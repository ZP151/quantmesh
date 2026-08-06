class PolymarketConnector:
    """Read-only boundary for prediction-market discovery and CLOB data."""

    venue = "polymarket"

    async def get_markets(self):
        raise NotImplementedError("Polymarket discovery adapter is planned for iteration 3")

