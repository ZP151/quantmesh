# 云端开发与研究的成本控制方法

核价日期：2026-11-22。本文是可公开的方法说明；全部数值来自公开价目或明确的假设示例，不是任何个人账号的历史费用、利用率、资源清单或已经承诺的部署方案。

## 先控制保留时长，再决定规格

常规开发优先复用本地环境；需要云端联调时，再评估单台机器运行隔离的API与Worker。临时staging按验收窗口创建与删除。独立常驻环境适用于必须持续可用或隔离故障域的场景，但增加固定保留时长。

普通Lightsail实例处于Stopped状态仍会计费，实际删除才结束该实例后续费用；保留下来的独立磁盘、快照或网络资源需要另行盘点。删除前必须有独立可恢复备份；已发生费用不会因删除退回。[AWS计费规则](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-frequently-asked-questions-faq-billing-and-account-management.html)、[删除及残余资源](https://docs.aws.amazon.com/lightsail/latest/userguide/delete-an-amazon-lightsail-instance.html)。

## 假设场景的公开价格比较

以下均假设Linux/Unix通用型、包含公共IPv4、整月保留，美元税前。仅比较计算套餐的公开月度上限，不含税、超额流量、独立存储、外部备份、域名或其他服务；不假设试用额度、个人折扣或免费层资格。2/4/8GB分别是配置规格，不能解释为已测内存占用。[AWS公开价目](https://aws.amazon.com/lightsail/pricing/)。

| 假设场景 | 每月计算套餐上限 | 相对示例基线 | 成立条件与风险 |
| --- | ---: | ---: | --- |
| 两台8GB独立常驻，比较基线 | $88 | 100% | 需要两个独立环境，接受持续保留成本 |
| 一台8GB，API与Worker隔离 | $44 | 50% | 合计峰值能容纳；共享机器有故障和资源争用风险 |
| 一台4GB，小规模受限并发 | $24 | 27.27% | 完成内存、CPU突发和磁盘验证；可能降低吞吐 |
| 一台2GB，最小功能或开发候选 | $12 | 13.64% | 更严格的承载验证；不预设它能运行数据库及完整研究负载 |

这是架构示例的价目比较，不是从任何历史账单推导的个人节省金额。按需窗口应使用拟购买区域和套餐确认后的小时费率：`计算费 = min(月度上限, 小时费率 × 计费小时)`。计费小时包括Stopped保留时段；不要直接把月价除以固定30天后冒充AWS实际小时费率。

## 缩容和合并的准入门槛

在另行批准的验证窗口，记录代表性任务及其输入、并发、运行时长和成功结果。分别测量API、Worker、数据库与操作系统；限制Worker并发、CPU、内存及子进程，保留API响应和磁盘余量。示例门槛可设为整机可用内存至少25%、文件系统空闲至少30%，但这些是待验证的规划假设，不是本项目已经通过的测试。

同时查看CPU原始采样的均值与p95、burst容量是否耗尽、网络与状态检查，不能凭日均CPU低就断定小机器足够。公开Lightsail指标包括CPU、burst、网络和状态检查；客体RAM、文件系统和I/O需有另行采集的证据，配置容量不能替代实际占用。先定义采样周期、时区、缺测率和统计方法，再计算百分位。[官方指标说明](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-viewing-instance-health-metrics.html)。

## 存储、备份与费用提醒

把热数据、可再下载工具、长期证据和恢复密钥分开保管。设置保留规则前，先验证恢复路径和密钥独立保管；不要为省存储破坏唯一合格备份。快照按存储计费，不能按整块名义磁盘容量机械推算；例如仅为演示，20个计费GB的快照以$0.05/GB-month计为$1/月。独立磁盘公开价为$0.10/GB-month。具体增量快照费用要按实际计费存储核对。[AWS存储计费](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-frequently-asked-questions-faq-billing-and-account-management.html)。既有外部存储的付费套餐或固定额度也有成本，不能称为免费。

后续可提议在月预算50%、80%、100%或预测超支时提醒；这些百分比是示例阈值。费用提醒不是实时硬支出上限，启用前应核对当时预算、通知和自动动作的费用及权限。本文没有创建预算、告警、通知或自动停机动作。[AWS Budgets说明](https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-startup-security-baseline/acct-10.html)。

恢复运行、购买资源、部署合并、缩容和删除旧备份均不由本文自动授权。交易默认保持paper模式，AI建议不构成下单权限。

公开示例数据与来源记录：[假设场景 CSV](aws-cost-scenarios-20261122.csv)、[官方来源及假设 JSON](aws-cost-sources-20261122.json)。个人历史账单和实际占用只保留在私有导出中。
