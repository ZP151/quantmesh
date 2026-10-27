# 可审批短设计：选择已保存历史窗口，仅作观察查看

状态：**DESIGN ONLY / NOT APPROVED / SOURCE0**。这是新 API/UX 行为，
不是原 #218 bugfix，也不自动完成原生两库同响应验收。

**一个用户动作：** 在现有市场图表旁选择“查看保存的历史”，输入带明确时区的
窗口结束时间，查看截至该时间最近一天的已保存观察；“返回当前”恢复原默认页面。
首片只支持现有 Hyperliquid 与 AAPL/NVDA 的1d路径，不增加任意interval、
多段DTO、聚合、策略引擎或回测数学。用户成功标准：选择 Oct23T23:44:01Z，
能在一个只读图表看到保存的真实1m片段/覆盖/来源，或明确 unavailable；
返回当前后默认请求与风险判断完全恢复。验收时间目标≤2分钟。

**最小边界：** 优先复用当前服务的 as_of 参数，但只能把它解释为用户明确
选择的数据窗口，不可替换 app/instrument/workspace/Paper 的时钟。建议一个
独立只读 `GET /api/instruments/{venue}/{symbol}/history-inspection?at=...`，
固定1d。比给整个 workspace 添加历史时钟更小：现 workspace 同时组合决策、
预测、账户和风险，不能把它们整体回拨。原 history URL 与 JSON 不变。
这是一个历史复盘路径，不为原生验收偷偷提供特殊配置。

返回复用 HistoricalSeries 的图表数据，外层只加实际请求 `observed_at`
（真实server UTC）、用户选择的 `window_end`，以及最后保存数据的
`source_time`/`source_received_at` 和按真实 observed_at 计算的陈旧标记。
`observed_at` 不冒充供应商观测时间；旧时间戳保持原值；若复用 manifest 数据
而没有 receipt 字段，receipt 明确缺失而不生成。UI 同时显示“历史观察”、
请求查看时间、数据时间、覆盖范围及“不是当前报价”；不展示live连接成功暗示。
外层元数据不是 segments DTO，不更改每根bar的语义。

后端复用 manifest-first 与 `_replay_series` 双时间过滤/身份冲突/STATUS/
分辨率/最后连续段规则；单独的 inspection 方法跳过当前 `join_live_tail`，
不得把历史时刻的freshness重新包装成当前live。at必须是显式有时区UTC时间，
不得晚于真实server now；未来/缺时区拒绝，缺资料与不足两根保持unavailable。
真实断档不补、不连接、不聚合；coverage只代表返回片段，不能宣称全日完整。

继承只读archive、stopped hot、不写DB、不启动provider和128MiB/1thread/0spill；
每库≤10000候选、最终≤10000条、每次≤128-key完整行取回。不扩大行数/keys或
扫描窗口；行数限制不等于任意payload总RSS证明，底层拒绝必须向上传递。
不并行拉全量历史，不造新索引/库/恢复器，不加主机权限或依赖。

历史页不调用workspace/render来生成过去的决策、报价、forecast或Paper提案；
不提供Paper按钮，历史anchor不进入任何POST/Paper/fence请求。服务端原Paper
freshness、风险、版本与fence仍按真实现在重新验证，不能靠隐藏按钮代替它们。
切换窗口后立即清除上一窗口图表及请求错误，避免旧响应被标成新窗口；返回当前
重新使用现有默认请求，不携带anchor。沿用现有MarketCanvas与日期输入/状态布局，
继承PRODUCT/DESIGN，不改视觉系统。设计侧文件漂移单独记录，不在本片修复。

**预期文件锁（仅批准后）：** instruments/{api,contracts,live_history}.py；
frontend/src/screens/InstrumentWorkspace.tsx、frontend/src/lib/api.ts 与
frontend/src/lib/messages.ts（现有双语字符串）；新增
专属后端/前端测试及一份ADR/iteration。复用MarketCanvas不改其数学。
README/版本/locks/generated由
publisher独占，不进入此片。先RED：旧default响应不变、at合法性、pastarchive
返回而source/receipt原值、无live_tail、gap末段、manifest优先、bounded拒绝、
未来/陈旧anchor不能改变Paper/fence、请求竞态/返回当前。GREEN后≤2轮独立复核。

**与特殊验收样本相比：** 此功能直接让用户查看自己已保存的历史，长期有用，
代价是一个受审的新只读API/UX；专为验收取得连续小样本只能验证两库某次合并，
不能解决旧历史的可见性。本设计优先产品可见性，不另取样本。即使获批并完成，
Oct23与Oct26相隔数日仍分别查看，不声称它们是一条连续series或原 #218 已关闭。

集中决定：批准上述受限历史查看切片，或暂不增加功能并保留当前明确不足。
在决定前不实现、不取数、不启动主机。
