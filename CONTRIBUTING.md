# Contributing to Ezop

Thank you for taking the time to contribute. This document covers everything you need to get started.

## Getting started

1. Fork the repository and clone your fork
2. Create a virtual environment and install dependencies (for Python):

```bash
cd python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

3. Create a branch for your change from `develop` branch:

```bash
git checkout develop
fir pull
git checkout -b feat/your-feature-name
```

## Making changes

- Keep changes focused — one bug fix or feature per PR
- Follow the existing code style (the project uses standard Python conventions)
- Big structural changes must include a design spec and a plan generated via `superpower::brainstorm`.
- Add or update tests for any behaviour you change
- Run the test suite before submitting:

```bash
make test
```

## Adding a schema change

1. Create `database/migrations/YYYY/YYYYMMDDHHMMSS-description.sql` with the diff SQL
2. Schema changes must be accompanied by the corresponding code changes in the same PR.
3. CI/CD will handle the rest.

## Submitting a pull request

1. Push your branch and open a PR against `develop`
2. Fill in the PR description — what changed and why
3. A maintainer will review and leave feedback or merge

## Responsible AI usage

1. AI tools are welcome, but you are fully responsible for the code you submit. Make sure you understand every part of it.
2. Significant changes must be accompanied by a design spec. You can use superpower::brainstorm or provide your own.
3. Submitting AI-generated code without understanding it is not acceptable. If we see repeated cases of this, we may restrict your ability to open pull requests. Please respect reviewers’ time. Low-quality, unvetted code will not be reviewed.

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
