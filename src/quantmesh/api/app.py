from fastapi import FastAPI

from quantmesh import __version__
from quantmesh.settings import settings

app = FastAPI(title=settings.app_name, version=__version__)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "project": settings.app_name,
        "version": __version__,
        "paper_mode": settings.default_paper_mode,
        "live_trading": settings.allow_live_trading,
    }

