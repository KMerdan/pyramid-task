# Standalone Pyramid Skill：确定性与复杂度系统审查

日期：2026-10-06。目标：`/Users/merdankiji/localGit/pyramid-task`，本地 main、source 4.2.0（ahead 1，含既有 Observer 未提交修改）。安装控制器仍是 Codex 4.1.0；本报告不把 source 功能当作已安装行为。不操作 Hemkar。

这是源码和 prompt 审查，不是实现或完整产品验收。诊断直接调用真实 Python 函数，在 example-harness-plan 的内存副本上构造负例；没有模拟函数成功，没有修改 canonical 文件，没有执行真实 update/replan/audit，没有运行完整测试套件。诊断结果及源文件 SHA 在同目录 `system-review-diagnostics.json`。现有本地 canonical 为已完成的 PYRAMID-HUMAN-OBSERVER-20261005，r1/G13。

## 结论与第一性原理

系统并不是应消除所有“随机性”。主要问题是：一些可以精确检查的约束仍由 Agent 从文字中记住并执行；一些接口只检查数据存在，没有检查关联关系；一些操作的批准成本与实际变更风险不一致。

职责应分成三层：

- Runtime：输入是否合法、依赖是否可完成、变更究竟是什么、证据是否绑定当前候选、状态转换是否获准。
- Agent：需求含义、方案取舍、测试是否充分、视觉是否可用、异常根因。返回带事实与限制的判断。
- 人/宿主：新权限、实质性的目标或范围变化、不可逆/高影响操作、尚未解决的重大风险。readiness 不能创造权限。

UUID、事件时间、真实外部环境差异不是需要删除的“randomness”。可测试的政策应显式输入时钟/环境；不要伪造真实执行结果来取得确定性。ASD-STE100-inspired 表达有助于统一术语，但不能替代机器约束，也不是正式 ASD-STE100 合规声明。

## 一、已复现的机械缺口

### 1. 验收依赖循环未被拒绝

给两个 work 节点添加互相指向的 integration-requires。runtime validate_plan 与发布 plan schema 都没有报错。两者 implemented、verification pending 时，真实 _audit_prerequisite_errors 分别要求另一方先 verified，构成验收死锁。

证据：scripts/pyramid_graph.py:39；pyramid_core.py:1477、3446。

改进：以 audit 实际采用的前置关系构建 acceptance prerequisite graph，检查环并返回最短可解释路径。包含 validated-by 与父节点对 primary children 的实际验收关系。工作启动 DAG 与验收 DAG 分离；不得把 integration-requires 改为硬启动依赖，否则会重新阻塞合法并行。

验收：双向 integration 环、跨 validation/gate/parent 环必须拒绝；允许合法的“可并行实现、顺序验收”图。

### 2. intent 自我引用被算作需求覆盖

新增 REQ-SELF-ONLY，只放在 intent 节点 source_requirements。runtime 与 schema 都通过；没有新增工作、criterion 或 proof 路径。

证据：pyramid_core.py:1281、1548；graph-contract 当前仅要求“至少一个节点引用”。

这是现有弱契约允许的情况，不是违反 JSON schema；但不能支撑“需求有可验收落点”的产品承诺。改进：覆盖检查需要可追踪的 criterion/proof/gate 路径，不是全图中出现过 ID。排除纯 self/metadata coverage，区分结果要求与政策约束；不要求每个约束独立造一个 implementation task。仍需 Agent 判断该证据是否真正证明需求，不能把结构覆盖当语义充分性。

### 3. replan 的顶层契约变化未进入 diff

保持 nodes/edges 不变，改变 intent.statement、删除 constraints/non_goals。prepare_replan 正常返回；diff 的节点/边变更列表全部为空。TASK-201 的 proof contracts 也与原计划相同。

证据：pyramid_core.py:3819、4355；pyramid_verification.py:155。

确认范围：候选准备/diff 和契约哈希行为已复现；没有执行真实 replan apply，不声称已观察到完成门被绕过。源码的 changed_contracts 主要由节点、关系及 proof contract 变化驱动，顶层政策需明确纳入变更影响规则。

改进：输出完整 changed-field delta，包含 intent、success evidence、constraints、non-goals 及相关 assumptions/decisions。对删除和弱化提供显式结构标记；文字是否语义等价仍要判断。对需要 review/approval 的 apply，绑定 preview 的 candidate digest、当前 context 与确切 review/approval，不只绑定当前图版本。复用现有 amend/expand 的模式，不再建一套批准账本。顶层变化应重新评估相关验收，不应简单让所有共享 producer run 失效。

验收：顶层目标/边界变化必见；预览后修改 candidate 不得套用旧的批准；无关排版变化与真实契约变化分别报告。

### 4. schema 与 runtime 的 result 形状校验不一致

checks 为字符串数组项，而非 check 对象。JSON schema 拒绝，_validate_agent_result 返回无错误。

证据：pyramid_core.py:3049；schemas/agent-result.schema.json。

限制：该 payload 没有通过 update_task 的 proof normalization 或 audit。不能据此断言伪造 proof 可通过最终 gate。

改进：单一 wire-shape 边界与 runtime 语义验证分工；共同形状规则使用正反例一致性测试。schema 负责形状，runtime 负责权限、图关系与 proof freshness，不重复维护两套不一致的形状规则。避免仅为此引入通用大框架。

### 5. 乐观并发观察绑定在公开 CLI 上可省略

update parser 接受既无 expected-guard，也无 expected-version/context 的命令；check_expected_version(..., None) 不拒绝。

证据：pyramid.py:54、60、74；pyramid_core.py:2419。

这不是无锁/无所有权/无生命周期保护，也不是 SaaS 授权漏洞。它意味着 Agent 可以不带“基于哪次观察做决定”的并发绑定。

改进：公开 Agent mutation boundary 要求适用的 scoped guard 或 composite context；内部/legacy 调用有明确兼容策略。恢复走显式受控路径。guard 冲突应重新核查相关事实，不得自动换新 guard 后盲重试。

## 二、需收紧但不应夸大为已复现 bug 的流程

| 领域 | 当前成本或宽松处 | 建议 |
| --- | --- | --- |
| Helper join | job/result/current guard/candidate 的比对写在 prompt；shape test 不证明三方 freshness | 增加纯 reconcile_helper，返回 eligible/stale/advisory/invalid 与原因；不建 helper canonical ledger |
| 查询与错误路由 | Agent 选查询/变更接口；CLI 错误主要是字符串，需再解释 | 基于当前状态输出稳定 reason code、作用域、下一步事实；Agent 决定实际行为。不强制再做一次 inspect |
| Expand vs replan | expand 一律精确批准；replan candidate 绑定较弱 | 按目标/权限/验收/风险变化统一政策。内部拆分和新权限不是同一类变化。现有批准规则改变前不可自行绕过 |
| 并行批次 | orchestrate 要等 batch audits 全部结束再选新 frontier | 以真实依赖、写范围、资源和 active claims 判断；单个 audit blocker 不冻结独立工作，join gate 仍保留 |
| Assurance 范围 | assets/inspection 分组由 Agent 决定，宽泛 scope 可放大失效 | 根据真实 patch、消费者与当前证据生成 fan-out/歧义提示和定向建议；统计阈值不是自动 hard gate |
| 实际修改归属 | changed_files 由 worker 声明 | 在明确 base→candidate 或集成 patch 上核对实际文件；不得把用户整个 dirty tree 的变化归给当前任务 |
| 重试与 review 深度 | 无新证据停止重试等主要是 prose | 用已有 procedure/input/error facts 识别重复无进展，输出诊断/replan 建议。重大语义和隔离判断仍需要独立 review |
| Artifact 保留 | 文件存在/体积不等于可删除 | 从现有 proof/handoff/history 引用决定候选清理集；ownership、停止状态、failure 保留与显式 cleanup authority 独立检查 |

Helper 的具体测试证据：tests/test_helper_contracts.py:138 构造已经 current/eligible 的 envelope，再验证 schema 和固定 snapshot 值。这个测试确实检验形状，不是伪造成功；但没有执行 job/result/current-candidate 的 reconciliation。需新增跨 envelope 负例，不能重命名 shape test 就宣称完成。

并行 barrier、广泛 assurance 与 retry 是源码/规则设计风险，本次没有在真实 host 重放其具体故障。

## 三、真正值得减少的复杂度

1. 不新增第二个 scheduler、authority store 或 plan ledger。复用 canonical state、typed edges、现有 proof 和 event。
2. 减少 Agent 在多个命令间的机械猜选，提供稳定决策事实，而不是再叠一层长指导。
3. 分离公共 envelope、domain validation、store/transaction、projections、CLI 和宿主 delegation。pyramid_core.py 6031 行，history 1718、visualizer 1643；按职责与副作用边界拆，不按任意行数切块。先保持外部接口与状态兼容。
4. Shared schema 有一个所有者；发布仍考虑离线验证消费者。不能盲目把不同语义的同名对象合并成一个。
5. STE-inspired 短句从同一事实生成：condition → actor → action → limit；错误保留 code/scope/evidence/limit。字段少不等于信息足，避免删掉失败或证据限制来节省 bytes。
6. Usage=0 是研究入口，不是删除依据。灾难恢复与低频生命周期操作有低频但真实场景；必须核对场景、替代路径、兼容成本。CLI usage 也没有完整测量纯 skill、direct API 或 Agent 决策次数。
7. 测量决策正确率、重复查询、输出 bytes、阻塞范围与往返数。字节不是 token，历史总量不是某版本优化的因果证明。

## 四、已做对，不应重复开发

- 有 project lock、commit head、scoped guards、proof fingerprints、方向性依赖失效，不是全靠 prompt。
- Source 4.2 inspect 已明确健康普通读取无需每次完整 validate；不能把安装 4.1 的旧指导误认成 source 仍未修复。
- CLI compact 默认；已有 loss-aware response 与完整输出逃生口。
- inspect mode 互斥；没有复现“多个模式冲突”。
- audit-readiness 使用实际 audit 的前置检查，不应另造一套 readiness 逻辑。
- immutable event 和 current state 分开；不需要为减少当前查询上下文重写所有历史为 Git 式 delta。
- helper 只做 ephemeral 执行辅助，canonical mutation 由 coordinator 持有；应补 reconciliation，不应给每个 helper 建任务生命周期。
- 已有 evidence-only/generated 分类，不能把所有报告变化重新等同于 source change。

## 五、如何纳入已讨论的改善方向

不新增一堆 graph tasks；作为现有责任域的 acceptance/regression 要求：

- Domain/schema：验收 DAG、真实 coverage path、shared wire-shape 一致性。
- Replan：完整契约 diff、确切 candidate/review 绑定与定向失效。
- Store/public boundary：mutation observation guard 与兼容/恢复路径。
- Delegation：纯 helper reconciliation、独立工作 continuation。
- Decision/context layer：typed blockers、最小足够查询、当前 packet 与 proof 复用。
- Harness：真实执行 provenance、actual patch 归属与无进展诊断。
- Observer：Board/Flow 展示同一 reason code、真实阻塞与 proof 作用域，不再由前端另猜状态。

这些目前只是审查建议；未应用到候选 intent 或 canonical。建议先以真实负例把边界固定，再做职责重构；否则只是把松散逻辑搬到更多文件里。
