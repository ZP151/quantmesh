"""Live Market Cockpit runtime (iteration 0015, ADR-0014).

Venue streams normalize into the owned ``MarketUpdate`` contract
(``contract.py``), are appended to the replay lake (``buffer.py``) and
are later published over the local feed and gated by the quote fence.
Everything here is read-only with respect to external venues and never
touches credentials.
"""
