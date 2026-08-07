from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "QuantMesh"
    environment: str = "local"
    allow_live_trading: bool = False
    default_paper_mode: bool = True
    lake_root: Path = Path.home() / ".quantmesh" / "data"
    experiments_dir: Path = Path.home() / ".quantmesh" / "experiments"
    moomoo_opend_host: str = "127.0.0.1"
    moomoo_opend_port: int = Field(default=11111, ge=1, le=65535)
    moomoo_opend_connect_timeout_s: float = Field(default=5.0, gt=0)
    moomoo_opend_request_timeout_s: float = Field(default=10.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="QUANTMESH_",
        extra="ignore",
    )


settings = Settings()

