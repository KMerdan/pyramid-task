# Pyramid 开发系统改进 — 候选 intent r3

日期：2026-10-06。对象：**Standalone Pyramid Skill**，`/Users/merdankiji/localGit/pyramid-task`；authority：`local-canonical`。不是 Hemkar Service/CLI/Skill 的计划。

本包是用户要求生成并补充的候选，未领取、实现或验收。规划生成时 canonical 是已完成的 `PYRAMID-HUMAN-OBSERVER-20261005` r1/G13；保留 dirty 源码、pending code binding 和 baseline r4。未改 canonical plan/state，未执行 archive/reset、安装、部署或清理。用户随后授权提交和推送本规划记录；Git 发布不激活候选，也不授予实施或安装权限。

本目录是可提交的规划快照，不是新执行 worktree 或第二份 canonical。以下 Git、版本、路径和转换 hash 均为生成时观察；激活前必须重新检查、preview 并取得确切批准。主 checkout 为 `/Users/merdankiji/localGit/pyramid-task`；上一轮已完成的 `dev/improvement` worktree 保留在 `/Users/merdankiji/localGit/pyramid-task-improvement`，本次没有重用其旧 canonical。

## Intent 与范围

`PYRAMID-DEVELOPMENT-SYSTEM-20261006`／`INTENT-800`：Agent 安全推进开发，实际执行检查与当前候选绑定；上下文、规格/replan 和协作有界；工程师理解结果与风险；artifact 生命周期可控；整体正确性、成本与可理解性得到真实评测。

r3 保留 r2 的全部 11 项 requirement、约束和 non-goals，包括：
- **REQ-810**：按职责与变化边界拆分 runtime/schema；薄 facade、无 cycles、一个 guarded publication，保留公共 API 与历史契约。
- **REQ-811**：对全部 CLI/skills 给出 actor、trigger、effect、替代与恢复理由；简化默认引导，不按零计数删除。
- **REQ-812**：Exact Context at Right Timing 是系统约束。按当前决策提供充分事实；复用有效 context；按需读取细节；相关变化只失效受影响范围；明确缺失事实。不引入 memory 平台或第二份 authority。

[r3 决策与责任分配](decisions-r3.md) 将六个改善领域落实到已有任务：context 交付、确定性契约、变化与审批、执行与证据、人类 Observer、架构与 artifact 生命周期。新增 24 项验收标准，未新增节点、边或 hard dependency。

现在为 **16 个工作节点、3 个累积 outcome、3 个联合 gate、1 个 intent**，共 23 节点／76 条边。所有完整验收标准、scope、输入、procedure 和观察通道只在 [candidate-plan.json](candidate-plan.json) 维护，本页不复制第二份任务账本。

## 实际分析依据

[架构与使用审计](architecture-and-usage-review.md) 包含第一性原理、全部 26 个 CLI/18 个源码技能的场景、合并/保留边界、模块/schema 目标与未知项。

- [usage-audit-30d.json](usage-audit-30d.json)：5,693 次记录，实际覆盖 2026-09-27 至 10-05。inspect 占调用 59.4%、输出字节 62.9%。7 个零计数命令不能直接判为冗余。
- [source-inventory.json](source-inventory.json)：12 个 Python 脚本，13,210 行；core 6,031、history 1,718、visualizer 1,643、assurance 1,143。含 exact dirty-source 文件 SHA、AST 函数规模与直接 imports。
- CLI 审计不测 skill/API 次数、调用顺序、项目、agent latency 或 model tokens。非零退出不自动等于 bug。历史 4.0/4.1 输出不是当前 4.2 candidate 的性能结论。
- 本地已存在 compact、selected assurance、证据复用与 Board/Flow；改进其边界与公共工作流，不重做既有功能。旧 native 4.1 pilot 没有建立 token savings，不能用 stdout 代替收益。

## 三个累积可用结果

| Outcome / gate | 可验证结果 | 新工作 |
| --- | --- | --- |
| OUTCOME-810 / GATE-810 | 模块边界与 schema 保持兼容；真实 skill 入口经历失败、修复、实际执行和独立验收；错误候选不能通过。 | CONTRACT-801、TASK-802、811、812、841、842、843、813 |
| OUTCOME-820 / GATE-820 | 前述仍成立；精确 replan、必要上下文、场景化路由、隔离协作和组合验收可用。 | TASK-821、822、823、824 |
| OUTCOME-830 / GATE-830 | 前述仍成立；工程师理解 Board/Flow/proof，安全管理 disposable artifact，双宿主真实评测支持完整结论。 | TASK-831、832、834、833 |

这是累计验收关系，不是所有实现都串行的阶段。最终 intent 复用 GATE-830，不新增第四个 gate。

## 任务索引

| ID | 交付 | 开始时实际需要 | 验收的组合输入 |
| --- | --- | --- | --- |
| CONTRACT-801 | 接口、架构/schema 所有权、场景与评测契约 | 当前证据 | 自身 proof／上级 gate |
| TASK-802 | 真实 harness、冻结基线和宿主/成本资格 | CONTRACT-801 | 自身 proof／上级 gate |
| TASK-811 | 受控 procedure 执行与记录 | CONTRACT-801 | 自身 proof／上级 gate |
| TASK-812 | 执行与语义验收分离 | CONTRACT-801 | 自身 proof／上级 gate |
| TASK-841 | canonical 存储、锁、发布与身份边界 | CONTRACT-801 | 自身 proof／上级 gate |
| TASK-842 | 生命周期、查询、投影和 history/assurance 模块 | CONTRACT-801、TASK-841 | TASK-843 |
| TASK-843 | schema 所有权、重复定义和离线兼容 | CONTRACT-801 | 自身 proof／上级 gate |
| TASK-813 | 薄 CLI、决策入口与实际检查集成 | CONTRACT-801、TASK-842 | TASK-811、TASK-812、TASK-802、TASK-843 |
| TASK-821 | 按决策交付充分上下文、有效复用与按需细节 | CONTRACT-801 | 自身 proof／上级 gate |
| TASK-822 | 完整 intent delta、精确 replan 与统一变化风险策略 | CONTRACT-801 | 自身 proof／上级 gate |
| TASK-823 | 隔离协作、确定性 helper reconciliation 与局部 blocker | CONTRACT-801 | 自身 proof／上级 gate |
| TASK-824 | 重复开发工作流和技能路由集成 | TASK-813 | TASK-821、TASK-822、TASK-823、TASK-802 |
| TASK-831 | Observer 分层、Board/Flow 和共享 proof inspector | CONTRACT-801 | TASK-813、TASK-824 |
| TASK-832 | 引用感知的 artifact 保留与受控清理 | CONTRACT-801 | TASK-811、TASK-812 |
| TASK-834 | 整体集成、文档与双宿主包身份 | TASK-824 | TASK-831、TASK-832 |
| TASK-833 | 真实宿主、工程师和系统收益评测 | TASK-834、TASK-802 | 自身 proof／上级 gate |

三项新增架构任务处理独立失败边界：
- **TASK-841**：存储/锁/atomic publication/scoped identity。真实独立进程 race、stale guard、publication interruption/recovery；不是 mocked-success。
- **TASK-842**：消费 store 接口后拆 use cases、validators、queries、projections 和历史职责；无反向 facade import、复制实现或新 giant module。保留单独的 append-only history 链。
- **TASK-843**：盘点全部 31 schema；初次修改只覆盖观察到重复的六个 envelope schemas 与共享定义，其他语义变化需 scoped replan。plan/expansion 的同名定义存在差异，不盲目合并。正/反例 runtime/schema 一致，包内离线解析。

已有 TASK-813 拆薄 CLI adapter，TASK-831 拆 Observer read model/proof resolution 与 HTML/renderer assets，TASK-821/824落实命令/技能场景路由。不另加“重复统计”节点。

r3 的机械回归重点是：验收依赖环、仅 intent 自证的 requirement、未被节点 diff 暴露的顶层 intent 变化、畸形 result 字段、缺失公共 observation guard。确定性检查负责这些可计算边界；模型负责语义与视觉判断；人和宿主保留实际权限。具体反例的观察范围见 [系统评审](system-review-20261006.md)，不把局部 helper 接受等同于整条公共路径已接受。

## 架构、并行与变化边界

实际接口消费链为 **TASK-841 → TASK-842 → TASK-813 → TASK-824 → TASK-834**。独立 context/spec/helper/renderer 工作只等待所消费的契约；验收再合流。runtime domain 不做 I/O，store 独占发布，queries/projections 无 mutable authority。既有公共 imports 是薄兼容 facade，不是复制旧业务。

CONTRACT-801 注册 provisional module 800 non-generated lines／function 120 lines 的审查触发线、更小 adapter预算及明确例外。判断标准是职责、cycle、兼容、安全与相关读取/改动范围，不能靠删空行或碎切函数通过。没有单为文件组织而升级 canonical schema 或自动迁移。

r2 时假设 CONTRACT-801 已验收、draft impacts 有效的纯函数检查得到以下历史候选组合；r3 执行前必须重算：
- TASK-802 / TASK-821 / TASK-822 / TASK-823。
- TASK-811 / TASK-812。
- TASK-831 / TASK-832。

这不是当前 ready、guard、parallel ID 或执行授权。新增 TASK-841/843 在当前粗资产草案中 conservatively serial；TASK-843 与 TASK-823 的 helper schema 写入确实冲突。必须经 CONTRACT-801 窄化 mapping/inspection，再用真实 frontier、隔离 worktree/fixture/port、host capacity 重新计算。本次未启动 agent。

## Harness、保障和 artifact 生命周期

一条合适 procedure 可覆盖多个 criterion/inspection。使用既有 project-fit probes/browser harness，组件跑受影响检查，最终累计 gate 做完整回归及真实公共旅程；“commands”是可用入口，不是每节点必跑全套。合法 unchanged producer proof 可复用，相关源/guard/composition变化必须重验。

Execution、semantic acceptance、visual capture 和真正图像判断分开。更少 bytes/AST nodes 不能证明 model savings 或 human comprehension。TASK-802 预注册匹配场景与阈值，TASK-833保留失败对和不可用观察；缺失 required host/accounting/human proof 不得模拟通过。checksum/receipt 不是 host permission 或对恶意写入者的 execution attestation。

[assurance-draft.json](assurance-draft.json) 是 baseline r4 上的 49 个 impact hypotheses、25 个 planned inspection records，全部未执行。新 extraction 检查按职责 owner 保持窄边界，最大单记录 8 个 task；不是 25 次新增 tests，也不是 passing assurance。CONTRACT-801 须通过 supported assess/impact 补齐新路径 locators、按实际语义刷新检查；new-intent 不会自动导入此草案。

r3 扩展了 TASK-824 的规则文档 scope；CONTRACT-801 必须重新核对影响与 inspection 映射。执行 blocker 只限制受影响工作，分别报告 can implement、can verify、can accept/release；不取消原来的联合验收。Context 成本评测包括检索和写入开销、重复读取、缺失与 stale context，不能只统计输出字节。

Canonical history、active/handoff/acceptance references、未解决失败、个人文件和原始 VM受保护。预算/inventory不授予删除权限；只允许确认为开发所有、已停止、无必要引用、注册根目录内且已获授权的 disposable cleanup procedure。此次没有清理。

## 转换预览：未激活

Installed controller：
`/Users/merdankiji/.codex/plugins/cache/kmerdan-skills/pyramid-task/4.1.0/scripts/pyramid.py`。
源码声明 4.2.0，main ahead 1且包含未提交 Observer 改动；源码/controller/remote/install qualification 分开。

[transition-preview.json](transition-preview.json) 是实际 runtime preview：`archive → reset`，blockers 为空，需要 exact approval；旧历史、events/reports/dossiers/completed proof 与 baseline 保留。pending exact-code binding 警告保留，不擅自提交或清理“修复”。

- candidate r3 SHA-256：`487ded2ee3815886fddfdea289960097520f126b71c21b2891aa64ec50318b7b`
- transition SHA-256：`69dde614f13148ccd97c8e742f82da146cbe5ffc35975155e93fd94c5d9c3335`

此前 r1/r2 preview 不再适用于 r3。candidate 或 canonical context 改变后需重新 preview；生成/补充计划不等于批准转换或实施。

## 规划评审与验证

[plan-review.json](plan-review.json) 绑定 [原 r2 exact bytes](candidate-plan.r2.json) 和 r3，双向追踪 12 项 requirement。r1/r2 原件与 r2 评审、转换预览保留。原要求、旧验收标准、证据 ID 与拓扑均保留；本次不通过增加任务宣称 complexity 已下降。协调者规划评审不是独立产品验收。

[planning-validation.json](planning-validation.json) 记录实际通过的 installed 4.1／source 4.2 schema 与 runtime 校验、原要求保留、criterion/proof 结构覆盖、有效验收依赖无环、requirement → work → gate/outcome 追踪和 canonical hashes 未变。[validate-planning.py](validate-planning.py) 是只读规划校验器，不是产品验收测试。`doctor` 会写入 canonical lock/projection，本次受源目录写权限限制未通过；没有扩大权限或绕过限制。只读 validate/inspect 和转换 preview 已完成。

Schema/graph、hash bindings、requirement/闭环检查只能证明规划结构。通过未等于代码重构完成、实际 token savings、cleanup安全或视觉理解已验证。当前 canonical plan/state exact hashes 保持不变。
