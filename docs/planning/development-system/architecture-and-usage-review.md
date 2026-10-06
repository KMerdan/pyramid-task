# 架构与使用审计：此次 intent 的补充依据

观察日：2026-10-06。对象：Standalone Pyramid Skill，`/Users/merdankiji/localGit/pyramid-task`，local-canonical。本地 dirty 4.2.0 源码与已安装 4.1.0 controller 分开。此文是分析与候选决策，不是通过的工程验收。

## 第一性原理

系统需要维护可恢复的开发承诺：谁能做什么、当前事实是什么、什么证明支持什么结论、失败后如何恢复。实现它们需要的最少独立边界是策略、用例、存储/发布、查询/投影、主机适配与契约。命令数与行数都是线索，不是目的函数。我们要降低一次改动必须理解、改动和重新验证的范围，同时不丢权限、失败证据和历史。

删除标准：一个接口没有成立的 actor/trigger/effect，或已有接口在相同权限、错误、恢复和兼容条件下完整替代它，才有退出理由。低频但高失败损失的恢复能力不应按流量删除；未测量的能力不能标记 unused。

## 实际审计与限制

[原始审计](usage-audit-30d.json) 是一次只读快照。请求窗口 30 天，实际记录从 2026-09-27T12:58:45.856+00:00 到 2026-10-05T22:42:08.418+00:00，不是完整 30 天的活动覆盖。5693 次调用中成功 5607、非零退出 84、unfinished 2。非零退出可能是正确拒绝或故障测试，不是 84 个已确认 bug。

- 当前 catalog：26 个 CLI command；19 个有记录，7 个零记录。
- `inspect`：3,381 次，59.4%；输出 311,370,545 bytes，占总输出 62.9%。
- `inspect --harness`：1,376 次；selected-node：1,062 次；audit-readiness：467 次。它们是被反复消费的决策入口，值得实测 packet 复用与选择性读取。
- 全部输出 495,155,935 bytes（约 472.2 MiB），CLI wall time 累计约 113.1 分钟。不是模型 token、人工时间、无效浪费或 agent latency。
- 只有 31 次 assurance-detail 却输出 61,772,119 bytes；10 次 pending-audits 输出 18,693,642 bytes。优先查“一次决策加载多少不相关内容”，不优先减少合法验收。
- 不能确定重复调用、项目分布、顺序或根因：SQLite 是按日聚合，无 project identity/raw argv/调用链。此审计不记录直接 Python API、技能执行、help/parser rejects、disabled/失败收集，且不回填。
- 版本分别看。4.1 的 update/clear 平均约 8,126 bytes；4.0 约 1,562,787 bytes。不是匹配项目比较，不能声称固定百分比收益。assurance-detail 在 4.1 仍平均约 2.36 MB，但本地 4.2 源码已有 selected assurance 查询（core scoped_assurance_detail）；不能把历史数据误称当前 candidate 尚未修复。
- 本次查询关闭计数，不污染统计。source skills 的 `goal-prompt` 新于被查询的 installed catalog；连同 orchestrate/simplify 都没有可推断的技能使用次数。

## 每个 CLI 表面：场景而非热度

“保留”表示已有合理语义，不表示已证明其发现性/成本最佳。“专家入口”表示从日常 prompt 移出，只在触发时加载，不等于隐藏恢复文档或移除公共兼容。

| CLI | 次数 | 建议 | 用户场景 | 保留／合并边界 |
| --- | ---: | --- | --- | --- |
| amend | 89 | 保留／按需 | 已领取任务新增文件或上下文；比全量 replan 更窄 | 只能 additive；语义/验收改变仍需 replan |
| archive | 0 | 专家入口保留 | 暂停整份 intent 并冻结可恢复快照 | new-intent 内部也可执行归档，CLI 零次不等于路径未用 |
| assess | 20 | 保留／按需 | brownfield 基线或资产边界变化 | 不等于每次 take 都重新评估 |
| audit | 207 | 保留／核心 | 把实现结果与独立验收分开 | 不能用 update implemented 替代 |
| clean | 0 | 恢复入口；审查边界 | 派生 docs/graph 含陈旧文件，需要完全重建 | 实际会删除派生目录；不能当 artifact 清理，也不等价 compile |
| close | 6 | 保留／边界 | 所有必要验收完成后正式关闭 intent | 通过 gate 不等于已生成 final report/chronicle |
| compile | 0 | 维护入口；审查边界 | 从有效 canonical 数据重新生成投影 | 与 doctor/clean 重叠候选；删除前证明错误、归档及 stale-file 行为等价 |
| create | 3 | 底层保留；默认 new-intent | 首次建立无 canonical plan 的项目 | 低频符合项目生命周期；不能覆盖现有计划 |
| diff | 17 | 按需保留 | 回答两个 graph version 之间改了什么 | 比读全历史窄；不是 Git diff |
| doctor | 28 | 维护入口保留 | 验证项目并在合法时编译派生物 | 不是纯 read-only；日常观察优先 inspect，别把它当每步固定 ritual |
| expand | 0 | 专家入口；需场景资格 | 一个宽任务需要更深子树，同时保持 parent contract | replan 更通用但约束不同；需对比等价案例后再决定合并/弃用 |
| history | 9 | 按需保留 | 追踪跨 intent 原因、路径或 commit 绑定 | 现有 4 次非零退出需独立复现；计数不含 stderr/原因 |
| impact | 335 | 保留／按需 | 资产检查、发现、drift 和控制的变更 | 335 次不证明都必要；避免只改账本触发同一证据重跑 |
| inspect | 3381 | 保留；优化选择和响应 | 回答当前下一步/目标任务/证据/阻塞 | 按问题返回 selected data；不能仅返回更少字节而丢 guard/unknown |
| lifecycle | 72 | 按需保留 | 查看生命周期、归档和可用转换 | 与 inspect summary 比较需求；保留恢复发现性 |
| new-intent | 42 | 保留／默认入口 | 无计划或完成旧 intent 后开始新目标 | 路由 create/archive/reset，hash-bound 批准不能省 |
| pause | 35 | 保留／边界 | 保存不可变 handoff，停止持有或交还任务 | 不能被 update release 替代；保留暂停现场 |
| reopen | 21 | 保留／失败触发 | 已验证或失败任务需要重新工作 | 不能直接覆写 verified history |
| replan | 181 | 保留／变化触发 | 改语义、依赖、验收或 intent 结构 | 编辑受影响 stable IDs；完整校验不等于全量重写候选 |
| reset | 0 | 专家入口保留 | 归档当前计划后初始化新计划 | 默认 new-intent 做安全路由；不推荐手动串 archive/reset |
| restore | 0 | 低频安全入口保留 | 恢复归档计划，保护现有工作与原证据 | 跨日/机器与错误切换是真实需求；恢复旧证明不证明当前源码有效 |
| resume | 62 | 保留／暂停触发 | 验证 handoff 后继续暂停任务 | 不能当 take 的别名；需检查 drift/lease |
| take | 226 | 保留／核心 | 声明对 ready 可执行任务的所有权 | 不能用状态写入绕过 authority guard |
| update | 308 | 保留；优化反馈响应 | 上报风险、阻塞、释放或实现完成 | 308 次输出大不证明操作多余；区分不同 transition 和有效 packet reuse |
| validate | 651 | 保留／边界 | 纯检查 canonical 一致性、不自动编译 | 651 次不能确定是否多余重复；需要匹配场景调用链 |
| visualize | 0 | 保留／人类观察 | 导出人类 Observer 或启动有界 live renderer | 源测试实际直接调用 visualizer API；CLI 零次不是无视觉需求 |
## 18 个 source skills 的场景覆盖

CLI 计数不能证明任一 skill 使用了几次。下面是职责映射，不是 skills telemetry；审查其 prompt 装载成本时需要 matched host traces。默认路径应按创建、工作、验收、变化、交接、恢复、观察触发，不应一次装载全部技能。

| Skill | 明确场景 / 机制 |
| --- | --- |
| assess | 基线与资产变化 → assess |
| audit | 独立验收 → audit |
| create | 讨论转首个候选 → create/new-intent |
| expand | 宽节点深分解 → expand |
| goal-prompt | 当前项目/阶段/权限事实 → reviewable goal draft；没有 CLI |
| history | 历史因果与绑定 → history |
| impact | 资产/检查/发现/drift → impact |
| inspect | 选择性状态与 usage 分析 → inspect |
| lifecycle | 失败重开/关闭/归档恢复 → 多个 lifecycle CLI |
| new-intent | 新目标 → hash-bound lifecycle routing |
| orchestrate | 独立 graph task 或 read-only helper → 主机 agent 工具；没有同名 CLI |
| pause | 停工交接 → pause |
| replan | 需求/证据改变 → replan |
| resume | 交接验证后继续 → resume |
| simplify | 候选语义/必要性检查 → agent 推理；没有同名 CLI |
| take | 领取可执行工作 → take |
| update | 上报而不自我验收 → update |
| visualize | 人类理解状态/证据 → visualize 或直接渲染 API |

## 源码与 schema 的实查

[源码清单](source-inventory.json) 记录当前文件 exact SHA-256、AST 函数数量/长度及直接 imports。12 个 Python 脚本共 13,210 行；31 个 JSON schema。含空行、注释和 visualizer 嵌入模板，不能用这些 LOC 直接推断算法复杂度。

| 模块 | 行数 | 观察到的混合／大型边界 |
| --- | ---: | --- |
| pyramid_core.py | 6,031 | 131 个函数；存储/锁/发布、guard、验证、投影、任务/拓扑生命周期和 queries |
| pyramid_history.py | 1,718 | 验证、chronicle 构建、事务修复、Git binding、查询/索引 |
| pyramid_visualizer.py | 1,643 | Observer/proof read model、证据解析、HTML/CSS/JS 模板与输出 |
| pyramid_assurance.py | 1,143 | assurance policy/validation 与 filesystem footprint walker |
| pyramid.py | 677 | build_parser 289 行、run 243 行；家族注册/dispatch可拆，避免泛型框架 |
| pyramid_parallel.py | 555 | build_parallel_frontier 220 行；已有纯模块，不因 LOC 自动再拆 |
| pyramid_verification.py | 560 | 最大函数 64 行；现有契约/证明模块应复用，不作为膨胀假设重写 |

core 的 validate_plan 369 行、inspect_project 248 行；history record_intent_chronicle 197 行；assurance validate_assurance 284 行。这些符号与 docs/architecture.md 的既有 extraction sequence 一致，说明“core 是 facade”目前是目标方向，尚非薄 facade。已有 pure domain 不反向 import core 的好边界要保留。

Schema 不是按同名自动统一：
- agent-result 与 audit-result 的 proofs 属性完全相同，helper-job/result 的 id/snapshot 相同：可以调查单一语义所有者。
- plan 与 expansion 的 criterion/agent/id/stringArray 相同，但 evidenceRequirement/node 不同：必须证明差异意图，不能为了 DRY 扩大/缩小任一接口的接受集合。
- 现有 tests 直接 jsonschema.validate(schema object)，没有统一离线 resolver 配置。跨文件 $ref 会改变消费者前提。可选择 authored fragments + 可重复生成的自包含 public schemas，或先资格化离线 registry；不能让开发测试提供 resolver 就宣称安装包兼容。
- JSON Schema 与 core/assurance/verification 的手写语义校验不是同一种真相：schema管形状，runtime管语义。需要共同正/反例协议，不应强行用 schema 替换权限、图、失效与发布逻辑。

## 目标架构与实施边界

```text
host skills → thin CLI / explicit runner adapters
                  ↓
          application use cases
          ↙         ↓          ↘
 pure policy    read queries   store + publication
      ↓           ↓            ↓
 contracts    projections     canonical JSON/events/history
                  ↓
       Observer shell + packaged render assets
```

dependencies 向领域/显式依赖收敛；pure policy不做文件/时钟/进程 I/O；queries 读验证后的 bundle，不编译无关图；store 独占锁与 publication。既有 pyramid_core/pyramid_history 等公共导入可做薄 facade，但不能反向 import facade、复制实现或造第二套事务。history 有其独立 hash-linked ledger，不可在“统一存储”中合并掉它的恢复与 append-only 语义。

新增 TASK-841（存储/发布）、TASK-842（生命周期/query/projection/history/assurance ownership）、TASK-843（schema ownership/package compatibility）。CLI 分解由既有 TASK-813 承担；Observer 模板/read model 分解由既有 TASK-831 承担；场景化 skill routing 归 TASK-821/824，不新增“只做统计”的重复任务。所有工作纳入原三个累计 gate，无新 ceremony gate。

CONTRACT-801 注册 provisional module 800 non-generated lines / function 120 lines 的审查触发线及更小 adapter预算；超限需要明确职责/风险解释，而不是削空行、切碎一段函数或全面覆盖例外。最终应检查：facade无迁移业务、acyclic deps、无重复实现、匹配功能负例通过、相关源读取/变更放大范围与实测成本。行数减少单独不通过。

安全顺序按真实消费：TASK-841 → TASK-842 → TASK-813，schema与其消费在集成边界重合；独立 context/spec/helper/renderer 构建不等待整个重构验收。写 scope 与schema/shared facade冲突按 actual frontier 重新计算，不能沿用旧 parallel组。

## 现在能下的结论与仍未知的事

可以确认 architecture ownership 是真实待改进面，selected decision 的输出是历史负担热点，零调用功能有多种有效或待资格化场景。不能确认哪些调用是重复、总 token 节省、哪个失败是 bug、哪些 skill 从未运行、或 compile/clean 与 expand/replan 是否真正可删除。

因此此次 intent 同时交付结构重构与场景裁决，并用 current-source/同输入测试验证，而不是“先凑出删除名单”。恢复/权限不因低频弱化，现有 4.2 修复不重复实现，required review 不变成全套每步重跑。此分析没有执行重构、删除功能、清理 evidence、变更安装或更改 canonical。
