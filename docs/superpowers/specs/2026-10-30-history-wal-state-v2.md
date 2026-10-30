# 显式 WAL 状态契约 v2：待审批短设计

**结论：建议独立批准这个软件契约切片；当前仅设计，未实现、未批准真实准入。** 它让真正完成 checkpoint、WAL 合法缺失的 DB 能被明确表达；不会把“某次没看见 WAL”升级为稳定输入。服务维护/恢复和 D/E 仍未解决，不能凭本设计停服或重试业务。

现状依据：冻结 v1 schema762ddbb3…要求 snapshot.files 至少2项，含实际 regular RO 的 DB 和 WAL；interface1e90638a…保留 Source/Server 信任分界。Server readiness95a3cd10…判定正常 checkpoint 可使 WAL 消失，现分支将安全拒绝。只保留旧分支无法表达合法缺失；把 WAL 改成普通 optional 则会混淆证据。选择新增有 discriminator 的 v2，不自动探测/降级，不造空文件。

**1. 准确结构与行为差异**

新增私有 admission schema_id=qm.history-ram-aux.admission.v2，profile=isolated-ram-aux-wal-state-v2。共同的 DB pin、nonce/有效期、actor/unit/guard、runtime/catalog、cut/keys/fields 及各门不变。snapshot 明确为 db、wal、dependency_files：

- wal={presence:PRESENT,file:InputFile}：真实 WAL，沿用 regular/OSRO、dev/inode/长度/mtime/ctime/SHA、路径与 held-FD 检查；0字节也只是实际 PRESENT 文件，绝不等于 ABSENT。
- wal={presence:ABSENT,parent:DirectoryPin,basename,absence_receipt_sha256,checkpoint_receipt_sha256}：只允许固定 updates.duckdb.wal 名称；parent 绑定 held 目录 FD 的 dev/inode/mount及路径身份。不得含 file、虚构inode/长度/空内容SHA或伪 WAL FD。DB 至少1项，依赖仍有原有数量上限与完整闭包；不把 v1 的 min2 改成 min1。

所有对象 strict/禁止未知或重复字段、非有限值、分支混杂和重复路径。v2 manifest 对带 discriminator 的 DB/WAL/有序依赖表示作 canonical 摘要；缺失用缺失证据表示，绝不 hash 成“空 WAL”。各 receipt 不互相自包含其 SHA，避免循环绑定。

私有 opener/capability 只按已认证的 schema 分派；没有公共 HTTP/CLI 参数。资源仍为 aux256MiB、aggregate2GiB、reader1GiB/threads1/UTC；普通128MiB/temp0默认不变。原库 OSRO，不调用 writable connect/CHECKPOINT/修复/创建或删除 sidecar；_tail_rows、SQL、逻辑 cut2026-10-23T23:44:01Z、过滤、111键/full17原值/NULL/rawJSON及独立数学均不改。

**2. ABSENT 的正证据与持续条件**

可信 Server/controller 在已成立的全窗无写者/命名空间排除内生成两个完成态 receipt：

A. checkpoint receipt：真实、完成的 checkpoint/clean-close 或等价已验证封存来源证明，绑定确切 DB generation、内容 pin、runtime、实际完成事件与新切点，且没有待应用恢复依赖。不能由“service inactive”“DB只读能打开”“WAL没找到”或自报 checkpointed=true 代替。若拿不到真实来源证据，ABSENT 在打开引擎前拒绝。本设计不授权在原库上补做 writable checkpoint。

B. absence receipt：绑定同 nonce/boot及有效区间、DB generation、固定父目录/mount/名称、依赖闭包与已完成的 no-writer/namespace receipt。用 held parent FD 对单一 basename 作 no-follow 查询，只有确切 ENOENT 可支持该时点的缺失；EACCES/其他错误、symlink（含断链）、异常父目录或未分类恢复 sidecar 均拒绝。读者可见输入命名空间 OSRO，其他 RW 别名仍由原 no-writer 门覆盖。主库锁保留，但不冒称存在“缺失 WAL 的文件锁”。

receipt 仍经根属0444/nlink1可信控制文件 FD、独立 expected-SHA、当前 nonce/PID/start/unit/source/catalog 绑定传递；SHA存在不是证据内容成立。Server 证明 A/B 的真实事件、依赖、排除和全窗连续性；Source 认证传输、分支、实际路径/FD/mount及活动 guard，再在 connect 前后、SQL前后和解码后复核。Source 点检不是 Server 持续机制的替代。只有轮询/前后两次 ENOENT、无事件记录或有监测盲区的 producer 不能签“全窗缺失”。

**3. 失效与收尾**

PRESENT 的 WAL 消失/换 inode/内容变动，ABSENT 出现任何目录项（包括空 WAL）、父目录/mount/DB generation变化、checkpoint/recovery依赖不符、guard/排除/receipt失效，均永久撤销本次 capability；不重开/重锁/自动切换分支或重选 cut。WAL 出现后又消失也不能恢复 epoch 的有效性；producer 必须有能排除或锁存这种变化的无盲区证据，否则先拒绝。

异常返回前撤销 payload并正常关闭 owned reader/parent/input句柄，保留调用者 admission FD 所有权。沿用独立 controller 的结果封存：完整posthash/111x17/oracle/math和正常关闭未全部完成，不对外释放最终报告。ABSENT 不新增写回；只读引擎若要求恢复/创建 sidecar，直接失败，不绕到 RW。停止/恢复 writer 的先后顺序仍是独立操作门。

**4. 版本与审批兼容**

旧 v1 producer/reader 与现存 WAL 分支不变；旧 reader 必须在打开 DB 前拒绝 v2。新 reader 可继续严格验证 v1 PRESENT，但新执行仍须有匹配其实际源码/runtime/catalog的 fresh receipt，不能复用旧运行 pins。v2 的 PRESENT/ABSENT 都用新 schema 与新设计/实际批准/执行 authority；不能把 ABSENT 降成 v1，不能用旧 b737 的256MiB批准替代新行为批准。原资源批准只能作为历史限制依据，不能签出新输入契约。批准未到前，真实 v2 producer 不启用。

未来实现边界仅私有 admission/capability及必要 opener 适配、配套 producer/receipt/schema与目标测试；不接触查询算法、公共产品/API、引擎或数据策略。Publisher/实施者按新 issue/受审计划交付，当前不写 tracked，也不补第三轮旧审计。

**5. 最小 RED/GREEN 与独立 review 计划（尚未运行）**

- 先 RED：v1真实缺失 WAL仍拒绝；v2合法 checkpointed ABSENT 尚不受支持。新增合法 PRESENT/ABSENT 判别和 manifest 后 GREEN。只有自有极小 fixture 可在切点前写入/checkpoint并正常关闭；此后真正只读打开，验证无 WAL 创建、DB不变及普通 API小结果正常。不得对真实原库做该步骤。
- 保留现有 PRESENT/control回归；拒绝缺/伪 checkpoint、错误 DB/nonce/runtime、父目录替换、权限错误/断链、矛盾分支、旧版降级及未列 sidecar。版本错配应在引擎打开前失败。
- 查询/解码期间分别触发 WAL出现、PRESENT消失/替换、guard或absence epoch撤销；要求无 payload、正常关闭且不切分支。出现再消失仍撤销。用有针对性的 mutant 去掉该分支的后置校验应 RED，原实现 GREEN；只证明软件防护，不冒实际持续监控证明。
- 复用受影响旧控制和自有 tiny archive；比较全部原 SQL/_tail_rows/数学边界不变。独立 Reviewer 检查 receipt真实性边界、版本降级、缺失到出现竞态与句柄所有权，Quant reviewer确认 cut/111x17/成本语义不变，Server ACK producer字段可产性。最多 R1+已知修正R2；实际 kernel/no-writer/全窗absence/独立111x17验收另行准入，单元 GREEN不是通过。

**6. 独立未解决项与交付状态**

D=停服/checkpoint/维护/恢复的源DB/WAL/恢复文件正增长上界；E=所有新controller/保护/证据/失败封套的完整高水。二者仍 UNKNOWN；8KiB控制文件、WAL4.2MB、aux256MiB或内存2GiB不能给它们作上界。维护排除、独立有界读者终止/正常恢复、失败恢复对象及数值时间/故障边界也未成立；600秒只是目标，不能向人索取未闭合的笼统停服许可。软件切片不批准服务影响、源写入或新远端预算，也不单独解开真实准入。

需 Root 按这份具体设计集中取得新行为批准后，才可制定有限实现计划；D/E/恢复仍由其独立负责。当前原库/安全/数据/交易/secrets门、全部旧失败和holds保持，真实 Goal UNMET。本任务本地1MiB/remote0已计，不重加退款；现在仅设计，未运行测试/host/DB/SQL/import/Git/实现，交付后 STOP。
