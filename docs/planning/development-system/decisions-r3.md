# r3 决策：Exact Context at Right Timing

日期：2026-10-06。目标仅为 Standalone Pyramid Skill source（local-canonical），不是 Hemkar 或已安装插件。用户授权本次更新候选 intent/tasks；没有授权 archive/reset、开始实现、安装、提交、推送或部署。

## 核心与边界

Exact Context at Right Timing 是接口设计与验收约束，不只是缩短输出：

> 在具体决策前提供充分、相关、当前有效的事实。复用有效上下文；只补充缺失或变化部分。必要细节可追溯获取。未知、失败和权限限制不能被摘要隐藏。

用户选择改善 memory 行为，不做 memory 平台。复用已有 packet、handoff、decision、history、procedure 和 source references。索引只作为可重建派生视图；语义检索只提议候选。不得建立第二份状态、权限或验收权威，不自动采集全部聊天/工具历史，不依赖新向量/图数据库。

## 六个责任域 → 既有任务

| 责任域 | 既有 owner | 新增验收重点 |
| --- | --- | --- |
| 上下文交付与续接 | TASK-821；TASK-824 公共集成 | 短索引→选中详情→核查来源；相关/无关变化、丢失上下文、跨项目和缺失来源；无 memory 平台 |
| 确定性契约 | TASK-841/842/843；TASK-813 公共集成 | mutation observation binding；验收 DAG；非 self-only coverage；shape/runtime 一致性 |
| 变更与审批 | TASK-822；TASK-824 公共集成 | 顶层目标/约束/non-goals 完整 diff；确切 candidate/context/review 绑定；按风险而非命令名重复请求批准 |
| 执行、证据与协作 | TASK-811/812 原有契约；TASK-823/824 | 真实执行与语义判断分开；三方 helper reconciliation；局部 blocker 不冻结独立工作；最终集成 gate 不削弱 |
| 人类观察 | TASK-831 | Board/Flow/public decision 同一原因和范围；criterion 下的代表截图；实现/验证/接受分别报告 |
| 架构与 artifact 生命周期 | TASK-841/842/843、832、834 | 按责任拆分，保留单一发布；checkpoint 控制增长，保留引用及失败；指南只维护一个所有者 |

CONTRACT-801 确认接口/风险/context 矩阵和 mapping，TASK-802 复用共享真实 harness，TASK-833 在真实宿主和工程师场景验证总成本/正确性。不新增节点或 gate。

## 五个可复现问题如何验收

[诊断结果](system-review-diagnostics.json) 是真实源码函数的内存负例，不是已通过的产品证明：

1. acceptance cycle：TASK-842 使用实际 audit prerequisites 检查验收环；不得把所有 integration edges 改成 hard start。
2. self-only coverage：TASK-842 检查 criterion/proof/gate 路径；结构合法不等于语义充分。
3. replan 顶层 delta：TASK-822 定义契约差异与绑定；TASK-824 用公共 apply 路径验证。顶层政策变化重新评估受影响验收，而非使所有 producer run 无条件失效。
4. malformed check：TASK-843 独立验证 wire-shape；TASK-842/813 接入现有公共运行边界。避免让 TASK-843 反向依赖 TASK-842，形成新的验收环。
5. optional guard：TASK-841 定义公开 mutation 绑定与明确兼容/恢复策略；TASK-813 验证 CLI。锁、ownership、lifecycle 本来存在，不能把此问题写成全面无保护。

原有允许/拒绝和历史兼容要求继续保留。上述已确认无效输入的拒绝是明确的行为修正，不能将 baseline 接受错误输入当作必须保留的兼容性。

## 审批与 blocker

- Runtime 检查机械关系与身份。Agent 判断需求意义、测试充分性和视觉质量。
- 人/宿主保留新权限、实质目标/范围/验收变化、不可逆/高影响操作与重大未知风险的决定。
- ready、memory、receipt、guard 都不创造权限。
- can-implement、can-verify、can-accept/release 分开。blocked scope 来自真实依赖、claim、写范围和资源，不来自整个 batch 或一个可选工具不可用。
- 一个边界只保留一个确切 pending need。普通授权内失败应诊断/修复；无新证据的重试不能持续，也不自动升级为人类审批。

## Harness 与评测

复用原 3 个累积 gate：

- GATE-810：真实公开 repair/refusal 旅程，加机械契约负例。
- GATE-820：继承前一旅程，验证上下文续接、目标差异、candidate 绑定、helper 汇合和独立继续。
- GATE-830：继承前两旅程，加实际 Board/Flow/image inspection、双宿主总成本、工程师理解和安全保留。

一条充分 procedure 可覆盖多个 criterion。不同观察不是新 test suite。已有 proof 是否复用，由 claim/contract/input/environment/artifact 与当前组合决定；源码变化不能用 bookkeeping 名义隐藏。

记录遗漏关键事实、stale/cross-project retrieval、重复读取、无效往返、审批循环、总实际 input/cache/output、时间和 artifact 成本。包括检索/写入开销。CLI bytes、模块行数和 Agent 模拟人不能代替这些测量。

## 本次变化与状态

- 候选 r2 → r3；23 nodes、16 work、3 gates、3 outcomes、76 edges、18 hard dependencies 保持不变。
- 保留原 intent ID/statement、11 requirements、所有原 acceptance criteria 和 proof；新增 REQ-812 与有界补充标准。
- 原 TASK-811/812 不重写，保留其完整执行/语义分离契约；本次加强对应集成和汇合。
- 尚未实现、运行宿主试点或验收；未把计划校验称为产品通过。
- canonical Observer r1/G13 completed 未改变。安装控制器 4.1.0 与 dirty source 4.2.0 分开。
- 本次 doctor 因需写入 lock/重编译投影而受限，未完成；只读 validate/inspect 成功。没有扩大权限或改用不安全替代。
- r2 exact snapshot 与 review 保留。任何旧 candidate/transition approval 不适用于 r3，必须按新 preview material 批准。
