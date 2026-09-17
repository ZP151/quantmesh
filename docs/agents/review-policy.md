# Review policy

QuantMesh uses a small impact gate so evidence work can move quickly while
runtime and trading safety keep an explicit review boundary. Select the change
class from the complete pull-request diff, not from the title.

| Class | Typical paths or behavior | Merge gate | Deployment gate |
| --- | --- | --- | --- |
| A — evidence only | `docs/**`, iteration records and Markdown that do not change source, configuration, workflows, assets or operating commands | Required CI green, whitespace clean, no unresolved review thread, and maintainer scope check. A squash merge may proceed directly under standing merge authority. | No deployment is needed. |
| B — runtime/data | `src/**`, `frontend/**`, tests that change runtime contracts, settings, migrations, retention, provider adapters, workflows or deploy files | One independent human review, required CI green, focused regression evidence, and the relevant iteration record. Automated comments do not count as human approval. | Deploy only from the merged commit; repeat exact health, smoke and user-loop checks. |
| C — trading/security/infra boundary | order authority, risk limits, credentials, authentication, public ingress, OpenD exposure, live-mode enablement or destructive data operations | Two human reviews including the safety owner, required CI green, paper-mode regression and explicit operator acceptance. No administrator bypass. | Separate release checklist and rollback witness are required. |

Every class keeps the existing paper default, `live_trading=false`, private
loopback/Tailscale boundary and no-secret rule. An unresolved actionable review
thread blocks all classes. A documentation PR that records an operational
blocker must keep that blocker open rather than implying that the surrounding
service recovery closed it.

For the current work, PR #154 is Class A: it records AWS recovery evidence and
does not alter the application tree. PR #155 is Class B: retention changes
startup and feed runtime behavior, so it must complete the human review and CI
gate before the existing AWS node is updated.
