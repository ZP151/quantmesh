class MoomooConnector:
    """Adapter boundary for the official moomoo OpenAPI package."""

    venue = "moomoo"

    def __init__(self, paper: bool = True) -> None:
        self.paper = paper

    async def get_quotes(self, instruments):
        raise NotImplementedError("Moomoo adapter will be enabled in the next iteration")

    async def place_order(self, order):
        raise NotImplementedError("Moomoo order routing will be enabled after paper tests")

