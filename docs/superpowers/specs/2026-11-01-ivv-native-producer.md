# IVV native producer — feasibility first

Issue: https://github.com/ZP151/quantmesh/issues/272 (parent #259).

## Outcome and authority

One operator action invokes the bounded producer check and obtains actual provider feasibility or one exact native failed predicate. The current milestone never issues a permit, creates an intent, imports the SDK or starts capture. The operator-approved original IVV integration now explicitly includes this missing producer port. Existing eabdda service/login remains untouched; c8 admission is not transferable.

## Invariants

- Retain the published capture helper bytes (56154 / 8fa613a6...), exact 21 plan keys, five provider_actor fields, 1..8 evidence refs, original seven sends, irreversible once and 480-second capture wall.
- Check the approved fixed host, unit/Invocation, three PID/start/UID/executable/cgroup/namespace relationships and listener ownership against native metadata. No replacement PID, guessed loaded launcher provenance or current-global-file-equals-loaded-code assumption.
- Provider feasibility needs an actual protected finite <=32MiB enforcer, readonly namespace and exactly the HOME, STATE, matching RUNTIME, /tmp, /var/tmp and /dev/shm write roles, protected lower/upper/work identities and no writable escape. Mount visibility, a c8 image, pidfd or serialized claim alone never suffices. Unestablished open writable channels remain insufficient.
- Metadata reads use held/named identity and post-read lifetime checks. Never read XML, credentials, account files, environment, provider argv, terminal/log content or FD payload; do not persist private paths, peer addresses or secret-derived hashes.
- The check is standard-library-only, bounded and read-only. It closes its own FDs/query children; it never stops, changes, attaches or mounts anything in the existing provider.
- FEASIBILITY_ONLY is not technical SDK admission. Trusted config, actual readonly Linux SDK 10.10.7008 and >=12 pins, capture actor 512MiB/swap0/CPU50%/Tasks32, Root permit and normal parent closure remain separate required gates.

## Interface and sequence

tools/research/ivv_native_producer.py exposes check_existing_provider() and --check. Native collection is the only CLI source of facts; pure evaluation supports local tests and is not a JSON attestation interface. Output is a closed safe schema containing feasibility-only state, first failed predicate, selected non-secret facts and owned-FD closure. No signing/SDK branch exists in Phase A.

Validate identity, namespace and actual writable graph/enforcer first. Stop at the first real mismatch or unavailable mandatory proof. Only if this provider can satisfy the existing boundary may Phase B implement trusted configuration/runtime/capture-actor and derived held-permit integration. Native evidence before publication is feasibility evidence only.

## Limits and acceptance

TDD plus fresh independent R1, at most one known-fix R2. Parent whole code/privacy/physical review precedes at most one bounded native feasibility invocation. No per-field SSH loop or readiness-only platform. First native infeasibility stops dependent issuer engineering and yields one minimal disposition. Target first verifiable increment within two hours; CI wall is recorded separately.

New code must receive exact source review/CI/normal publication/catalog before production issuance. No OOS, profitability, Paper/live, data/math, dependency, environment or provider-rights change.
