# Contributing to Ezop Python SDK

Thank you for taking the time to contribute. This document covers everything you need to get started.

## Getting started

1. Fork the repository and clone your fork
2. Create a virtual environment and install dependencies:

```bash
cd python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

3. Create a branch for your change:

```bash
git checkout -b feat/your-feature-name
```

## Making changes

- Keep changes focused — one bug fix or feature per PR
- Follow the existing code style (the project uses standard Python conventions)
- Add or update tests for any behaviour you change
- Run the test suite before submitting:

```bash
make test
```

## Submitting a pull request

1. Push your branch and open a PR against `main`
2. Fill in the PR description — what changed and why
3. A maintainer will review and leave feedback or merge

## Reporting bugs

Open an issue and include:
- What you expected to happen
- What actually happened
- A minimal code snippet that reproduces the problem
- Your Python version and SDK version (`pip show ezop`)

## Suggesting features

Open an issue describing the use case. PRs for large features are easier to merge when the design is discussed first.

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to abide by its terms.
