# QuantMesh 开发暂停与恢复交接 — 2026-11-22

此文档记录既有开发成果、未完成工作与恢复条件。2026-11-22获准的工作仅为记录整理、源码保全与文档同步；功能开发、数据采集、金融试验和部署继续暂停。恢复须消费更新的明确范围，历史Issue的标签不产生自动执行授权。

## 已完成的限定范围

- 任务恢复功能已按历史验收范围封存；90秒仍只是性能观察。
- BTC正式应用通过有限时段行情观察与清理；该结果不证明常驻服务或全市场覆盖。
- PR254完成离线普通页计算、成本基准报告、不可变决定、受控重启后同ID的admission/report/decision读取且无新增计算。真实研究资格独立。
- PR303/305/307已合并：恢复API、保存研究列表（最多32条）、同ID重开、vn.py中英文和桌面流程。此前页面验收只证明当时已部署范围，当前未声明在线入口。

## 未完成工作与依赖

| 工作 | 当前状态 | 已保留成果 | 恢复后的最小下一步 | 原角色 |
|---|---|---|
| 真实研究案例 | 未完成、暂停 | 工程用户链与事务消费者 | 对适用真实包独立验收后，完成普通页成本/基准报告、决定与重启原件找回 | Quant → Product |
| IVV数据 | 限内部小时图表 | 1893小时行覆盖121交易日的资格结论 | 补足研究协议需要的RTH日线及行动、单位、来源依据；小时数据不冒充日线 | Quant |
| OpenD SDK | 长期阻塞、暂停 | 84字节Init请求后的无应答证据及短测试代码/日志索引 | 先取得能够区分读取、解析、分派或写回原因的最小证据；不连开推测补丁 | 原SDK负责人、Server |
| Beta账户 #309 | 分支保存、NOT_READY | `1209064a1bbbf5621671c8a160a884ca63839527` | 收敛SSE订阅清理与session失效后的响应截断两项P2；账户前端依赖稳定后端合同 | Product → UX |
| 桌面日/周图 #308 | 远端WIP归档、功能未完成 | 15份源码与计划已保全；归档分支codex/archive-day-week-wip-20261122/9d31fe1b | 完成页面/路由及必要typecheck和浏览器链路验收；已有测试不代表最终通过 | UX |
| 5/21/63交易日预测 | 只有规范 | 预测时点、区间、基准与到期评分口径 | 在合格数据上实现可检验预测及显示，保留样本和误差/覆盖率 | Quant → Product/UX |
| 旧保存历史库 | 软件部分完成、运行未验收 | privateRAM/WAL实现与失败结论 | 如未来明确恢复，重新裁定独立维护范围；不是新研究的前置 | Server |
| 策略有效性/交易晋级 | 未验收 | 确定性研究与风控基础 | 成本、时序、样本外和纸盘证据；继续Paper默认、Live关闭 | Quant、Product |

## 代码与证据保存

本次读取远端main为`a99340195b27368772ef8d2d24242da79c1a85f5`，tree`2085d219f27e15ed21f9ae5dd0cf6a7cb128f8b5`。账户源码远端分支已核到1209064a；两P2审阅仍NOT_READY，没有因源码保存自动变为可发布。旧工作区的ignored测试日志缺失，保留的审计摘要不可代替原始输出。日/周图初盘点尚未提交，其后Publisher已确认归档分支codex/archive-day-week-wip-20261122/9d31fe1b远端回读；原私有15文件保全不变，仅一份文档内部会话标识脱敏。未完成源码保存不等于合并发布。

三台原云实例及系统盘已在明确批准的收尾中删除。8件备份文件完成云回读长度与摘要核验，恢复资料已封存；新机器数据库恢复及业务启动尚未验证。历史“备份正在执行”和“待上传”字段已过时，不能据此重启运行。此文不包含原金融数据、凭据、恢复密钥、网络/账户信息或运行会话内容。

公开的[云端成本控制方法](../runbooks/aws-cost-control-20261122.md)只比较官方价目与假设场景；个人历史账单和实际资源占用留在私有导出，不能从公开示例推算个人节省额。

### 本次实际源码归档版本

| 保存内容 | 分支 | commit | tree | 验收边界 |
|---|---|---|
| Beta账户 | codex/beta-research-accounts | `1209064a1bbbf5621671c8a160a884ca63839527` | `c37cd8b976af51fda5c6f7f841d15c75478f6e41` | 已在远端，未合并，两P2未关闭 |
| 日/周图WIP | codex/archive-day-week-wip-20261122 | `9d31fe1be61dc0c8242479d067b7a572b7ddcf53` | `0a61b72b8b10a9a622252219f5527f8b74aad278` | 15文件保存，无功能修复或新验收 |
| SDK诊断文档 | codex/archive-init-causal-docs-20261122 | `7ea2c7450c971492ce8f9243f99f9098a805f2a5` | `2ddad6669e73057a5c1c92d80e70b3a9e80f0b62` | 两笔原本地文档提交保存，OpenD仍未修复 |

三项均消费唯一Publisher的实际远端分支回读收据。本轮未将这些未完成范围合并为产品发布。

## 路线图解释及下一次恢复

M0–M13记录的是既有软件基础与历史交互验收。M14的工程部分已交付，真实数据研究、Beta账户、多周期图和可检验预测尚未收尾。保存列表、语言与桌面成果不因后续阻塞变成未开发；软件合并也不等于真实策略有效。没有可辩护的统一全项目完成百分比。

截至2026-11-22采样，14个未关闭Issue按已知后继状态整理：

| Issue | GitHub状态/标签 | 本次归类 |
|---|---|---|
| [#309 Add opt-in beta accounts with isolated Native research and revocable access](https://github.com/ZP151/quantmesh/issues/309) | OPEN / ready-for-agent | PAUSED_BRANCH_NOT_READY |
| [#308 Desktop daily/weekly charts with independent lookback and time-linked views](https://github.com/ZP151/quantmesh/issues/308) | OPEN / 无 | PAUSED_REMOTE_WIP_SAVED |
| [#301 Prepare a guarded same-build OpenD maintenance transaction](https://github.com/ZP151/quantmesh/issues/301) | OPEN / ready-for-agent | PAUSED_NO_DEPLOYMENT |
| [#293 Add a guarded Init-only SDK reference and conditional fixed IVV capture control](https://github.com/ZP151/quantmesh/issues/293) | OPEN / ready-for-agent | PAUSED_LONG_TERM_BLOCKED |
| [#272 Implement feasibility-first native producer for the approved one-shot IVV capture](https://github.com/ZP151/quantmesh/issues/272) | OPEN / ready-for-agent | SUPERSEDED_FAILURES_RETAINED |
| [#269 Profile two slow release pytest nodes in the existing gate](https://github.com/ZP151/quantmesh/issues/269) | OPEN / 无 | CONDITIONAL_SOFTWARE_NOT_RELEASE_GATE |
| [#259 Admit the approved one-shot IVV retrospective study through the native daily workstation](https://github.com/ZP151/quantmesh/issues/259) | OPEN / 无 | PAUSED_BLOCKED_INPUT |
| [#257 Support explicit WAL PRESENT/ABSENT admission for checkpointed history](https://github.com/ZP151/quantmesh/issues/257) | OPEN / 无 | PAUSED_RUNTIME_UNMET |
| [#255 feat: guarded private RAM auxiliary profile for saved history](https://github.com/ZP151/quantmesh/issues/255) | OPEN / ready-for-agent | PAUSED_RUNTIME_UNMET |
| [#242 Research: qualify one SEC issuer as-filed clock, amendment and accounting fields](https://github.com/ZP151/quantmesh/issues/242) | OPEN / needs-info | INVESTIGATION_DONE_NEEDS_INFO |
| [#208 live: keep the feed loop responsive during owned persistence](https://github.com/ZP151/quantmesh/issues/208) | OPEN / 无 | SEALED_BOUNDED_PASS |
| [#205 research: freeze one OpenD SPY daily sample and complete a bounded replay workflow](https://github.com/ZP151/quantmesh/issues/205) | OPEN / ready-for-agent | RETIRED_HISTORICAL_ONLY |
| [#169 Server-owned OpenD gateway and real market ingestion independence](https://github.com/ZP151/quantmesh/issues/169) | OPEN / ready-for-agent | PAUSED_LONG_TERM_BLOCKED |
| [#167 Iteration 0038 — Recoverable research foundation and server market sources](https://github.com/ZP151/quantmesh/issues/167) | OPEN / ready-for-agent | MILESTONE_NOT_ACHIEVED_PAUSED |


下一次恢复由主控选择一个明确用户动作、成功标准和原owner，沿已有源码及证据续办。第三次结构性失败返回Planner缩范围；已有完成证据不重派。跨市场、收费、移动端和新策略家族没有由本记录获得新增实施授权。
