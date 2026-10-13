# NEW weak-reference correction: INCOMPLETE, no integration

Ruling627067fa75e0669c75ccfb55a5c9f3ab8dabc5496b5973124fac4a447027ad59
was read in full and hash-verified. Retained172/173 source/delta/manifests/failures
are untouched. Earlier WIP tree40a9b71250be34d69cc3d85c2809a02a9704e66e;
current staged WIP tree8252e0fbfc8eb4909f7ec77d55991c20f8892f3e. HEAD remains
bb36e404a8e6cfe8a254cb3b1f3d17ecaace1bcf. No commit/push/PR/review/integration.
AGENTS authority remains revoked. Only the same three new source/test files changed.

Earliest actual sys capture is retained. Builtin _weakref is then imported before
ordinary entry imports; constructor/type, C call descriptor and readonly callback
member plus module namespace associations are privately captured by the measured
fixed entry. _WeakReferenceStorage is a private raw inspection helper, not runtime
admission: host-unit late captures explicitly grant no fresh-entry authority.
Session construction still requires actual entry/runtime/interpreter/DSO/binding
checks before it can use this capture. Parent/container/kernel authority is absent.

Exact captured reference instances expose target/callback via captured base C
descriptors; both are traversed and associated. Dead target is None. Actual raw
constructor associations revalidate; subclasses and proxy kinds refuse before
GC fallback. No callback, target method, user descriptor/hash/repr/equality is
invoked. An actual target metaclass comparison trap reproduced12calls in RED;
current graph classifications use actual type identity instead. Closed checked
module/core dictionaries are referenced through their independent namespace set;
unknown globals still traverse. No opaque-object whitelist was broadened.

Evidence: unit-red.log4failed (missing new storage helper); unit-green.log4passed
on its exact earlier source. traps-red.log1failed. CURRENT green.log6passed2failed:
actual weak referent native-cache stand-in, callback cache payload, foreign module,
live/dead and target/callback storage mutation, subclass/proxy descriptor traps,
and target equality/hash/repr traps pass. These are actual builtin weak-reference
objects, with fake Cython/foreign payloads; no native numerical imports/probes.

Actual current fixed BASE entry and captured-core mutation test still fail BEFORE
foundation-initialized. Thus captured-core and weak-constructor shadow/preload modes
have NOT reached their intended boundary and are not counted as verified. Actual
entry reports sanitized refusal and exit2; no current BASE success is claimed.

Per ruling, exactly ONE controlled fresh diagnostic was taken for the DIFFERENT
unsupported family: _contextvars.Token.MISSING, raw-kind MISSING, with no GC
referents (diagnostic.stderr). Refusal is retained. No MISSING name/identity/type
exemption, new capture or further patch loop was added. Return this unsupported
storage/constructor boundary to Planner. No review starts while BASE acceptance
fails, and no old construction/Task1 or third old architecture review was repeated.

Current lint, formatting and staged diff whitespace checks pass. Source snapshots,
exact hashes, all current raw results, ruling snapshot and resource/manifest receipts
accompany this handoff. Software-only; ALL native caches refuse, independent parent
Engine/image/config/CID/kernel chain and closed native boundary remain unimplemented.
No local materialization/env/clone/container, numerical/vendor/API operation,
protected runtime/package-init/store/schema/lock/math/report change or cleanup.

Budget before seal: current incremental260,718B /600,000B; original foundation
upper4,874,129B /5,500,000B. Root READ-ONLY frontier dynamically remeasured after
its added failed-source/frontier-writer copies:19,490,297B /20,000,000B, free C
98,818,564,096B. Original8,876,772B baseline and all failures/copies retained.
No cap reset/increase outside ruling or whole-C5GB attribution waiver. The seal
receipt records subsequent source/metadata/archive-copy charges within this slice.
