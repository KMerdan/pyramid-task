# Repository guidance

Start with `CONTEXT.md` for dated source status and `docs/README.md` for topic
owners, then inspect current Git state and only the files relevant to the request.
Planning JSON and `proof-output/` are historical records, not a pending work queue
or current installation authority. Preserve captured evidence and generated files.
The improvement index owns A/B/C decisions and dated qualification. Local working
runs are ignored; size does not grant cleanup authority. Drafting `goal-prompt`
does not execute the resulting prompt.

The installable plugin lives in `plugins/pyramid-task/`. Keep runtime behavior deterministic and agent reasoning in the skill instructions.

Before submitting a change:

1. Preserve the canonical graph, state, event, and lifecycle contracts.
2. Do not hand-edit generated `.pyramid/graph.json`, `.pyramid/ready.json`, browser output, or `docs/tasks/` artifacts.
3. Keep every `SKILL.md` concise, imperative, and free of repository-maintainer instructions.
4. Add or update schemas and tests when changing serialized data or lifecycle transitions.
5. Run `python3 tools/validate_repository.py` and the full unit test suite.

Do not commit credentials, local marketplace configuration, generated runtime state, Python caches, or personal project data.
