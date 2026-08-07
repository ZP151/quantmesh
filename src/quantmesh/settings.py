from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "QuantMesh"
    environment: str = "local"
    allow_live_trading: bool = False
    default_paper_mode: bool = True
    lake_root: Path = Path.home() / ".quantmesh" / "data"
    experiments_dir: Path = Path.home() / ".quantmesh" / "experiments"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="QUANTMESH_",
        extra="ignore",
    )


settings = Settings()

