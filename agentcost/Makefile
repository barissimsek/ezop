PYTHON  := .venv/bin/python
TWINE   := .venv/bin/twine
RUFF    := .venv/bin/ruff
PYRIGHT := .venv/bin/pyright
SRC     := src/ezop_agentcost/ tests/ examples/

# Use uv when available (its venvs ship without pip), otherwise the venv's pip.
ifneq ($(shell command -v uv 2>/dev/null),)
PIP_INSTALL   := uv pip install -p $(PYTHON)
FORCE_INSTALL := --reinstall-package ezop-agentcost
else
PIP_INSTALL   := $(PYTHON) -m pip install
FORCE_INSTALL := --force-reinstall
endif

.PHONY: dev test test-benchmark benchmark lint format build install publish publish-test clean

dev:
	$(PIP_INSTALL) -e ".[dev]"

lint:
	$(RUFF) check $(SRC)
	$(RUFF) format --check $(SRC)
	$(PYRIGHT)

format:
	$(RUFF) format $(SRC)
	$(RUFF) check --fix $(SRC)

test:
	$(PYTHON) -m pytest tests/ -v -m "not benchmark"

# Seeded-regression acceptance test against the offline mock model (~30 s, no API keys).
test-benchmark:
	$(PYTHON) -m pytest tests/test_benchmark.py -v

# The benchmark as a readable table; pass ARGS, e.g. make benchmark ARGS="--exact -n 2".
benchmark:
	cd examples/support_agent && ../../$(PYTHON) benchmark.py $(ARGS)

build: clean test
	$(PYTHON) -m build

install: build
	$(PIP_INSTALL) dist/ezop_agentcost-*.whl $(FORCE_INSTALL)

publish: build
	$(TWINE) upload dist/*

publish-test: build
	$(TWINE) upload --repository testpypi dist/*

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
