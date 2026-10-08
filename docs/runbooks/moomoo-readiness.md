# Moomoo/OpenD 私有行情就绪检查

用于迭代 0037 的只读连接预检。它不解锁交易账户，不下单，也不代表
AAPL/NVDA 的 AWS 实时图表已经验收。

## 在正确的机器上执行

先在运行 OpenD 的主机检查本机连接，再在 AWS 主机检查其配置的私有端点。
Windows 本机通过不能证明 AWS 已经连通；AWS 的 `127.0.0.1` 也不指向 Windows。
保留 OpenD 私有入口，不开启公网端口或 Funnel。

Windows PowerShell（安装 QuantMesh 的 Python 环境）：

```powershell
Get-NetTCPConnection -State Listen -LocalPort 11111 -ErrorAction SilentlyContinue
python -m quantmesh.moomoo.cli readiness --symbols AAPL,NVDA --market US --json --timeout-seconds 30
$LASTEXITCODE
```

在 AWS 的 Linux SSH 终端中，使用部署虚拟环境的绝对路径，无需激活环境：

```sh
/opt/quantmesh/current/.venv/bin/quantmesh-moomoo readiness --symbols AAPL,NVDA --market US --json --timeout-seconds 30
echo $?
```

Linux 的 `systemctl` 必须在 Linux 主机执行，不能复制到 Windows PowerShell。
如需在 PowerShell 使用 curl 参数，请调用 `curl.exe` 并传入普通 URL，
不要粘贴 Markdown 链接语法。

## 读懂报告

| 状态 | 含义及下一步 |
| --- | --- |
| `route_unavailable` | TCP 未连通；先检查 OpenD 是否运行、监听地址和私有路由 |
| `sdk_missing` | 缺少经项目审计的兼容 SDK；不要随意升级供应商依赖 |
| `auth_required` | 行情请求被认证状态拒绝；命令没有尝试解锁交易 |
| `unavailable` / `partial` | 全部或部分报价/日线请求不可用；检查对应 symbol 的状态 |
| `protocol_error` | 返回结构、身份、周期或调整方式不可信；不要作为有效数据使用 |
| `timeout` | SDK worker 超过期限，已停止；TCP 预检和清理时间另计 |
| `ready` | 每个请求的 symbol 都有结构有效的报价和至少一行日线 |

退出码：`ready=0`，认证问题 `2`，SDK 缺失 `3`，其他失败/部分可用 `1`。
报告只保留安全诊断，不输出原始供应商错误或账户数据。临时文件仅包含连接
元数据和脱敏报告，结束后删除。SDK worker 默认期限 30 秒，最大 300 秒。

报价读取前会注册 SDK 的 QUOTE 订阅，并关闭向 Python 推送。
逐笔轮询同样先注册 TICKER；应用仍按五秒轮询，不代表逐笔推送。
这个注册步骤不购买权限。“请先订阅 Basic 数据”本身不能证明需要购买套餐；
必须区分 SDK 订阅缺失与实际行情权限拒绝。

## 已验证的私有路由与待发布配置

2026-09-23 已验证：Windows OpenD 只监听 `127.0.0.1:11111`；通过
Tailscale SSH 把 AWS 的回环端口转回本机。保持 Windows、OpenD 和隧道运行。
现有隧道运行时不要重复启动。断开后可在 Windows PowerShell 重建：

```powershell
tailscale ssh ubuntu@quantmesh-staging-8gb -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 127.0.0.1:11111:127.0.0.1:11111
```

这个窗口会一直运行；退出会断开隧道。若要求身份复核，使用本次命令实际返回
的验证链接。`tailscale ssh` 自动校验协调服务提供的主机密钥。不要禁用校验、
修改 OpenD 为公网监听或为此新增公网防火墙规则。当前隧道未设为开机服务。

以下为最初候选部署步骤；当前 PR #163 已部署 SDK、股票 watchlist 和分钟图。
部署脚本的
`--live-market-data --moomoo-market-data` 组合会使用 `requirements-audit.txt`
约束安装已有 `[moomoo]` extra，并设置 US AAPL/NVDA、回环端口和五秒轮询。
默认仍不启用 Moomoo；`--activate-existing` 从保留版本恢复其原配置，不能混用
创建配置的选项。发布须待 CI 恢复且审核通过，使用合并后的精确提交。

Linux SDK 在导入时需要真实用户目录；就绪 worker 会恢复被隔离环境清理的
标准 HOME 值，不传入凭据。供应商 SDK 仍会在用户目录生成其自身诊断日志；
不要将这些原始日志直接上传或贴入对话。CLI JSON 仅输出脱敏报告。

验收分开记录：最初 AWS 独立候选证明报价、日线和两轮逐笔读取；PR #161/#162
随后完成真实源连通与列表显示。PR #163 已接入供应商常规时段真实分钟 K 线，
不能用报价通过代替图表动态验收。

## 后续真实行情验收

在新 AWS 私有站点的 Markets 和 Watchlist 分别进入 AAPL、NVDA。
记录实际来源、会话/延迟状态、至少两个不同的源时间戳，以及图表修订或追加。
价格相同不等于数据停更，应检查源时间。`ready` 只证明能读取有效载荷，
不验证新鲜度、完整历史、实时授权或五秒轮询的持续运行。

保持 Paper 模式、实盘执行关闭；缺失、延迟或休市数据必须显示真实状态。
另行验收原有 BTC/ETH/SOL 路径。24 小时容量观察及恢复演练归入后续运维验收，
不阻塞本地功能开发。2026-09-24（新加坡时间）用户已批准恢复 CI，
检查全部通过后合并部署；仍须记录精确提交与实际部署/页面证据。

## 2026-10-08 分钟图发布验收 / Minute-chart release acceptance

Release `69515b7` (PR #163) is checked, merged and deployed. Both stocks now
render actual provider minutes through Markets/Watchlist, with private source,
observed coverage and local sequence labels. Closed-session OHLCV/reload and
crypto regressions pass. October 8 regular-session API/browser witnesses also
pass actual revisions, two new minute appends and source-matching OHLCV.

在私有站点 Markets 或 Watchlist 点击 AAPL、NVDA，选择 1D 和 Line，可看到
已采集的真实 1m 走线图。首次发布后验收发生在收盘之后；股票源时间停在收盘、
年龄增长并显示 Stale 是正确行为。请勿把页面刷新时间当作行情源时间。
2026-10-08 13:56–14:03 UTC（新加坡 21:56–22:03）的真实开市验收已通过：
两股票同分钟修订、13:58→13:59→14:00 连续追加、刷新保留 30 条已收盘分钟，
以及最近四条已收盘 OHLCV 与供应商前后采样一致。四个股票入口及 BTC/ETH/SOL
图回归通过。原始供应商标签保存在 API live_lineage.provider_time_key，
sequence_origin 明确为 local-observation；页面显示私有许可与本地序号限制。
OpenD 和私有隧道须保持运行；缺 bid/ask 时纸交易仍阻断。

## Windows 登录后启动与私有重连

`deploy/windows/opend_recovery.ps1` 复用现有 GUI 和同一条私有隧道。它不读取
OpenD 配置、密码、账号、日志，也不修改供应商的 Remember Me/Auto Login。
启动程序不能证明已登录或有实时权限；需要登录时由用户打开供应商界面完成。
原生只读检查如下，不会启动或停止任何 GUI/隧道，也不写入状态目录：

```powershell
powershell.exe -NoProfile -NonInteractive -File deploy/windows/opend_recovery.ps1 -Once -ObserveOnly -OpenDPath C:/Users/15492/AppData/Roaming/moomoo_OpenD/moomoo_OpenD.exe -TailscalePath "C:/Program Files/Tailscale/tailscale.exe"
powershell.exe -NoProfile -NonInteractive -File deploy/windows/install_opend_startup.ps1 -Status
```

PR #164 已通过检查并合并为 `c4ebee4`，2026-10-08 已安装当前用户启动配置。
隐藏 helper 保持运行，重复启动退出 0；现有 OpenD 和原私有隧道保持正常。
安装器只写当前用户 `%LOCALAPPDATA%/QuantMesh/OpenDRecovery` 和 Startup 中
`QuantMesh OpenD Recovery.lnk`。不创建管理员服务、不改变执行策略或公网入口。
已有 OpenD/隧道保留；远端监听状态无法确定时等待，避免重复创建转发。
状态会区分 `needs_opend_login`、`needs_tailscale_or_ssh` 与实际已有的私有隧道。

Configuration acceptance passed with exact merged scripts, shortcut/digest
readback and duplicate suppression. Next-login and a real outage recovery
remain pending. Source authentication is still the vendor's UI responsibility;
starting the GUI does not prove remembered login or real-time entitlement.

安装器 `-Uninstall` 只移除校验为本工具所有的项目。若 helper 正在运行，先
移除登录启动快捷方式，返回 `startup_removed_cleanup_deferred` 并保留程序、
状态和连接；停止后的再次卸载才清理其文件。拒绝修改外来文件/替换快捷方式/
目录链接。下一次真实 Windows 登录与网络断线恢复仍须单独留证；本任务不
重启 Windows、退出用户或切断现有源连接来制造验收结果。
