## Summary

Describe the change and the problem it solves.

## Contract impact

- [ ] No serialized contract change
- [ ] Backward-compatible schema or runtime change
- [ ] Breaking change documented and intentionally versioned

Explain any graph, state, event, agent-packet, or lifecycle impact.

## Validation

- [ ] `python3 tools/validate_repository.py`
- [ ] `python3 -m unittest discover -s plugins/pyramid-task/tests -p 'test_*.py' -v`
- [ ] Relevant manual or browser checks

## Safety

Confirm that the change preserves authorization boundaries, immutable history, and archive/reset recoverability.
