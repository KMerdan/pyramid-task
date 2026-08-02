---
name: pyramid-task-planner
description: Compatibility router for old Pyramid Task Planner installations. Use when a legacy `$pyramid-task-planner` invocation asks to decompose a feature, idea, architecture proposal, or new intent; delegate all planning and lifecycle mutations to the installed Pyramid Task V3 plugin instead of writing `docs/tasks` directly.
---

# Pyramid Task V3 Compatibility Router

Do not create task Markdown files directly. Locate the installed `pyramid-task` plugin and let its runtime own `.pyramid` canonical state and generated projections.

Route requests as follows:

- First intent with no `.pyramid/plan.json`: use `pyramid-task:create`.
- New intent after an existing or completed cluster: use `pyramid-task:new-intent`.
- Existing legacy project that must continue its current intent: use `pyramid-task:upgrade`.
- Current execution, audit, inspection, or lifecycle work: use the corresponding Pyramid Task V3 skill.

Treat `.pyramid/project.json` as the V3 project-format marker. `plan.json` and `state.json` are compatible canonical contracts and do not identify the installed runtime version.

If the V3 plugin is unavailable, stop and ask the user to install or enable `pyramid-task`; do not recreate its state protocol from memory.
