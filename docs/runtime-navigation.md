# Runtime navigation

Start with the row for the changed behavior. Read its implementation and matching test; expand to concrete dependencies when the change consumes them. The compatibility facade is an API lookup, not required reading for pure-rule work. Full import closures and unmet budgets are in the [final report](releases/4.2.1.md), separately from this navigation guide.

| Change | Implementation entry | Verification entry |
| --- | --- | --- |
| State, guard, ownership | `pyramid_state.py`, `pyramid_errors.py` | `test_runtime_modularization.py`; named guard/claim cases in `test_runtime.py` |
| Replan / expansion candidate | `pyramid_topology.py`, `pyramid_validation.py` | `test_validation.py`, `test_runtime_modularization.py` |
| Plan/assurance errors | Ordered phases in `pyramid_validation.py`, `pyramid_assurance_contracts.py` | `test_validation.py`, `test_assurance_modularization.py` |
| Packet / graph / Markdown values | `pyramid_projection.py` | `test_runtime_modularization.py` |
| Paths, lock, JSON, event/head commit | `pyramid_files.py`, `pyramid_storage.py` | `test_storage_modularization.py` (real processes/faults) |
| Graph-last / report publication | `pyramid_publication.py` | `test_storage_modularization.py`, existing publication cases in `test_runtime.py` |
| Handoff values and read/write | `pyramid_handoff.py`, `pyramid_handoff_io.py` | Handoff/pause/recovery cases in `test_runtime.py`, `test_task_modularization.py` |
| Changed-file rules and inspection effects | `pyramid_changes.py`, `pyramid_change_io.py` | `test_task_modularization.py`, assurance/scope cases in `test_runtime.py` |
| Claim / update / audit / pause / amend / reopen | `pyramid_task_commands.py`, `pyramid_results.py`, `pyramid_proof_io.py` | `test_task_modularization.py`, `task_modularization_support.py` |
| Create / replan / expand / close | `pyramid_plan_commands.py`, `pyramid_plan_bundle.py` | `test_plan_modularization.py`, `plan_modularization_support.py` |
| Archive / reset / restore / clean / new intent | `pyramid_plan_lifecycle.py` | `test_plan_modularization.py`, lifecycle cases in `test_runtime.py` |
| Assess / impact | `pyramid_assurance_commands.py` | `test_plan_modularization.py`, brownfield cases in `test_runtime.py` |
| Project / history / diff / readiness queries | `pyramid_queries.py`, `pyramid_project_queries.py` | `test_query_modularization.py`, `query_modularization_support.py` |
| CLI flags / dispatch / output | `pyramid_cli_options.py`, `pyramid_cli_plan.py`, `pyramid_cli_task.py`, `pyramid_cli_queries.py`; entry `pyramid.py` | Query/CLI independent oracle; CLI cases in `test_runtime.py` |
| History contract / loaded read model / durable ledger | `pyramid_history_contracts.py`, `pyramid_history_model.py`, `pyramid_history.py` | `test_history_modularization.py`, history/recovery cases in `test_runtime.py` |
| Freshness / blockers / explicit defaults | `pyramid_assurance_rules.py`, `pyramid_assurance_defaults.py`; clock compatibility in `pyramid_assurance.py` | `test_assurance_modularization.py` |
| Requested repository footprint | `pyramid_assurance_io.py` | Footprint oracle and ordinary-query no-scan traps |
| Observer values / resource assembly / live service | `pyramid_observer.py`, `pyramid_visualizer.py`, `assets/observer.html`, `assets/live.js`, `pyramid_live.py` | `test_observer_modularization.py`, existing static/live `.cjs` smoke and actual image review |
| Opt-in dependency analysis | `pyramid_dependencies.py`, `pyramid_proof_analysis.py`, `pyramid_benchmark.py` | `test_dependencies.py`, `test_proof_analysis.py`, hash-bound corpus benchmark |

All Python filenames above are under [plugin scripts](../plugins/pyramid-task/scripts/), tests under [plugin tests](../plugins/pyramid-task/tests/). Existing runtime test IDs remain valid apart from the one documented [S1 mapping](releases/4.2.1.md#compatibility-and-verification). Support files define fixture/oracle inputs; their full inherited setup is counted in the context report.

The transaction route is command → explicit value checks → locked storage reread/guard → event/state/head commit → graph-last publication → read projection. History ledger append/repair has its own durability route. Immutable named TaskPorts/PlanPorts/QueryPorts preserve old fault/clock seams; they are not arbitrary transition registries. Defaults bind concrete lower owners. Pure modules do not import the facade or perform file/clock/process access.

Use the [architecture](architecture.md) for authority and integration rules. Read the [release qualification](releases/4.2.1.md) for measurements and limits; historical stage evidence is retained separately. Optional dependency scanning is explicit; normal queries neither discover ast-grep nor traverse the repository. Large dependency/verification/parallel implementations and the historical runtime test fixture remain intentionally outside this refactor's additional splitting scope.
