# Two-axis bounded bootstrap review

Scope: d351c3a through bootstrap candidate plus root-owned actual_build health
constructor/new fields/tests. Original service/store/PG architecture excluded.
Independent fresh reviewers: bootstrap_spec and bootstrap_standards.

Round1 at66f7667: Spec identified2 Important (unloaded dependency code and
timestamp-valid dependency bytecode); Standards identified the same unloaded
dependency gap. Fix0f8b71e measures all installed executable closure RECORD hashes
and refuses bytecode and unrecorded code. Distribution-based tests observed
RED2, then GREEN, runtime44passing. No licensing or schema/protocol changes.

Round2 at0f8b71e: Spec clear. Standards identified1 Important untracked directory
symlink shadow (repository plus site-packages). Fix97f53d0 explicitly rejects
directory links. Two direct reproductions observed RED2 then GREEN. The final
candidate passes native full service85/0skip and genuineHTTP/SQL37checks. Under
the two-round cap there was no third re-review; the second-round finding is
closed by its direct regression and fresh final-candidate gates. Root retains
the final integration/release review gate. No deferred minor findings.

Reviewers confirmed fixed bind/default preflight, immutable explicit authority,
SecretStr/redacted errors, actual store health, truthful absent Worker/model,
adapter reuse and no original service architecture expansion. Static review
alone is not native qualification; the separate raw receipts provide that proof.
