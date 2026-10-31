# OpenD internal pool readonly configuration

Refs [issue263](https://github.com/ZP151/quantmesh/issues/263).

One user action: recover the original c8 persistent private OpenD login console. This bounded prerequisite succeeds when systemd makes the internal storage pool readonly while all six intended external destinations remain writable; backend and visible login acceptance follow separately.

The actual merged559 Source check refused POOL/fs mount_mode. One subsequent isolated manager-owned configuration trial on installed systemd255 passed: POOL, fs, both lower views and both overlay views were readonly; HOME, STATE, RUNTIME, TMP, VARTMP and SHM each created/wrote11 known bytes/fsynced/closed its own exclusive synthetic file. Mountinfo stayed equal; actor/cgroup, Ref/bus and owned mount/loop closure passed. Direct POOL access returned EACCES through unchanged0700; readonly causality comes from kernel mount flags, not that errno.

Add only ReadOnlyPaths=exact c8 POOL to the existing c8 dropin. Pin those bytes and require the same exact effective manager scalar for c8 recovery. Keep the six writes, all binds including the formal IMAGE->ALIAS readonly input, base template, storage algorithms, identities, claim/marker, resources and paper/live defaults unchanged.

The isolated trial omitted IMAGE->ALIAS to avoid creating a missing formal target; Root explicitly permitted this probe-only input difference. It did not execute Source, the original service, vendor, SDK or UI. Its PASS is not full Source/backend admission. Raw wire7541B SHA b1ea1c1d1d0dd7e5cd0975920b8dacf95b654b7acfcf243e08eec0c83e41ee84; decoded23824B SHA0a1a77096c68745844f01c81eaaf2ac82446925b75ad7d04c638a8cd70c81897, retained in output/opend-private-storage-20261031-0220/pool-readonly-probe-01.

No new namespace platform, allowlist, caps, mode/ACL, dependency or financial behavior. Reuse installed systemd; no upstream implementation copying. Fresh agent review maximum R1/known-fix R2, exact selected CI plus aggregate green, normal expected-head merge and actual merged catalog precede any later operational disposition. Existing8MiB software hold is reused with fresh forecast; no new charge.
