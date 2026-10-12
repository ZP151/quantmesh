# QuantMesh workflow catalog 2.0.0

24 sourced offline workflow cases adapted from legacy catalog 1.0.0, retaining
QM-001 through QM-024 and their desired acceptance assertions. Taxonomy migration
is explicit; no legacy score is comparable or relabelled. All embedded scripted
fixtures and helper/test/verifier bytes are pinned by the frozen catalog.

Three historical audit assertions (QM-022/023/024) reproduce real failures at
the approved production baseline `2f424d07574ad5d3106d5447b259193a333ba7d2`:

- The origin guard admits `https://127.attacker.example`.
- Generic ResearchPipeline accepts an absent citation when its scripted critic passes.
- QuoteFence allows a filled paper order with one-hour-old source and fresh receipt.

These are observed boundaries and root-cause candidates, not production fixes.
The copied `test_audit_badcases.py` retains the desired assertions byte for byte.
The baseline is expected to exit 1; those failures count against success.
See [handoff](HANDOFF.md) for evidence commands, review, limits and integration needs.

## 90 秒中文解释

这个 Eval 衡量的是 QuantMesh 的工作流契约，不是大模型的投资能力。
使用者运行一个本地命令，就能把 24 个有来源的场景重新执行，覆盖正常流程、
边界、恢复、安全、复杂任务和历史回归。每个场景都绑定输入和验证器的字节哈希，
记录代码版本、独立 pytest 进程、完整日志、调用轨迹和最终结论。

我先复用已有离线 harness，再补上严格比较和证据保存。缺少 token、费用或完整
调用信息时写 null，不把未知当零。跳过、预期失败和超时都不能算成功。
任务成功率与单个验证器成功率分开计算，按场景和难度聚合。比较只允许同一套
catalog、验证器和超时预算，换题或换分类不能制造提升。

这次三个历史安全断言确实失败，所以普通 baseline 也返回非零。这是需要生产
代码负责人修复的证据，不能删题或反转断言。另有明确标记的 known-bad 负对照，
证明 harness 会记录真实失败。模型响应全部是脚本；真实数据库、Linux 隔离和
模型 API 的验收仍然独立待办，也没有付费调用或实盘交易。
