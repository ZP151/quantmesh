# 范围、身份与审批差异

Status: PROPOSED_ONLY。依据b6fa35b7702063a5f04e2910de3f88bf875da8fa；不实施、不测试、不创建WT。此文件细化决策页，不能当作新协议已存在或真实输入已获准。

## 1. 一项需要人的新授权

可供root集中询问的原话：

> 是否批准方案A的一个合成工程切片：原位版本化现有日线账务内核，新增受信数量策略接缝，由该唯一内核产生次OPEN代理模拟fill并推进已冻结趋势policy；使用独立candidate协议/新源码身份，旧SMA100与once-consumed profile仅保留原件读取/原ID重开而禁止按旧身份新执行？本批准不含真实数据采集/金融资格、交易、付费或预算扩大。

这是从“外部给定Account/Fill的纯policy trace”变成“唯一账务内核实际计算合成现金/应收/模拟fill”的明确行为变化，也允许活动engine源hash变化及新的协议namespace。它不是重复确认#236，也不是只增加一个adapter。若不接受旧profile退为只读或这一核心迁移，应保持STOP，不在两个可执行账本之间折中。

## 2. 两条路径为何推荐A

**A：原位重构，唯一活动账务实现。** 在既有spy_replay_engine.py内将数量选择从一次日线状态转移中分离。费用/分红/现金/mark和metrics/_reconcile继续属于该文件的一条实现；新candidate驱动和legacy-compatible控制都调用它。旧run_cashbook循环不得保留成可执行副本，也不得在adapter中复制其现金更新。过去Git blob/原包里的源文件只是惰性历史证据，不是第二个运行内核。新的数量、顺序和取消语义是真实数学/控制变化，须新版本、新hash和工程证据。

**B：复用已安装vn.py成熟引擎。** ADR0029证明既有独立安装及固定fixture接入；runner真实使用add_strategy。对其支持的原生分钟/long-short/limit任务，这是可执行扩展路径。但当前仓库接线并未证明本候选的ex/pay应收、整股全额现金约束、next-OPEN而非限价触价、以及对应基准/终点语义。原engine存在native统计也不证明等价现金账本。若另补这些会形成被禁止的账务层；若放弃这些会变成另一个候选。因此**本候选排除B**，不尝试安装/运行/外部调查，不把“未证实”等同于对上游能力的全面否定。

P2 Catalog是原包检验器，不是第三条engine路径；PaperAccount的既有订单账务也不能在缺少日线应收/评测profile时冒充相同研究对象。它们在本次不扩展。

## 3. 唯一账本与数量接口

以下为拟定内部接口，不是新公共API/DSL。实现计划须在批准后再落精确类型及TDD。

| 内核/策略步骤 | 输入与输出/唯一写入者 |
|---|---|
| begin_session | 内核按冻结session日历与行动表，对上日持股确认ex entitlement，处理已到pay的应收；输出不可变account view。原已有cash/shares/pending是唯一账务真值 |
| size_request | 受信registry仅选已冻结candidate或固定对照；t收盘action+当前OPEN/account view/严格prior20量→signed quantity proposal及原Action/campaign身份。policy不能提交订单或改cash |
| apply_open | **内核唯一**：验证不放大proposal、ownership/cash/容量/数值边界；用原始OPEN及原单边成本公式更新一次cash/shares/fee，输出simulation fill及before/after账务。无额外matcher、native-vn.py收费或第二次同日交易 |
| on_fill | 原policy消费本次真实计算出的**模拟**fill，只推进campaign、已消费档位、退出origin；若允许量更少，普通档位余量一次取消，全退保留origin继续下一合格会话 |
| close_and_decide | 内核收盘mark并记录净值；已完成且可用的t数据形成t+1action。原policy只看raw-close，不能读t+1开盘；warmup不产生新candidate订单。首次B50/B100买持是协议预定入场，不从同日close生成 |

最终OPEN是预先锁定的结束边界；flat不得进入，持仓未清完失败且不发布成功数值报告。最后不处理一个事后close信号。股息未付应收保留为财富，不成为spendable cash；同批不再投资卖出所得。split/不支持行动仍拒绝。该研究模拟的pay日开盘入账假设不升级为真实账户结算资格。

### 数值接缝必须明示，不能靠隐式float→Decimal洗平

- 既有内核现金/费用/收益算术仍使用已采用的数值表示和公式；本切片不增加第二个费用类，也不把全部账本迁成新货币引擎。旧函数被抽取/重排与数量选择变化仍导致新源hash及新数学版本；不承诺旧运行字节相同。
- 新协议明确一个**仅供policy读的保守视图**：cash及receivable向下取到USD1e-8，shares保持整股；原始OPEN/close价格必须有确定的十进制表示且至多8小数，才能提供给冻结policy。底层原cash/receivable绝不被视图值覆写，偏差与原值身份记入trace。现有policy的20位/1e12/8小数界限保留；不能代表的状态拒绝，不静默扩大输入域。
- 内核使用其实际未量化账户与同一OPEN再次校验proposal的费用后cash、75%约束及已审量cap；不得上调股数。若保守视图与真实算术仍在临界处不一致，整次工程计算以numeric_boundary_mismatch失败；不能给负现金清零、向上round、私下补一股或报告成功。该小额保守视图可能少买一股，是v2数量语义，必须绑定协议并展示，不能说经济行为毫无变化。
- policy的fee_at_allowed仅供核对；唯一扣费发生在apply_open。统计继续复用现有metrics表达式，不新写Sharpe/费用/回报算法。既有long_entries公式实际数所有buy fills；新report将它准确标作buy_fill_count，campaign entry另从policy事件计数，不把加仓次数伪装独立机会。

这条桥能在固定可表示工程fixture上落地；若一般合法新数据频繁触发numeric refusal，需要另一次明确的货币表示设计，不能在首切片暗加量化/舍入规则。

## 4. 源hash、旧profile与原件准入

1. 旧packaged engine原字节SHA6e8ad80f134b7c1f44bcb4cb7695e784009953aba9060326e8ecb2a54e624b8e、Git blob32620e7dafff8bebae575b7c3eb9cf73a1ceb0c9留在b6fa历史及旧工件中，不修改旧工件/marker。既有ORIGINAL_ENGINE_SHA256所指历史源bf69680b7d3e2be8e3c9b6baf8a19ab09972fa501118cc3b0c9aa9045b056f22只作历史来源身份，不拿它声明v2数学仍未变化。活动spy_replay_engine.py原位重构会得到新SHA；源pin、service摘要、candidate报告全部诚实更新为新版本，不伪造保持原hash。
2. 新candidate入口只认新namespace/profile，旧SMA100、旧once异常capture及其任何别名都不能进入。旧SMA100的submit在“找到同ID且digest一致→只读返回”之后、“新claim/新job/数学之前”拒绝，默认不以新内核计算旧profile。不得重新签一个v3 policy exception来借用原capture。
3. 旧GET/原件下载/decision引用按原record、原implementation_digest及ObjectRef继续检验；不把它们强制改成当前loaded hash。b6fa的_verify已经以job原摘要比对报告，_verify_exception会保留protocol原source/runtime身份，这些只读边界应保留。未知旧身份继续明确拒绝/不足，不批量迁移、改写report或自动运行。
4. 合成的legacy-compatible SMA控制只是**新v2工程profile中的控制arm**，用于验证提取后的既有算术，不是旧once任务继续执行、原样本回测或旧profile恢复。旧原件重开证明只读绑定；不能把它当一次新金融结果。

## 5. 新协议、输入与完整身份

独立schema建议`qm.native-daily.candidate.protocol.v1`、`qm.native-daily.candidate.report.v1`，不把旧spy协议从v3宽松解析成任意策略。首次只注册一个固定study，无任意callable/path/上传代码。

协议必须共同绑定：

- study/candidate/strategy version、DoubleMA10/20、全部overlay阈值/50%预算/75%界限、P0/Q0/one-shot/full-exit/终点规则；policy源SHA保持原冻结身份，adapter/kernel为新实际SHA；依赖/数值视图/计算版本。
- 数据raw/normalized bars/action ObjectRef、来源/币种/volume单位/venue语义、日历/version/window、实际可用时间/修订/PIT事实、review refs及scope；不能把“存在一张review”当用途许可。
- 100warmup+21观察仅为首工程窗口；5/10bps合并单边代理与0现金利息明确固定；T、TO、B50、B100、cash五arm共用账务实现和同一终点，B100的100% benchmark cap例外明确登记，不把75%偷偷应用到它。
- 数据用途/暴露/trial ledger refs与schema；当前旧SPY final、d882…及已见历史诊断均为已暴露/已消费。换source/hash不恢复独立性。新独立测试需要实际未看过的时间段、事前sealed protocol和一次release记录；本轮没有这类新集合，也不为其虚拟日期或hash。
- request_digest覆盖protocol/input/代码身份与完整固定arm集合；每arm/scenario子ID再绑定arm和费用设置；report封装原request/protocol/data/code digests、account/action/cancellation/fill ledger及原始完整结果。一次完整成功才发布单一content-addressed对象；局部结果/失败不冒充成功。Full-exit origin与每次attempt身份分别保存。

**真实准入分层：** 复用既有ObjectStore、CalendarService、SourceFacts/ReviewHashes等事实模型及受信审核逻辑；不得直接把SMA100的ReplayInput.verified返回值视为新candidate授权。新candidate的source grant必须明确覆盖这个新candidate/用途/窗口，旧once scope不能转移。首工程profile由内部可信构造且标synthetic；真实分支保持关闭，直到数据owner提供新实际合格对象和相应范围/预算，且新的candidate grant映射接受独立核验。定义真实门禁不表示已经实现或取得真实资格。

最少拒绝矩阵：错误schema/candidate/policy/kernel/hash；old profile/once consumed lineage；fixture冒称real；用途/单位/venue/行动覆盖/可用时点未证；未完成/缺失/重复bar；unsupported split；无记录的新trial/假OOS；负/不可表示账户、numeric mismatch；terminal incomplete；report/request错绑。拒绝发生在claim/math/发布各自最早位置，原件与失败保留，不fallback到fixture。

## 6. 真正最小可审切片与时限

**一个用户动作：** 新的离线固定工程case入口读取内部封存的新协议→由共享v2内核运行→保存/重开合成结果及拒绝原因。没有新route、UI平台或普通真实输入选项。

- **2h目标增量**：活动内核原位拆出一个数量接缝；一例synthetic cash/ex/pay/费用/部分数量案例真实由内核计算；既有SMA控制golden在预声明数值容忍内一致；已保存legacy原件只读重开，旧profile新submit在数学前拒绝。若这些关键RED未转GREEN，不以“新DTO已写完”冒充增量。
- **4h目标可审边界**：一个固定100+21复合fixture，五arm×5/10bps共用唯一循环；stage一次取消/退出origin/终点/精度视图与身份拒绝；新原件ObjectStore绑定及冷重开；最多两轮独立review与有限raw证据，sole publisher再走最终CI。新工件按新namespace在自身离线模块中验证/重开，不塞进旧P2 Catalog或旧ReplayService的报告schema，不新增通用JobStore/Worker。并不承诺到点必然通过，结构失败即缩减。
- **4h明确不含**：真实新源权限/field semantics、真实独立OOS、成本/容量校准、长期样本/统计power、前向paper、public UI/持久JobStore/Worker接线、新currency引擎、自动采集/调参。新的工程数值不称新实证收益或PASS。

2h/4h只从这份新核心范围获批后的**实际实现ACK**起算，不从当前设计ACK假称在实现，也不回填上午已STOP任务或昨日#236时钟。当前唯一在跑的是45分钟封顶的output-only设计任务。

建议未来文件锁：修改spy_replay_engine.py（唯一core）、spy_replay.py（legacy新执行fence/原件兼容）；新增research/native_daily_candidate.py、tools/research/run_native_daily_engineering.py及自身新tests/docs。**不碰**UI锁定的trend_overlay_trace.py、原CLI wrapper、route/API/entry/frontend以及原trend_overlay_candidate.py。锁与实际base在批准后重新核定，不预占source writer。若需ADR，由root在实施时分配实际未占编号，本轮不占0036或任何ADR。

## 7. 风险、不可拆发布与回滚

风险按优先级：共享内核抽取改变旧算术；旧profile在新代码上误执行；旧原件被loaded-source误拒；snapshot数值视图改变临界数量；费用被重复扣；终点/应收被忽略。每项都有上述合成/refusal回归，不用真实旧金融样本“对齐结果”。

core、旧submit fence和新profile为一个不可拆启用单元。默认新入口关闭，只有整组测试/review/CI合格才启用合成入口。若失败，停止新任务并回到已知代码；v2新工件保留且仅按v2身份读，不交给v1执行。旧consumed marker/原件不回滚、不重放；core回退不能自动恢复旧任务的新执行权限。**已有可用的回滚禁用方式**：保持原`--spy-replay-root`供旧记录读取，但移除`--spy-replay-input`，使ReplayService以replay_input=None运行；b6fa submit已在现有ID重开后、新数学前对None输入拒绝（spy_replay.py:1282–1297；workstation.py:2310–2323构造路径）。这只是未来发布配置要求，本轮不操作任何运行配置；不能只退代码却重挂旧输入。

本轮只交设计；没有新WT/依赖/数据/测试/收益/host/model或源码变化。原64MiB保留，不增加资源额度；未来执行前按actual新base核worktree+fixture+失败+输出的总峰，不借旧unknown/UI/server额度。其他UI与发布可以继续，无需等待本设计。
