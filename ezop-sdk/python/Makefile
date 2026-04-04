PYTHON  := .venv/bin/python
PIP     := .venv/bin/pip
TWINE   := .venv/bin/twine
RUFF    := .venv/bin/ruff
PYRIGHT := .venv/bin/pyright

.PHONY: test test-integration lint format build install publish clean

lint:
	$(RUFF) check ezop/ tests/
	$(RUFF) format --check ezop/ tests/
	$(PYRIGHT) ezop/

format:
	$(RUFF) format ezop/ tests/
	$(RUFF) check --fix ezop/ tests/

test:
	$(PYTHON) -m pytest tests/ -v -m "not live"

test-integration:
	$(PYTHON) -m pytest tests/test_integration.py -v -m "not live"

build: clean test
	$(PYTHON) -m build

install: build
	$(PIP) install dist/ezop-*.whl --force-reinstall

publish: build
	$(TWINE) upload dist/*

clean:
	rm -rf dist/ build/ *.egg-info
