# Worker native-load boundary implementation plan

> For agentic workers: execute inline with TDD and a bounded independent review. This refines the already approved Option A native-load requirement; it does not activate a Worker or install a host policy.

**Goal:** Make the measured immutable ELF closure the only source of executable file mappings, and deny writable/generated executable memory before allowing numerical Worker execution.

**Architecture:** Reuse the actual research host's AppArmor 4.0.1 and Docker seccomp/cgroup support. Construction tooling derives a policy from independently pinned ELF bytes and a pinned Docker default seccomp document, preserving baseline refusals and narrowing protected syscall allowances. Parent admission must later verify the loaded enforcing profile, policy bytes, actual container security options and actual noexec mounts; parsed configuration is never admission authority.

**Spec:** `2026-10-13-worker-lineage-root-ruling.md`, native-cache proof and independent binding chain; `2026-10-12-research-foundation.md`; issue #172.

## Global constraints and planner decisions

- Keep the frozen WorkerRunner/JobStore/report contracts and numerical engine. Native-cache exceptions remain refused until the complete parent/kernel/entry chain passes actual execution.
- Use the existing isolated workspace on a dependency branch from exact PR #175 head `de06066`; #175's current CI and candidate remain independent of this new work. Integrate after its ordinary review/CI gate, without force push or admin merge.
- No new runtime dependency, environment, image or paid resource. Existing three AWS machines and paper=true/live=false remain the operating budget.
- Preserve the original 8,876,772-byte software baseline, prior 26,616,648-byte conservative forecast, pending whole-C attribution and all previous failures. New PG-related roots measure 5,600,929 bytes; conservatively add them without assuming overlap. C free is 165,186,068,480 bytes. Explicitly allocate a 40,000,000-byte cumulative software ceiling, retaining the 50GB free floor. This is local software accounting, not a paid-resource or native-materialization waiver.
- Resource correction before the next run: an omitted short pytest ID for the 1MiB oversized-input case made PYTEST_CURRENT_TEST exceed Windows' 32,767-character limit. The first run has 39 passes and two setup/teardown errors, producing a 4,202,324-byte log and a conservatively counted 2,209,752-byte entire pytest cache, exceeding the original 3,000,000-byte phase reservation. Retain the failure and original SHA/byte count; redact the traceback's ambient environment representations and compact repetitive diagnostic IDs before retaining the safe log. Increase this phase allocation explicitly to 7,000,000 bytes, giving cumulative upper 39,217,577 bytes within the same 40MB ceiling. No earlier reservation, baseline or failure is subtracted. Fixed short IDs and cache-disabled focused verification prevent a repeat.
- Do not modify the staged incomplete a718 provenance foundation or repeat the passed synthetic Reader/native Task1 witnesses.

## Review focus

1. A custom seccomp profile must not replace Docker's baseline refusals with a default allow action.
2. Executable memory may be requested via mmap, mprotect, pkey_mprotect, memfd or SysV SHM; transient execution matters even if later mappings disappear.
3. ELF filenames must not inject AppArmor grammar or admit input/output paths.
4. An effective child mount, including a nested mount, must be checked from actual mountinfo; Docker bind mode strings do not prove noexec.
5. Pure policy generation and parser success must remain distinguishable from kernel enforcement and independent parent admission.

## Task 1 — Policy construction and truthful mount validation

Files: create `src/quantmesh/research/worker_kernel.py`, `tests/test_worker_kernel.py`.

Interfaces: `build_kernel_policy(elf_files: dict[str, str], *, docker_default: bytes, docker_default_sha256: str) -> KernelPolicy`; immutable result contains the profile name, AppArmor bytes, seccomp bytes and combined digest. `verify_mountinfo(raw: bytes) -> None` rejects root mutability, missing required mounts, any executable writable mount, any executable inputs mount, ambiguous/invalid/oversized mountinfo and incorrect input/output/tmp permissions. Neither function installs or certifies a profile.

- [x] Write behavioral tests for default-allow refusal, default rule preservation, independent syscall argument evaluation, grammar injection/path rejection, deterministic binding and nested/ambiguous mount checks.
- [x] RED: `python -m pytest tests/test_worker_kernel.py -q --basetemp=<fresh workspace-owned directory>` fails because the implementation is absent; exit2 log retained.
- [x] Implement pure bounded builders. Pin x86_64; preserve baseline refusals and restrict existing ALLOW rules for anonymous executable/W+X mmap, executable mprotect/pkey_mprotect, executable SHM and unsafe memfd flags. Never create an allowance absent from the baseline. Intersect existing masked/equality conditions and preserve capability gates without duplicate argument indexes. Permit `m` only on exact immutable measured ELF paths. Permit `ix` only on the measured canonical Python command/target. No shell, install, loaded-profile claim or default activation.
- [x] GREEN: focused44pass/one existing NumPy warning/1.10s; Ruff/format/diff pass. Existing remote AppArmor parser skip-kernel-load/skip-cache exits0. Existing host libseccomp compiles49BPF instructions with no filter load;14 independent exported-BPF decisions pass. These are construction/compiler checks only.
- [x] One scoped fresh review identifies P1 wrongSHM flag. Two REDs reproduce SHM_EXEC incorrectly allowed/SHM_RDONLY incorrectly refused; mask corrected to Linux UAPI0100000, full44checks pass. No third architecture review. Preserve RED/GREEN and commit the coherent checkpoint.

## Task 2 — Native enforcement and independent parent integration

Planner ruling after PR175 CI fixture repair: use a separate bounded 2MB
metadata-intake reservation (cumulative ceiling48MB, previous measured upper
43,877,260 bytes retained). Stream the existing immutable image through one
never-started, nonce-owned container; hash ELF regular files and archive links,
keep only <=512KiB metadata, never extract/materialize the image or load code.
Export is capped at1.5GB read/90s; container limits/network none/no privileges,
same Engine/image/counts before and after, removal by fullID/image/nonce. Original
AWS5GB/free50GB limits remain. Review this finite recipe before actual use.
Image content measurement is not native containment, admission or numerical
qualification. Source intake pins the installed Docker29.9.0 commit's Apache2.0
default profile (SHA785b2429); pure construction preserves37 original rules as
43 restricted rules, but synthetic ELF placeholders still do not prove a real
image closure. All earlier failures and separate kernel7MB/CI6MB budgets remain.

- [ ] Freeze a bounded test-owned operator recipe using the existing immutable image and a new exclusive phase, including exact policy/ELF/source hashes, engine/kernel identity, limits, noexec task mounts, an independent surviving sibling and cleanup by exact ID/nonce.
- [x] Pin the exact upstream default seccomp profile compatible with the installed Engine; preserve its source/license and verify generated policy compatibility.
- [ ] Under the applicable reviewed operational boundary, install only the uniquely named task profile; test actual mmap/mprotect/pkey/memfd/SHM denial, legitimate baseline imports and numerical execution. An unsupported import or mount is a retained failure and requires a planner correction, never an exemption.
- [ ] Integrate the actual enforcing kernel policy and mount evidence into image admission, the fixed standalone entry and the immutable parent binding. Revalidate at pre-dispatch/post-compute/publication, then run existing full baseline/report and two-job reclaim acceptance.
- [ ] Clean only exact owned test resources. Actual profile-load, noexec mount setup, independent parent, numerical equality, persistent reports and server user acceptance remain required before enabling a Linux Worker.

Primary references: [Docker AppArmor](https://docs.docker.com/engine/security/apparmor/), [Docker seccomp](https://docs.docker.com/engine/security/seccomp/), [AppArmor policy permissions](https://apparmor-documentation-c38b15.gitlab.io/documentation/in-depth/profiles/core-policy-reference/).

Implementation ruling: the initial additive ERRNO draft is superseded before review or native use. The upstream [containerd default profile](https://github.com/containerd/containerd/blob/main/contrib/seccomp/seccomp_default.go) documents that broad ALLOW rules can make ERRNO branches unreachable, and runc can split repeated argument-index conditions as OR. Independent allowance-evaluation regressions first fail 10 cases against the draft, then pass 42 total checks after restrictive rule intersection. No loaded policy or runtime certificate relied on the draft.

Actual metadata checkpoint: inventory8ec11903 / 886ELF / 633mapping paths; exact Engine default policy parses on AppArmor with skip-kernel-load. RLIMIT_AS parser allocation regression passes. First inherited-label refusal and exact never-started CID cleanup retained; no actual enforcing policy or Worker acceptance yet.
