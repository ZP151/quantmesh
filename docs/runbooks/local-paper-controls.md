# Local synthetic paper pause and resume

Scope: issue196 / ADR0033. This extends the existing manual kill-switch page.
It reuses the account store, persisted account, journal recovery and paper kernel.
It does not run a strategy or connect a broker. Implementation acceptance is
recorded in `docs/iterations/0038-paper-controls-p3.md`.

## Start an isolated rehearsal

Use existing project dependencies and a new owned demo folder. Keep the control
folder outside the demo folder, so its retained audit cannot be reset with demo
data. Without `--paper-control-root`, the optional capability is off.

```powershell
python -m quantmesh.api.workstation --demo --demo-root output/paper-rehearsal/demo --paper-control-root output/paper-rehearsal/controls --paper-max-order-quantity 1 --paper-max-notional 1000 --paper-max-position-quantity 100 --port 8868
```

These three numbers are explicit **synthetic engineering thresholds**. They do
not establish an investment risk budget. All three must be finite positive
values supplied together. Starting with none is allowed, but resume stays
blocked until the operator configures all three and restarts. Review the costs
displayed by the page; the existing kernel still applies its fee, slippage,
available liquidity and risk semantics.

## Operator loop

1. Open the existing `/ops/kill-switch` page on this local instance. Check the
   synthetic scope, current pause cause, evidence checks, thresholds and costs.
   Every opted-in startup begins paused, even after a previous valid resume.
2. Enter a short reason and pause. A fresh synthetic paper order must be rejected
   by the existing kernel, with no new account/journal/fill effect.
3. Select global or an existing retained venue stop, then check resume evidence.
   Global resume preserves venue stops. The service checks the current persisted
   account, journal, audit and explicitly configured thresholds under the account
   authority lock. Missing or inconsistent evidence blocks resume.
4. Review the displayed revision, enter a reason and explicitly check the local
   confirmation before resuming. A change between check and confirmation is
   refused. Refresh and check again; do not try to reuse the old context.
5. Inspect the current state and completed receipt. Download the original audit
   or receipt. Downloads include their actual SHA256 and the client checks it.
6. Stop and restart this same owned instance without resetting or deleting files.
   It must reopen paused and retain the original receipts. Replaying an old
   successful resume returns its original receipt plus current state; it cannot
   undo a later pause or create another order.

Confirmation records local intent, not authenticated identity. Legacy JSON/HTML
disarm routes cannot substitute for verified resume in this mode. Demo reset is
refused while controls are attached. The command palette leads to this page
instead of offering a direct resume or reset. Loading, errors and generic503
failures stay guarded; only the exact capability-off response enables default
legacy controls.

## Evidence trouble

Preserve the original account, journal and audit bytes when evidence is missing,
corrupt, inconsistent or has an unfinished publication. Do not edit the retained
files to obtain a green state. A corrupt cold account may prevent startup under
the existing seeder validation. This slice offers no repair interface. A second
writer is refused by independent account/control OS leases.

This loop qualifies synthetic control behavior only. It does not establish
strategy skill, real-market execution quality, data rights or production
readiness. Historical REJECT/INSUFFICIENT and consumed OOS evidence is unchanged.

## 中文操作摘要

使用独立本地演示目录，并把控制审计目录放在演示目录之外。启动参数中的三个
正数阈值仅用于合成演练，不是实际投资风险预算；缺少阈值会阻止恢复。

打开现有“暂停开关”页，先核对合成范围、当前状态、原因、证据和成本。每次
冷启动均暂停。填写原因后暂停，新的纸面订单应由现有内核拒绝且不产生额外
成交。检查恢复证据后，核对当前版本并明确勾选确认；中途状态改变会被拒绝，
须刷新重新检查。全局恢复不会静默解除各场所暂停。

查看完成回执并下载原始审计/回执。重复请求返回原始回执和当前状态，不会
重新执行旧恢复。保留文件重启后仍须暂停，历史回执保持不变。证据缺失、损坏
或发布未完成时保留原始字节，不要手工篡改成通过。此功能不增加策略循环、
真实行情、券商连接或实盘权限，也不改变既有研究裁决。
