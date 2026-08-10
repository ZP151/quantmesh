# QuantMesh 中文说明

> 面向个人量化研究者的本地优先、多市场研究、实时看盘与确定性模拟交易工作站。

**状态：** 预发布 · 仅本地 · 模拟盘优先 · 支持 English / 简体中文 · 禁止自主执行

QuantMesh 将股票、加密永续合约和预测市场放进同一条可检查的工作流：查看有来源的数据，确认其新鲜度，研究假设，在模拟盘中演练决策，并在之后回放和审计结果。

英文主文档见 [README.md](README.md)。产品边界见
[产品战略](docs/product-strategy.md)，当前实施状态见
[ACTIVE.md](docs/goals/ACTIVE.md)。

## 当前可用能力

| 模块 | 能力 | 真实性边界 |
| --- | --- | --- |
| 本地工作站 | 一条命令启动的 React/FastAPI 回环应用 | 不作为云端或托管服务暴露 |
| 演示模式 | 可重置、确定性种子数据和模拟账户 | 演示/合成数据始终明确标识 |
| 市场与研究 | 股票、加密、预测市场、自选、研究与预测页面 | 始终显示市场、来源、时间和新鲜度 |
| 模拟交易 | 模拟下单、持仓、盈亏、风控、熔断和审计 | 确定性模拟内核是唯一订单权威 |
| 实时研究 | 可选的只读连接器、健康检查和回放演练 | 数据缺失或过期时真实显示为不可用 |
| 偏好设置 | 中英文和系统/浅色/深色主题持久化 | 偏好仅存于本地浏览器 |

## 快速启动

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,research,e2e]"
quantmesh-workstation --demo
```

打开 <http://127.0.0.1:8765/app/>。首次启动会创建带清晰标识的确定性本地演示数据；它不会向外部市场发送订单或凭据。

## 可选只读实时模式

只有在设定有限观察列表后才启动实时模式。它与确定性演示模式分离，并且保持只读：

```powershell
$env:QUANTMESH_LIVE_WATCHLIST = "BTC,ETH,SOL,HYPE"
quantmesh-workstation --live
```

接入可选的 Moomoo 或预测市场数据前，请先阅读
[实时驾驶舱操作清单](docs/runbooks/live-cockpit-operator-checklist.md)。

## 产品工作流

```text
观察有来源的市场证据
        ↓
检查市场 · 时间戳 · 序号 · 数据年龄 · 新鲜度
        ↓
研究 / 预测 / 比较假设
        ↓
确定性风控检查与模拟下单决策
        ↓
持仓 · 盈亏 · 风险 · 审计 · 回放
```

实时、延迟、过期、断开、回放、合成数据必须在界面上明显不同，不能伪装。

## 安全边界

- AI 可以总结证据、质疑假设和提出实验建议；不能签名、下单、撤单或调整仓位。
- 默认是模拟盘。主网签名、真实资金交易和钱包托管不在当前产品边界内。
- 所有订单路径必须经过确定性风控、报价围栏、仓位限制、熔断和审计记录。
- 密钥必须留在本地；不要把私钥、券商凭据或已签名载荷放进提示词、提交或 Issue。

在修改执行相关能力前，请阅读完整的
[威胁模型](docs/threat-model.md) 和 [发布流程](docs/release-process.md)。

## 当前路线

| 阶段 | 目标 |
| --- | --- |
| 当前 | 可复现实验到模拟交易工作流、全局偏好与完整 SPA 多语言 |
| 下一步：0019 | 有边界的实时研究面板：报价/盘口/成交/概率、真实新鲜度、紧凑图表和确定性回放 |
| 量化研究实验室 | 特征、回测、Walk-forward、模型注册和完整血缘 |
| 组合与风控 | 跨市场暴露、相关性、限额、回撤和对账 |
| AI 研究助手 | 有来源引用的分析、质疑和风险审查输出 |
| 受控执行 | 仅在独立批准、模拟/测试网门禁、幂等和对账演练之后考虑 |

下一轮的可执行范围见
[iteration 0019](docs/iterations/0019-live-research-surface.md)。

## 开源复用

QuantMesh 自己维护统一领域模型、数据来源/新鲜度语义、模拟交易内核、风控、回放证据和产品工作流；成熟能力通过适配器复用：

- Qlib、LightGBM、scikit-learn：研究、因子和模型实验；
- 官方市场 SDK：可审核的行情及模拟/测试网适配器；
- DuckDB、Parquet：本地研究数据湖与可复现回放；
- React、Vite、部分 shadcn/ui：本地操作工作台；
- Hummingbot、Freqtrade、OpenBB、VeighNa、TradingAgents：设计参考，不复制其执行权限。

许可证、所有权和改造决策见 [开源复用矩阵](docs/REUSE_MATRIX.md) 与
[参考项目说明](docs/REFERENCE_PROJECTS.md)。

## 开发与验证

```powershell
python -m pytest
ruff check .

Push-Location frontend
npm ci
npm run lint
npx vitest run
npm run build
Pop-Location

python tools/build_frontend.py --check
```

发布候选版本时，必须执行文档中的干净检出发布门禁；本地一次测试通过不等于发布证据。

## 免责声明

QuantMesh 是量化研究与软件工程工具，不构成投资、法律或税务建议。回测、预测和模拟结果不保证未来表现；真实交易可能损失部分或全部本金。
