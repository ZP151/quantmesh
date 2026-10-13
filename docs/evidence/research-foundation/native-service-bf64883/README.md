# Current native Linux offline service boundary

Exact root candidate bf64883f0a18e3d4e1e07c83522cbc41276abf7e passes the
complete independent offline service gate on a new owned native checkout:
137 tests pass, 5 PostgreSQL-specific cases skip, 142 collected, gate exit 0.
All 81 pinned packages have licensed metadata. Unmodified dependency admission
before and after execution verifies 6,669 RECORD files and zero bytecode files.
The new child -B/environment fix is exercised by the complete service boundary.

This is OFFLINE_SCRIPTED_ONLY. No paid/real model call, production source,
PostgreSQL deployment, whole-project CI or production release is certified.
The separate b107 failed service gate remains in the accounting/repair archives;
its original credential-output unavailable category is not retrospectively
diagnosed by this fresh pass. Previous contaminated environments were preserved,
not cleaned. This fresh runtime used cached exact-lock wheel bytes, no network.

All top-level gate receipts and raw stdout/stderr/exit streams are copied
byte-for-byte and hash-bound. Private pytest fixture directories are excluded.
