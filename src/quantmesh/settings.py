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
    reports_dir: Path = Path.home() / ".quantmesh" / "reports"
    orders_dir: Path = Path.home() / ".quantmesh" / "orders"
    moomoo_opend_host: str = "127.0.0.1"
    moomoo_opend_port: int = Field(default=11111, ge=1, le=65535)
    moomoo_opend_connect_timeout_s: float = Field(default=5.0, gt=0)
    moomoo_opend_request_timeout_s: float = Field(default=10.0, gt=0)
    # Hyperliquid (M5): the testnet endpoint is pinned; a mainnet URL is
    # refused by the adapter before the wire (ADR-0007).
    hyperliquid_testnet_url: str = "https://api.hyperliquid-testnet.xyz"
    hyperliquid_connect_timeout_s: float = Field(default=5.0, gt=0)
    hyperliquid_request_timeout_s: float = Field(default=10.0, gt=0)
    # Polymarket (M6): public read-only endpoints, pinned, keyless
    # (ADR-0008). Overrides are explicit construction-time decisions,
    # never env-driven secret material.
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polymarket_request_timeout_s: float = Field(default=10.0, gt=0)
    # Kalshi (M6 Phase B): the public trade-api v2 host is pinned; the
    # migration host is refused at construction (ADR-0008).
    kalshi_base_url: str = "https://api.elections.kalshi.com/trade-api/v2"
    kalshi_request_timeout_s: float = Field(default=10.0, gt=0)
    # Cross-platform event mapping ledger (M6 Phase D, ADR-0008 decision
    # 5): append-only record of every mapping verdict.
    mappings_dir: Path = Path.home() / ".quantmesh" / "mappings"
    # Feature and model registries (M7 Phase A, ADR-0009): versioned
    # feature specs/sets and byte-addressed model artifacts on the M3
    # registry discipline.
    features_dir: Path = Path.home() / ".quantmesh" / "features"
    models_dir: Path = Path.home() / ".quantmesh" / "models"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="QUANTMESH_",
        extra="ignore",
    )


settings = Settings()

