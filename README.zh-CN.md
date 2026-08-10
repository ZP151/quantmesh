<div align="center">

# QuantMesh

**面向股票、加密货币和预测市场的本地优先研究与确定性模拟交易工作站。**

[快速开始](#快速开始) · [文档](#文档) · [路线图](docs/roadmap/ROADMAP.md) · [English](README.md)

<br />

`本地优先` · `模拟盘优先` · `只读实时数据` · `Apache-2.0`

</div>

QuantMesh 为个人量化研究者提供一条可审计的闭环：查看有来源的市场证据，
研究假设，演练模拟交易，并在之后回放和检查结果。

## 为什么是 QuantMesh？

市场证据往往散落在券商终端、交易所面板、预测市场和 Notebook 里。
QuantMesh 将决策流程保留在本地，并让每一步可检查。

- **证据先于行动**：每个实时值都包含市场、时间、序号和新鲜度状态。
- **模拟盘先于资金**：确定性风控、报价围栏、仓位限制、熔断和审计约束订单路径。
- **统一的本地研究界面**：比较股票、加密货币和事件概率，不把合成或过期数据伪装成实时数据。
- **默认可复现**：从可重置的确定性演示开始；本地实时帧可写入回放数据湖。

## 快速开始

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,research,e2e]"
quantmesh-workstation --demo
```

打开 <http://127.0.0.1:8765/app/>。演示模式完全本地、确定性且有明确标识；
不会向外部市场发送订单或凭据。

<details>
<summary>可选只读实时模式</summary>

设置有限观察列表后，再单独启动实时工作站：

```powershell
$env:QUANTMESH_LIVE_WATCHLIST = "BTC,ETH,SOL,HYPE"
quantmesh-workstation --live
```

接入可选 Moomoo 或预测市场数据前，请先阅读
[实时驾驶舱操作清单](docs/runbooks/live-cockpit-operator-checklist.md)。

</details>

## 工作方式

```text
市场数据 / 研究 / 预测
          ↓
市场 · 来源 · 事件时间 · 接收时间 · 新鲜度
          ↓
本地研究工作站与回放数据湖
          ↓
确定性模拟风控检查与模拟下单决策
          ↓
持仓 · 盈亏 · 审计 · 回放
```

不可用、延迟、过期、合成和回放数据在产品中是不同状态；缺失市场值不会被估算后展示。

## 当前能力

- 一条命令启动、仅绑定回环地址的 React/FastAPI 工作站。
- 确定性演示数据、可重置模拟账户、自选和研究页面。
- 本地数据源配置后，可使用带健康状态、新鲜度和回放语义的只读行情连接器。
- 模拟订单、持仓、盈亏、风控、熔断和审计记录。
- 本地持久化的 English / 简体中文和系统 / 浅色 / 深色主题。

## 产品边界

QuantMesh 不是自动交易机器人。

- AI 可以协助研究与质疑，但不能签名、下单、撤单或调整仓位。
- 默认使用模拟盘。主网签名、钱包托管和真实资金交易不在当前产品边界内。
- 密钥必须留在本地；不要把私钥、券商凭据或已签名载荷放进提示词、提交或 Issue。

## 文档

- [产品战略](docs/product-strategy.md)
- [当前迭代](docs/iterations/0019-live-research-surface.md)
- [路线图](docs/roadmap/ROADMAP.md)
- [操作清单](docs/runbooks/live-cockpit-operator-checklist.md)
- [开源复用矩阵](docs/REUSE_MATRIX.md)
- [威胁模型](docs/threat-model.md)

## 状态

QuantMesh 正处于本地原型开发阶段。当前重点是有边界的实时研究面板：
市场指标、证据边界、紧凑图表和确定性回放。长期交接状态见
[ACTIVE.md](docs/goals/ACTIVE.md)。

## 许可证

[Apache License 2.0](LICENSE)

---

<div align="center">

**有来源的证据 → 模拟决策 → 可回放的结果**

</div>
