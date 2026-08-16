"""Canonical provider identities for Hyperliquid public microstructure."""

from __future__ import annotations

import hashlib
import json
from typing import Literal


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def trade_source_event_id(block_time_ms: int, coin: str, tid: int) -> str:
    """SHA-256 over canonical ``(block_time, coin, tid)`` provider identity."""
    if isinstance(block_time_ms, bool) or not isinstance(block_time_ms, int):
        raise ValueError("block_time_ms must be an integer")
    if isinstance(tid, bool) or not isinstance(tid, int):
        raise ValueError("tid must be an integer")
    if not isinstance(coin, str) or not coin.strip():
        raise ValueError("coin must be nonblank")
    return _digest([block_time_ms, coin.upper(), tid])


def book_snapshot_epoch(
    block_time_ms: int,
    coin: str,
    bids: list[list[float]],
    asks: list[list[float]],
) -> str:
    """Identity of one complete full-book frame, never a synthetic delta."""
    if isinstance(block_time_ms, bool) or not isinstance(block_time_ms, int):
        raise ValueError("block_time_ms must be an integer")
    if not isinstance(coin, str) or not coin.strip():
        raise ValueError("coin must be nonblank")
    return _digest(
        [
            "hyperliquid-book-epoch-v1",
            coin.upper(),
            block_time_ms,
            bids,
            asks,
        ]
    )


def book_side_source_event_id(
    snapshot_epoch: str, side: Literal["bid", "ask"]
) -> str:
    if not isinstance(snapshot_epoch, str) or not snapshot_epoch:
        raise ValueError("snapshot_epoch must be nonblank")
    if side not in ("bid", "ask"):
        raise ValueError("book side must be bid or ask")
    return _digest([snapshot_epoch, side])
