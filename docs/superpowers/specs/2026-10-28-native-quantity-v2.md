# 决策页：原生数量策略接缝＋独立 candidate 协议

**建议批准一项新范围：原位版本化既有日线账务内核，使其产生次OPEN模拟fill并驱动趋势policy；新增candidate协议的合成工程闭环。** 旧SMA100 profile转为只读/原ID重开，不允许按旧身份启动新数学。仍不批准真实数据采集/新金融实验、paper/live、付费/依赖或预算扩容。本页是待集中确认的方案，未实施。

依据仅为实际已核commit `b6fa35b7702063a5f04e2910de3f88bf875da8fa`：`spy_replay_engine.run_cashbook/calculate`、`ReplayInput.verified/ReplayService.submit/_verify`、既有freezer、P2 Catalog、原policy与ADR0029。新ACK2026-10-28 14:57:07UTC /22:57:07SGT；45分钟上限15:42:07UTC。

| 路径 | 实际可复用与代价 | 取舍 |
|---|---|---|
| **A 原位扩展现有日线内核** | 把run_cashbook内现有唯一会话循环拆出明确数量请求接缝；保留一处费用/股息应收/cash/shares/mark更新和现有metrics/_reconcile；新增受信policy选择、fill反馈和版本化身份。活动源码hash必然改变，旧profile不能继续冒充旧源码执行 | **推荐。** 有界工程迁移可做；旧数值兼容须由合成golden证明，不能口头保证 |
| **B 已安装vn.py4.5.0/CTA1.4.1扩展** | 原生add_strategy是真实扩展口，可继续承担其既有分钟合成实验；但本接入只固定1950分钟bar及原限价/long-short语义，未证实本候选所需现金股息ex/pay应收、次日OPEN、整股现金/资金上限及同口径对照 | **排除为本候选替代。** 要等价须另补账本/撮合或改变候选规则，违背唯一内核及既定研究对象；不重跑/安装/外查。不是声称vn.py普遍无此能力 |

**A的唯一写账边界。** 每arm只有一个账户状态，所有arms/成本情景调用同一内核实现。会话开始由内核按原公式记ex-date旧持股权益、pay-date进现金；已在t收盘冻结的action于t+1原始OPEN，用只含当时账户/已知历史量的只读快照调用size_at_open；内核复核、不放大允许股数，只在一处按成交名义金额扣一次5/10bps，生成明确标注的OPEN代理模拟fill；on_fill只更新campaign/档位，不能改现金。随后内核收盘mark，再形成下一action。应收可计NAV但不可花；不新增融资/利息/现金结算能力。Decimal-policy与现有float账务须作精确定义、可拒绝的数值边界，禁止用四舍五入买出额外一股；不在此次重写货币引擎。

**取消与终点。** 普通档位一次机会，裁剪余量取消；全退保存原Action身份，后续hold仍清余股，不再加仓。预定最终OPEN必须清完，否则失败/no成功数值报告；终点flat不得建仓或延长窗口。same-day卖出所得不循环买入。raw-close DoubleMA与旧总收益SMA100是不同规则；split/不支持行动拒绝。

**源码与旧原件。** 旧packaged engine SHA `6e8ad80f134b7c1f44bcb4cb7695e784009953aba9060326e8ecb2a54e624b8e` 保留为Git blob `32620e7dafff8bebae575b7c3eb9cf73a1ceb0c9`/历史工件身份，原始历史engine SHA `bf69680b7d3e2be8e3c9b6baf8a19ab09972fa501118cc3b0c9aa9045b056f22`也保持原义；不能再声称活动文件仍同hash。**不复制旧loop到第二模块、也不并行运行新旧cashbook。** 同一活动文件原位重构为native-daily-v2。旧service的新submit明确拒绝；已有ID只读重开/原bytes下载及绑定验证保留，不能重新序列化成新协议。当前_verify已使用job原implementation摘要而非把它改写为当前hash，保留这一点。旧once marker与scope永不迁移/复活。

**新协议与数据。** 独立namespace `qm.native-daily.candidate.protocol.v1`，精确绑定新kernel/policy/adapter源码、配置、10/20及全部档位、窗口/日历、执行时序、成本、T/TO/B50/B100/C对照、数据/行动/审核refs及样本暴露/trial登记；新request/report均新ID和新hash。复用ObjectStore、日历、事实验证及现有指标公式；不让旧SMA100协议通过改hash变成新候选。新profile第一版只开放可信内部synthetic工程输入；真实模式只有新独立审核、明确允许用途且与candidate scope匹配的数据包才能被后续启用，旧d882…及已消费OOS禁止。未见样本现在不存在，不给新收益/PASS。

**最小可审切片与时间。** 一个离线固定工程case → v2协议验证 → 同一内核执行 → 原件结果/拒绝原因。2h目标：现有SMA控制的合成数值兼容、一个数量/费用/股息case及旧记录可读/旧新submit拒绝；4h目标：固定100warmup+21观察、T/TO/B50/B100/C×5/10bps的合成结果，partial/终点及身份拒绝、独立review与有限证据。它不是4h真实金融资格、UI、长期评测、source-use/PIT/容量验证或paper晋级承诺。兼容性失败就保留RED并缩减，不悄悄换预期。

**风险/回滚。** 首要风险是共享账务迁移漂移、旧对象被当前hash误拒、旧profile借新代码重新执行。新入口默认关闭；一个发布切片包含quantity-core、legacy-submit fence和新profile，缺一不启用。回滚只关闭v2并退回已知代码；新工件保留原bytes且不交给v1执行，旧consumed marker不回滚。源码锁/接口/拒绝矩阵见SCOPE-AND-DECISION.md。等待这一项重要核心/协议授权；UI/发布继续，本会话不实施或测试。
