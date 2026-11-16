# Minimal beta research accounts

Issue [309](https://github.com/ZP151/quantmesh/issues/309). Actual human parallel-product authority is recorded by the coordinator as SHA-256 `8b0e81425f882157327dcbb8032295ca3c9ee709224e69d6efcbe90c0952a709`. Ordinary bounded implementation is authorized; no actual invitations, service cutover or public exposure is inferred.

## One user loop

An Operator creates one manually delivered invitation, a tester exchanges it for a session, opens only their own fixed Native research, and immediately loses further access when the Operator revokes the account. A cannot enumerate, read by known ID, download or change B's research or decisions. Existing unowned records stay in the original Operator store; no automatic adoption or sharing.

## Existing system and approach

The private research service already uses SecretStr, a fixed Operator identity and constant-time Bearer authentication. The desktop has loopback/Origin guards, not an individual account model. Reuse that authentication pattern, Python secrets/hashlib/SQLite, the existing WriterLease and the existing NativeDailyService unchanged. Do not add passwords, SSO, email delivery or a generic identity platform.

The new mode is explicit construction-time opt-in on create_workstation_app. The existing personal mode remains byte-compatible in behavior and is not remotely exposed or restarted. The initial backend slice requires an injected Operator Native service and BetaAccess registry. Actual activation and external recipients/deployment remain separately controlled; there is no implicit migration or new host.

## Minimal contract

- POST `/api/beta/users` (Operator): `{display_name}` creates a tester with a server UUID and returns its public record plus a single-use invitation `{token, expires_at}`. No email/address or client-selected ID/role/root.
- GET `/api/beta/users` (Operator): public user records only, never credentials/digests.
- POST `/api/beta/users/{user_id}/revoke` (Operator): permanently revoke this tester and its unused invitation/all sessions. Operator cannot revoke itself through this endpoint.
- POST `/api/beta/sessions`: body `{invitation_token}` exchanges the code; alternatively empty body plus configured Operator Bearer creates an Operator session. Mixed credentials are refused. Returns `{user, expires_at}` and sets `qm_beta_session`, HttpOnly/SameSite=Strict/path=/, Secure on HTTPS. Neither session secret nor bootstrap secret appears in JSON.
- GET `/api/beta/me`: current public identity and session expiry. DELETE `/api/beta/session`: invalidate only the authenticated cookie/Bearer session and expire the cookie. A bootstrap Operator Bearer is not a logout-able session.
- Missing/invalid/expired/revoked credentials:401 `unauthorized`; wrong role/capability:403 `forbidden`; unknown resource:404 `not_found`; capacity/consumed invitation conflict:409; bad payload:422 `invalid_request`; unavailable auth store:503 `auth_unavailable`. Responses carrying identity or errors are private/no-store.
- Existing `/api/research/native-daily` request/response and artifact contracts do not change. Server-resolved principal selects a separate Native store under the configured beta root, never a browser path/owner field. Default new tester roots have no input registration. Research entitlement/data admission/trial rules are still the existing ones; an account is not a data grant.

Invitations last24h, sessions8h; limits32 tester accounts and256 retained sessions. Hash credentials at rest, retain revoked records, and fail rather than silently evict them. Persistence uses one process lease and atomic SQLite transactions. Every research operation revalidates the session/account under the registry lock; revoke linearizes with those operations and returns only after earlier guarded work finishes. It does not interrupt or refund a research trial.

## Full surface boundary

In enabled mode, unauthenticated requests may get the packaged SPA/static resources and submit the session exchange only. Tester capability is current-user/logout plus its own Native research routes. Other APIs, legacy aliases, raw registries, trading/provider/model actions and all tester WebSockets are denied, including known IDs. Operator retains the original store and routes after authentication. Cookie writes require an exact allowed same Origin, not merely any localhost port; Bearer CLI writes may omit Origin. Never weaken the existing personal-mode Origin checks.

## Scope, files and risks

Product alone owns new `auth/beta.py`, `api/beta_access.py`, Native API authority integration, optional workstation assembly and backend tests/docs. UX alone owns every frontend/generated-client/locale path. No current service, protected root,8878/18956/64462, real input, SDK, payment or real invitation is touched.

This is local/private application-level separation, not an OS sandbox against a local filesystem owner. Per-user stores intentionally avoid cross-user artifact rewriting and shared grant migration. Other workstation surfaces are Operator-only for this slice, and real inputs require separate per-user trusted registration and rights review. Test-only construction factories may supply synthetic services; HTTP never selects such factories. Browser UI and deployment are not backend acceptance claims.

Tests must prove real app/router A/B isolation, legacy Operator access, one-time invitation races, expiry/revoke/logout/cold reopening, authentication bypass refusal across legacy/API/WS routes, cookie CSRF, and absence of plaintext credentials in stored files. Existing Native math and report bytes are reused; no old numerical matrix or real financial trial is rerun for this account feature.
