Frozen b9d7b5d...a1f137f, four files only. Two read-only fresh reviewers; no external execution.

Spec: P1 missing actual admission-orchestration negative coverage; P2 path tests rejected ancestors before reaching intended link/tree guards.
Standards: P2 same missing admission-orchestration coverage. No other actionable correctness/material smell findings established.

Disposition at b623a568: actual start/inspect and genuine validator denial tests added with explicit root/manager/backend mocks and real PTY/pidfd/gated child; final replacement refuses release and reaps. Individual simulated-root metadata/no-follow/hardlink/owner/mutability/hash tests and descendant sentinel added. Final native83/0skip; Windows52pass31Linuxskip. Root startup steering uses fixed ExecStartPost later client; exact updated unit pin regression covers e108294e59e624d17b0f75034930c9ae3fe1f3d3353c44a90586069e1e0cfdac.
