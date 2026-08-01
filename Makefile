PYTHON ?= python3

.PHONY: validate test check

validate:
	$(PYTHON) tools/validate_repository.py

test:
	$(PYTHON) -m unittest discover -s plugins/pyramid-task/tests -p 'test_*.py' -v

check: validate test
