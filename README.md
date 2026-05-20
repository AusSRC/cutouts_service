# Cutouts_service

A cutouts service to act as an alternative for the existing CASDA cutouts service backend. Developed as part of the ASEPS work.

## Setup

```bash
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
pip install ".[dev]"
```

## Lint and test

```bash
make lint
make test
```

## Run the CLI

```bash
cutouts-service 180.0 -30.0 0.1 https://example.com/file.fits
cutouts-service 180.0 -30.0 0.1 ./file.fits
```

The CLI currently accepts `ra`, `dec`, `radius`, and a `file` input (URL or path), and prints the parsed request parameters.

## Contributing

See [contributing.md](contributing.md) for developer environment setup, uv workflow, and dependency policy.
