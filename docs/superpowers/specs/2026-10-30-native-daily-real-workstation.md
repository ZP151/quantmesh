# 真实候选闭环设计

用户在/app/research/jobs选固定DoubleMA/包/grant→提交→状态/同成本基准→Reject/Watch→同ID重开。指标：十臂只执行一次，重开零计算/零重复trial，原件下载SHA一致。无包存INSUFFICIENT/not_run。独立于Server256。

复用原页；CLI-only不满足闭环，通用Worker平台超范围。native-daily-v2、candidatev1、数量A、同一cashbook、T/TO/B50/B100/C×5/10bps不变，不重审数学。

六处接线：
1. RealInput仅受信配置注册ObjectRefs（bars/actions/calendar与原始来源/审核），浏览器不传路径/bytes/qualified=true。校验raw价格币种复权、volume单位/历史venue、ex/pay与split处理、calendar/available_at/PIT事实；不新造SIP门槛，PIT未知限制结论。合成EngineeringInput/_checked继续关闭真实入口。
2. 新candidate专属grant绑定candidate+源/用途+包refs+确切窗口/样本角色/暴露+trial额度+批准原件；不可迁移旧SPY once/OOS。复用对象/锁/日志，不复用旧scope的verify_authority。不足/禁止均不计算。
3. 新/api/research/native-daily：GET options、POST jobs(Idempotency-Key UUID)、GET jobs/id、GET artifacts(kind)、POST decision。请求仅package_ref?/grant_ref?/approved_scope_ref?及冻结protocol_ref；首次持久化UUID+requestDigest，再单inflight计算。相同UUID/body读原任务，变体409；grant换UUID不重跑。grant试验占用与intent同一持锁日志写入后才计算，中断不退款、不自动重跑；页面保存UUID、查询真实状态。
4. 保持合成protocol.v1与read_result不变。新真实schema绑定源/数据/grant/样本/runtime/code；只把evaluate的十臂计算提为内部共享函数，合成/真实守卫分别调用它，唯一账本不变。5/10bps仍标未校准代理，同预算同日期完整十臂与对账，不代表金融PASS。
5. 不可变admission.json先于计算；report之后保存research-decision.json，绑定UUID/request/protocol/grant/admission/report SHA，只有Reject/Watch。准入通过不等于金融充分；paper/live=false。无报告的不足决定report=null。
6. 复用ObjectStore、JsonlStore、WriterLease及现有UI的分步/原件下载模式。GET按原refs校验冷读，禁止调用evaluate/CalendarService/取数，重启变interrupted，篡改拒绝。旧SMA/合成ID可读且新提交退休不变。

文件锁：新增research/native_daily_real.py、api/native_daily_real.py；native_daily_candidate.py仅共享计算抽取；api/workstation.py只组合入口。前端新增screens/NativeDailyPanel.tsx、lib/native-daily-api.ts；仅改ResearchJobs.tsx选择器及生成api/client.ts。新增tests/test_native_daily_real.py与NativeDailyPanel.test.tsx；Root锁ADR/iteration/REUSE_MATRIX及issue/plan。不得碰engine/policy/旧once、SPY读路或Server文件。沿用Operate视觉。

离线RED→GREEN：缺包/错grant零计算且存决定；同ID/并发不重复、变体409、换ID不绕trial；受信替身完整十臂对账；中断不重跑/篡改拒绝；禁计算与日历仍冷读同字节。普通页验证提交→状态→报告→决定→同ID重开；替身只证明工程。只查增量，拟24–48h/首增量≤2h；实现另领32MiB、单研究≤8MiB含临时/日志，超限不部分PASS。当前1MiB只设计。

真实验收另行准入：人明确新包refs、来源用途grant、精确100+21会话窗口/样本角色和暴露/trial规则；独立输入审核与现金/仓位/成本/分红对账，再于普通页完成闭环、核原件SHA。无包维持INSUFFICIENT。供审建议：新US.IVV日线/OpenD、新窗口日期待人选，复用USD/美股日历/现金分红规则，避开旧SPY对象；仅提议，不声明来源/grant合格或取数/OOS。

一次批准范围：新真实schema/grant/五接口/页面/决定重开+共享计算抽取，仅离线实现/替身测试。数量A不重审，旧合成/旧ID权限不扩张；数据范围/用途grant及真实运行另批，未定不运行。本轮代码/测试/网络/SQL/试验=0，Goal未达成；STOP。
