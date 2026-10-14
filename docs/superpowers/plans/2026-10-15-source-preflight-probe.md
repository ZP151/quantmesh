# Actual source-preflight probe on the prepared Worker image

This is a root-review draft for one source-only qualification step in iteration
0038. It does not qualify native loading, the Worker, numerical outputs, or
current Engine/kernel admission. The full Worker, PG, Agent, and server-feed
acceptance remains open.

## Pinned preparation

- Image ID and image manifest: `sha256:7c3a8389dc95348125c10ea062bd3cbd2af2a645f1b66127ead7bad6c0c6097c`.
- Raw OCI config SHA-256: `b5e9d3424e5915326235e869847fba670bb641d4f1321a4d83c884341cec3fdc`.
- Source commit: `41214ff3d049677ae9b599f5bd77ae23b817144f`.
- Image inventory SHA-256: `a9a9ab86294b0ad34f0448720ace3b3385273289515a6e36f632fec75283e753`; source manifest SHA-256: `38151dc32b838168a68b872ffd39530383f42006ee5a080f142bcf015dc93b91`.
- Dependency-lock SHA-256: `07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a`; pinned interpreter ELF is 14,480 bytes with SHA-256 `4dbf3143240288fb2170257ffaa7bd030cdda5d2703d1f5f30b627042267e2e3`.
- Fixed entry SHA-256: `aacb6225f59b2256bc45d0d30aaf229551b7498a896abe5452755d2f3d69b5af`; fixed observer SHA-256: `647e91bf88429c9887aeac44327968c01b12d78f23c7c6f1c35dc8e3f9fedf6f`.
- Required interpreter: `/usr/local/bin/python3`, CPython `3.12.15`, prefix `/usr/local`, actual `-B -I -S`, Linux x86_64.
- Baseline reported by root: Engine `cfe71bf3-9059-4059-887d-ac401f2283ec`, four images, zero containers. Re-inspect live state before any later operation; these are planning pins, not fresh evidence.
- Historical source-policy hash: `08acecf7f5eaa17f79cae5765dcc0dfbff64cd1a715b4d572f9500c306f48ff5`. It is hash-referenced for binding shape only. `policy_loaded` was false in the source-image evidence; this plan does not load policy or claim native admission.

## Proposed bounded operation

1. Root first reviews the exact `worker_provenance.preflight` contract and this
   driver. Use a fresh exclusive phase directory beneath the existing
   root-owned probe area and a newly generated 32-hex nonce. Never reuse any
   prior nonce, container ID, failed receipt, or phase directory. Do not alter
   or delete retained evidence.
2. On the already prepared AWS host, inspect the actual Docker Engine, immutable
   image ID, raw OCI config bytes/hash, image count, container count, and all
   relevant default/runtime settings. Require the pinned values above and the
   intended source manifest/inventory. The host must independently inspect the
   live security controls before create and again before GO. There is no image
   rebuild, source copy, package install, network access, or native policy load.
3. Make one fresh ubuntu-owned0700 phase and a private binding staging
   directory. Cloud phase file bytes are bounded by1.4MB, with a byte forecast
   before creation and bounded no-follow metadata measurement during/after work.
   Original AWS introduced5GB/free50GB and source preparation100MB remain the
   independent physical disk gates. Local source/evidence accounting remains
   the SAME6MB phase/cumulative129MB allocation, carrying114,179,067B and all
   failures. The concrete caller measures local files/native fixture receipts
   and reserves400KB for new transport/log/receipt artifacts before dispatch;
   the host rechecks the admitted numeric accounting before phase creation.
   These local limits are not mislabeled as a129MB total cloud-materialization
   limit. No old disk baseline is reset or retained resource deleted.
4. The root creates one disposable container from the pinned image with the
   reviewed fixed Python executable and the mounted driver at `/probe/driver.py`.
   Require network disabled, read-only rootfs, all capabilities dropped,
   `no-new-privileges`, UID/GID `10001:10001`, `--cpus=1`, `--memory=768m`,
   equal768m memory-swap, `--pids-limit=64`, no TTY, and open stdin. Apply a 40 second per-case parent
   watchdog and 240 second whole-phase wall deadline; kill/reap only the exact
   nonce/CID-owned container on expiry. Proposed command override is
   `--entrypoint /usr/local/bin/python3` with argv `-B -I -S /probe/driver.py`,
   attached stdin/stdout; no shell is involved. Cap each captured stream at
   64 KiB. These proposed resource limits require root review against the
   already verified host controls before execution. Mount the binding staging
   directory read-only in the container at `/inputs`; make the host staging
   directory traversable and each binding file readable by UID 10001. The host may replace the
   staged file between cases, while the container cannot write it. Mount only
   the driver and binding input; do not mount the checkout or a mutable source
   tree. Do not invoke `/opt/quantmesh/worker_entry.py` because it continues
   into `_child_main`.
5. Obtain the full created CID from the actual create response, then inspect the
   exact object and verify its nonce label, image ID/config, runtime controls,
   UID, mounts, and state. Build each canonical binding from independently
   observed live values, including the exact Engine ID, image ID/config hash,
   CID, nonce, source manifest/inventory hashes, dependency-lock and Python
   executable hashes, entry/observer hashes, `/usr/local`, Python `3.12.15`,
   and the historical policy hash described above. Use the binding encoder's
   canonical schema. Do not infer live Engine/CID/image values from prior JSON.
6. Start the container only after the pre-start inspection succeeds. The driver
   waits for newline-delimited GO frames on stdin. After the exact live CID
   exists and has been checked, the trusted host writes the case's canonical
   binding into the private staging file, computes its SHA-256, and sends that
   expected digest plus independently pinned manifest/inventory/entry/observer
   digests over stdin. Never put the expected binding digest in the mounted
   file or have the child recover it from there. The staging-file replacement
   and GO write must be ordered; do not proceed if the child is not waiting on
   the expected nonce/CID-owned container.
7. Run these five cases, one GO frame and one result per case:

   - `positive`: exact source binding and parent-delivered digest. Require the
     public `preflight` call to return the matching `SourceObservation`.
   - `wrong_go_digest`: exact positive binding, but the driver deliberately
     flips one nibble of the digest passed to the public `preflight`. Require
     `rejected_as_expected`.
   - `wrong_manifest_pin`: a separately canonicalized binding whose
     `manifest_sha256` is wrong, with its actual binding digest sent over GO;
     GO still carries the independently measured real manifest digest. Require
     `rejected_as_expected` from the public `preflight`.
   - `alter_entry_memory` and `alter_observer_memory`: use the positive binding
     and source files, but append a harmless byte string to the respective
     in-memory argument passed to public `preflight`. Do not write or mutate
     image files. Require `rejected_as_expected` for each.

   `output/prepare_source_preflight_probe.py` only invokes the module's public
   `preflight` API; it does not call `_preflight`, test helpers, callbacks, or
   `_child_main`. It checks actual interpreter flags/runtime and runs under
   UID 10001. The driver emits compact JSON lines only. Capture complete raw
   stdout and stderr at the operator, with a strict 64 KiB cap each; do not
   parse empty logs as JSON. Any malformed protocol, unexpected acceptance,
   mismatch, timeout, or nonzero child exit fails the phase.
8. Record operator monotonic timestamps, exact command/arguments, create/start
   response, full CID, pre/post `docker inspect` control state, exit/status/OOM,
   bounded resource counters if available, host free-space before/after, raw
   stdout/stderr hashes and bytes, and every case result in an immutable
   receipt. Do not record binding bodies or secrets. On timeout, stop/reap only
   the exact container whose full CID and fresh nonce label were just verified;
   preserve the failure receipt and logs. Do not remove unknown objects or use
   broad prune/cleanup commands. Verify the exact owned container is gone and
   that unrelated image/container counts and disk floor remain acceptable.
9. Report only a successful source-preflight observation if every positive and
   negative case matches. State explicitly that this does not prove the image
   was launched under a currently admitted kernel profile, does not solve the
   production `_snapshot` to UID handoff, and does not authorize `_child_main`.

## Binding and lifecycle contract gap for root review

The public source observer checks canonical binding bytes, the externally
provided binding digest, fixed Python/version declarations, source entry and
observer bytes, manifest/inventory hashes and source associations, and the
verified builder's complete inventory. It does not compare `engine_id`,
`image_id`, `image_config_sha256`, `container_id`, `owner_nonce`, or
`kernel_profile_sha256` to live host objects. The operator therefore has to
verify those values independently before GO and preserve the inspection
evidence. The current source policy hash is a historical binding value only;
it cannot be described as a currently loaded profile. Root should resolve
whether this externally verified binding is sufficient for the requested
source-only qualification before authorizing the later cloud operation.

The reviewed fixed entry accepts its expected digest through the trusted
parent/go channel, but proceeds into `_child_main` after source preflight. This
draft instead uses a tiny one-shot diagnostic driver so the actual public
preflight can be exercised without starting a Worker. Root review must confirm
the container's actual image entrypoint/config permits overriding the command
with the reviewed `/usr/local/bin/python3 -B -I -S /probe/driver.py` command
without relying on a shell or changing image contents. If the immutable image
cannot start that command under its actual defaults, stop and return with that
specific blocker; do not modify/rebuild the image or add a loader.

## Checklist

- [ ] Root reviews the exact script bytes and approves or corrects the GO
  protocol and five-case binding construction.
- [ ] Root confirms the image's actual entrypoint/default command supports the
  proposed Python override without shell, package, or image changes.
- [ ] Root confirms source lock/executable hashes and can construct canonical
  bindings from live values without deriving the expected digest from file.
- [ ] Root independently rechecks exact Engine/image/config and container
  controls, storage budgets, and fresh nonce/CID ownership immediately before
  any later cloud execution.
- [ ] Only after that review, root decides whether to perform one unique,
  bounded source-only probe. This file creation itself ran no remote command.

## Concrete caller and stop boundary

`python -B output/dispatch_source_preflight.py` is the sole one-shot local
caller. It explicitly reads only the bounded driver, host recipe and scalar
pins, checks resource accounting, generates/persists the exact nonce before
SSH, byte-pins the transport and injects SOURCE_DRIVER/SOURCE_PINS/
SOURCE_ACCOUNTING/SOURCE_NONCE into the host program. It calls ubuntu/private
SSH only once. An unknown transport outcome requires the same exact nonce's
host receipt/CID reconciliation, never rerunning the caller with a new nonce.
The host verifies actual OpenStdin=true/Tty=false, current Engine/image/raw
config before each GO and after the cases, plus exact CID controls.

This is one finite diagnostic within the server report delivery slice. After
its result, continue the actual baseline/job/report/reopen chain; do not add a
second or third kind of source proof. At the second structural review failure
or the slice timebox, stop this approach and record a concrete architecture
blocker/decision under the delivery contract. Source-only smoke remains clearly
distinct from release/native admission. Agent availability cannot block reports.
