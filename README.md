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
cutouts-service 180.0 -30.0 0.1 https://example.com/file.fits --output cutout.fits
cutouts-service 180.0 -30.0 0.1 s3://example-bucket/file.fits --output cutout.fits
```

The CLI accepts `ra`, `dec`, `radius`, a remote FITS URL input (`http`, `https`, or `s3`), and a required `--output` path. It uses Astropy to extract a sky cutout from the source FITS file and writes the resulting FITS file to disk.

## Contributing

See [contributing.md](contributing.md) for developer environment setup, uv workflow, and dependency policy.
