VENV := .venv
PYTHON := $(VENV)/bin/python
RUFF := $(VENV)/bin/ruff
PYTEST := $(VENV)/bin/pytest

.PHONY: install lint test check

install:
	python -m venv $(VENV)
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

lint:
	$(RUFF) check .
	$(RUFF) format --check .

test:
	$(PYTEST)

check: lint test
