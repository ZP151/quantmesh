# QuantMesh 中文说明

QuantMesh 是一个本地优先的跨市场量化研究与交易工作台，目标是把股票、加密资产、预测市场、本地量化模型、AI 辅助研究、模拟盘和受控交易执行放进同一条可审计流程。

当前仓库处于 MVP 基础设施阶段。实现重点是快速复用成熟的开源组件，通过稳定的 QuantMesh 适配器集成数据供应商、回测引擎、交易 SDK 和 AI 工作流，而不是全部手动重写。

## 产品范围

- Moomoo 行情和模拟交易
- Hyperliquid 永续合约、现货行情、测试网交易和风险控制
- Polymarket、Kalshi 等预测市场数据
- 因子模型、技术策略、机器学习和事件概率模型
- 本地 AI 研究、新闻分析和交易决策解释
- 统一回测、模拟盘、组合风险和审计日志

大语言模型不会拥有无限制的交易权限。AI 可以提出研究方向、解释信号、生成实验和识别异常；订单必须经过确定性的风险检查、仓位限制、流动性检查和执行控制。

## 快速启动

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev,research]"
uvicorn quantmesh.api.app:app --reload
```

启动后访问 `http://127.0.0.1:8000/health`。

## 开源复用策略

QuantMesh 自己维护统一领域模型、连接器接口、风险引擎、编排、审计日志和产品界面。成熟能力优先通过 Python 包、适配器、Git submodule 或隔离的本地服务复用。

适合直接集成的项目：

- Qlib：因子研究、数据集、机器学习流程和回测
- VectorBT：快速向量化实验和参数扫描
- Hyperliquid 官方 Python SDK：REST、WebSocket 和签名交易
- Polymarket 当前 CLOB SDK：预测市场接入
- Moomoo OpenAPI Python SDK：券商行情和模拟盘

适合作为参考或伴随服务的项目：

- Hummingbot：连接器、订单追踪、重连和 Hyperliquid 支持
- Freqtrade：dry-run、模拟钱包、策略生命周期、持久化和风控
- OpenBB：数据供应商注册、数据路由和本地 AI 数据工具设计
- VeighNa/vn.py：gateway/app 分层、CTA、组合策略和机器学习投研
- TradingAgents：分析师、交易员、风险和组合管理 AI 角色编排

详细许可证、集成方式和改造程度见 [`docs/REUSE_MATRIX.md`](docs/REUSE_MATRIX.md) 和 [`docs/REFERENCE_PROJECTS.md`](docs/REFERENCE_PROJECTS.md)。

## Agent 协作与路线图

Codex 和 Claude 共用 [`AGENTS.md`](AGENTS.md) 中的仓库协作协议，各自的平台资源和项目级技能位于 `.codex/` 与 `.claude/`。完整产品路线记录在 [`docs/roadmap/ROADMAP.md`](docs/roadmap/ROADMAP.md)，每轮可追踪记录位于 `docs/iterations/`。

创建下一轮可写迭代记录：

```powershell
quantmesh-iteration "Paper Trading Kernel" --owner "your-name" --status active
```

## 安全默认值

- 默认启用模拟盘和测试网。
- 实盘交易必须显式开启。
- 密钥只能从本地环境变量或系统密钥存储加载。
- 私钥、签名和原始账户凭据不得发送给 AI 模型。
- 每个信号和订单应保存输入数据、模型版本、风险检查和执行结果。

## 迭代路线

1. 完成领域模型、本地配置、健康检查和内部模拟连接器。
2. 完成带手续费、价差、滑点、现金、持仓和审计记录的确定性模拟撮合。
3. 接入 Moomoo 行情和模拟交易。
4. 接入 Hyperliquid 行情和测试网执行。
5. 接入 Polymarket 和 Kalshi 概率数据。
6. 接入 Qlib/VectorBT，建立动量、均值回归和风险平价策略。
7. 加入概率校准、组合风险和模型失效检测。
8. 加入本地 AI 研究助手。
9. 通过模拟盘晋级门槛后，再开放受控实盘交易。

## 免责声明

QuantMesh 是软件工程和量化研究项目，不构成投资、法律或税务建议。回测结果不代表未来表现，真实交易可能导致部分或全部本金损失。
