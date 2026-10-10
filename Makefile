PYTHON ?= python3

.PHONY: validate test test-maintainer check

validate:
	$(PYTHON) tools/validate_repository.py

test:
	$(PYTHON) -m unittest discover -s plugins/pyramid-task/tests -p 'test_*.py' -v

test-maintainer:
	$(PYTHON) -m unittest discover -s tools/tests -p 'test_*.py' -v

check: validate test test-maintainer
