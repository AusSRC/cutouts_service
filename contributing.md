# Contributing

Thanks for contributing to this project.

This guide explains how to set up a local development environment, run checks, and work consistently across tooling choices.

## Principles

- pyproject.toml is the source of truth for project metadata and dependencies.
- uv.lock is a reproducibility artifact for uv users.
- If there is ever a conflict, follow pyproject.toml and regenerate uv.lock.

## Prerequisites

- Python 3.11+
- make
- git
- uv (recommended)

## Clone and initialize

1. Clone the repository.
2. Initialize submodules:

```bash
git submodule update --init --recursive
```

## Development setup with uv (recommended)

From the repository root:

```bash
uv venv .venv
source .venv/bin/activate
uv sync --extra dev
```

This installs the project and the dev dependencies defined in pyproject.toml, including lint and test tools.

You can either keep the virtual environment activated, or run commands with uv run.

Examples:

```bash
uv run make lint
uv run make test
```

## Alternative setup without uv

If you prefer standard Python tooling:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install ".[dev]"
```

## Run checks locally

With an active environment:

```bash
make lint
make test
```

Or with uv:

```bash
uv run make lint
uv run make test
```

## Run the CLI locally

```bash
cutouts-service 180.0 -30.0 0.1 https://example.com/file.fits
cutouts-service 180.0 -30.0 0.1 ./file.fits
```

## Dependency and lock file guidance

- Update dependency declarations in pyproject.toml.
- Regenerate uv.lock when dependency changes are made and include it in the same PR.
- Do not edit uv.lock manually.
- Team members not using uv can still install from pyproject.toml and do not need uv.lock for normal development.

## Pull request checklist

- Lint passes.
- Tests pass.
- Dependency changes are reflected in pyproject.toml.
- If dependencies changed and you use uv, uv.lock is updated.
