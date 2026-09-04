# Cutouts_service

A cutouts service to act as an alternative for the existing CASDA cutouts service backend. Developed as part of the ASEPS work.

## Setup

To set up the repository run the below commands to fetch the repository and install the development requirements.

```bash
git clone https://github.com/AusSRC/cutouts_service
cd cutouts_service
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .
```

To include the development dependencies, such as `ruff` and `pytest`, run:

```bash
pip install ".[dev]"
```

## Testing

If you installed the development dependencies you can run `make test` to ensure that the package is appropriately installed. 

## Running from the command-line

The cutouts service is run from a single command:

```bash
usage: cutouts-service [-h] [--s3-endpoint-url S3_ENDPOINT_URL] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                       [--spectral-units {channels,Hz,kHz,MHz,GHz}] [--spectral-min SPECTRAL_MIN] [--spectral-max SPECTRAL_MAX] [-n] --output OUTPUT
                       [--backend {astropy,objstore}]
                       ra dec radius file
```
### Where:
| Positional Argument | Description |
|:----------:|:-------------|
| ra | Right ascension of the centre of the cutout |
| dec | Declination of the centre of the cutout |
| radius | Cutout radius in arcminutes |
|file | Input file path or URL |

| Option | Expected Value | Description |
|:------:|:--------------:|:------------|
| -h, --help | |          show this help message and exit |
| --s3-endpoint-url | S3_ENDPOINT_URL | Optional S3-compatible endpoint URL for s3:// sources |
| --log-level | DEBUG, INFO, WARNING, ERROR, or CRITICAL | Logging verbosity level (default: INFO) |
| --spectral-units | One of 'channels', 'Hz', 'kHz', 'MHz', or 'GHz' | The unit selection for specifying the spectral bounds, can be one of channels, Hz, kHz, MHz, GHz; default is 'channels'. |
| --spectral-min | SPECTRAL_MIN as a decimal number | The lower bound of the cutout request along the spectral axis, the units are specified by the `--spectral-unit` option. Default is to request all channels. Note: the channel number is zero-indexed, i.e. enter 0 to retrieve the first channel. |
| --spectral-max | SPECTRAL_MAX as a decimal number | The lower bound of the cutout request along the spectral axis, the units are specified by the `--spectral-unit` option. Default is to request all channels. Note: the channel number is zero-indexed, i.e. enter 0 to retrieve the first channel. |
| --dry-run, -n | |       perform a dry-run, where the selected fits cube will be queried for extent and size. |
| --output | OUTPUT filename |      Output cutout FITS file |
| --backend | One of 'astropy' or 'objstore' | The backend to use to perform the cutout. The two supported options are 'astropy' and 'objstore'. Default is 'astropy'. |

### Example

```bash
cutouts-service 180.0 -30.0 0.1 "https://example.com/file.fits" --output cutout.fits
cutouts-service 180.0 -30.0 0.1 "s3://example-bucket/file.fits" --output cutout.fits
cutouts-service 180.0 -30.0 0.1 "s3://example-bucket/file.fits" --s3-endpoint-url "https://objects.example.org" --output cutout.fits
cutouts-service 180.0 -30.0 0.1 "https://example.com/file.fits" --spectral-min 0.8 --spectral-max 1.0 --spectral-units GHz --output cutout.fits
```

The CLI accepts `ra`, `dec`, `radius`, a remote FITS URL input (`http`, `https`, or `s3`), and a required `--output` path. It uses Astropy to extract a sky cutout from the source FITS file and writes the resulting FITS file to disk. Ensure that the urls are contained in quotes, especially if it contains special characters.

For S3-compatible object stores, pass `--s3-endpoint-url` to route `s3://` requests to a custom endpoint.

## Current unsupported features and caveats

- For the ObjectStore backend, only the first HDU will be accessed as an image. The output file will only have one HDU. The Astropy backend will perform the cutout and copy any secondary HDUs to the local FITS file. The CASAMBM entry in the header will be set to False when using the ObjStore backend, this ensures compatibility with CARTA and other visualisation applications.
- The current version will only cutout on two physical axes (Right Ascension and Declination) and one spectral axis. A stokes axis will be copied in its entirety. Any other axes will be omitted.
- The Objstore backend does not support more than one stokes parameter and requires a degenerate stokes axis (length of 1). The Astropy backend will handle this fine.
- The current version will only work with presigned URLs and public URLs, private s3 objects are currently inaccessible, generate a presigned URL to access these files with `cutouts-service`. This can be done using any of:
    ```bash
    # AWS
    aws s3 presign s3://bucket/file.fits --expires-in 604800
    # Rclone
    rclone link alias:bucket/file.fits --expire 3600
    ```

## Troubleshooting
- There have been issues with installing this package with pip version less than 25, ensure that pip is upgraded before installing.

## Contributing

See [contributing.md](contributing.md) for developer environment setup, uv workflow, and dependency policy.
