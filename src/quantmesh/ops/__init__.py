"""Operational hardening (M10 Phase A, issue #58): metrics, structured
logs, reliability/drawdown limits with alert emission, signed audit
exports, and the secret-store seam.

The metrics store and the limit/alert evaluation are pure local
computation on the ADR-0006 discipline; the audit export is an
HMAC-signed bundle over the existing journals. Nothing here touches
the network, credentials (the keyring backend lands in Phase E behind
the KeyStore protocol), or any execution surface.
"""
