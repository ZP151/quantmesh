# 待批准：历史只读查询的隔离内存辅助区

已证：原读取在真实1GiB/2GiB配置下未完整返回111×17；独立观测得到结构化errno30，OPEN_FILE仅文本匹配，实际目标OTHER_UNKNOWN。所有本次进程已关闭。不能宣称TEMP已定位、损坏已证明或该方案必成功。

选定Source方案B的更窄写权限实现：原DB/WAL及运行时代码保持操作系统只读，原LiveBuffer read_only=True、原SQL/字段/NULL/rawJSON/排序/去重/调用者事务及数学不变。新增唯一写位置为0700/noexec、硬限256MiB、明确noswap的私有tmpfs内存辅助区；engine temp0改为256MiB并绑定该固定路径。所有辅助页、守卫、API/参考进程均计入现有2GiB进程组硬限，不新增RAM上限、机器、依赖或付费资源。无法证明tmpfs配额、noswap、进程组记账时数据前停止，无磁盘辅助区回退。

只选原库复用路径；不授权复制约7.42GB数据，不授权停止生产写入者、修改原库权限、溢写磁盘、采新数据或启动策略回测/Paper/实盘。原库当前尚未达到不可变输入准入。

先离线实现和定向复核：独立fresh-exec只读守卫PID持有实际内核全文件读锁，跨预hash→普通历史API→Product正常关闭→独立a355全量原件/数学核对→posthash→守卫正常关闭。不能只看连接对象存活；守卫自身不能再开关同inode fd。必须证明实际锁/FS支持、相同DB/WAL/recovery generation与窄查询依赖、相关写入者遵守锁、无路径替换及非合作/WAL单独写入。已有写入者阻挡或任一证明缺失，数据前停止；不暂停或挑战它，不新建快照服务。连接成功/stat/只读挂载不算证明。

实现范围限只读连接的默认关闭私有profile、相关测试和既有私有控制器；默认128MiB/公共API不变，HTTP不可选择内存/目录。新profile不继承失败的旧1GiB opt-in资格。必要代理审阅、精确CI、正常合并/merged-source核对后，实际门通过才做一次原普通历史API验收；不另行warmup/原始资格/原因查询。非200、不完整、配额/超时或关闭失败即终止，无权限、RAM、SQL或匹配器自动扩张。

200后串行独立a355核对所有111条×17字段及完整数学/报告/APIbody，不能共享Product取数器/预期结果；所有进程正常关闭、独立关闭证明、DB/WAL/Paper/真实时钟不变，才能达到原Goal。1MiB M1/browser完整artifact上限不改；S/R实际大小和解码峰未知，必须实测计峰，超出只能拒绝，不能截断/采样/digest代替。

资源：旧失败和所有fullholds保留，现有v6总上限10.5GB/远端4.5GB、各机50GiB空闲底线不变。原库复用成立时已有固定草案为远端295MiB/本地140MiB，仍须加入守卫/hash/配额元数据/全部原件/STORED/临时重叠/关闭/余量并在执行前完整实算。当前账本含本审批材料新1MiB后G9,209,471,066/P3,837,244,430；未预留未来实施/执行，无已通过的容量准入承诺。若完整预估不能容纳，先给具体缺口，不能盲复制或隐式涨额。

依据：Source DECISION18e57c998f23931de700a08fad83e790115cf1bdba6880c13c74625d8fada7ba；GUARD-FEASIBILITY aa1f8f67a991a17c56b2904427169df913fe98de9a628a77b3e0978c70179c3a；Server readiness8fe47f810d02e2cc27efd29e8b9a9be0bafe3c5025933509e7a71fdd6bce274a；最终cause executive2f4c19a036e88ff0115bd6b1be4a81ac0534200df32131e07374a7af86bdb98e。现阶段只申请这项架构设计批准，尚未实施或获准实际辅助写入。旧Goal保持完整且未完成。
