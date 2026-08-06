class HyperliquidConnector:
    """Adapter boundary for the official Hyperliquid Python SDK."""

    venue = "hyperliquid"

    def __init__(self, testnet: bool = True) -> None:
        self.testnet = testnet

    async def get_quotes(self, instruments):
        raise NotImplementedError("Hyperliquid market data adapter is planned for iteration 2")

    async def place_order(self, order):
        raise NotImplementedError("Hyperliquid execution requires explicit risk approval")

