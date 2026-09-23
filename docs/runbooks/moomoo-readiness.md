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

在 AWS 的 Linux SSH 终端中，使用部署环境的 `quantmesh-moomoo` 命令：

```sh
quantmesh-moomoo readiness --symbols AAPL,NVDA --market US --json --timeout-seconds 30
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
这个注册步骤不购买权限。“请先订阅 Basic 数据”本身不能证明需要购买套餐；
必须区分 SDK 订阅缺失与实际行情权限拒绝。

## 后续真实行情验收

在新 AWS 私有站点的 Markets 和 Watchlist 分别进入 AAPL、NVDA。
记录实际来源、会话/延迟状态、至少两个不同的源时间戳，以及图表修订或追加。
价格相同不等于数据停更，应检查源时间。`ready` 只证明能读取有效载荷，
不验证新鲜度、完整历史、实时授权或五秒轮询的持续运行。

保持 Paper 模式、实盘执行关闭；缺失、延迟或休市数据必须显示真实状态。
另行验收原有 BTC/ETH/SOL 路径。24 小时容量观察及恢复演练归入后续运维验收，
不阻塞本地功能开发。CI 暂停期间不推送、合并或部署本切片。
