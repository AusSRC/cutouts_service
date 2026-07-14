# Cutouts_service

A cutouts service to act as an alternative for the existing CASDA cutouts service backend. Developed as part of the ASEPS work.

## Setup

To set up the repository run the below commands to fetch the repository and install the development requirements.

```bash
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
pip install ".[dev]"
```

## Testing

Run `make test` to ensure that the package is appropriately installed. 

## Running from the command-line

The cutouts service is run from a single command:

```bash
usage: cutouts-service [-h] [--s3-endpoint-url S3_ENDPOINT_URL] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--spectral-start-channel SPECTRAL_START_CHANNEL]
            [--spectral-stop-channel SPECTRAL_STOP_CHANNEL] [--dry-run] --output OUTPUT [--backend BACKEND]
            ra dec radius file
```
### Where:
| Positional Argument | Description |
|:----------:|:-------------|
| ra | Right ascension in decimal degrees |
| dec | Declination in decimal degrees |
| radius | Cutout radius in arcminutes |
|file | Input file path or URL |

| Option | Expected Value | Description |
|:------:|:--------------:|:------------|
| -h, --help | |          show this help message and exit |
| --s3-endpoint-url | S3_ENDPOINT_URL | Optional S3-compatible endpoint URL for s3:// sources |
| --log-level | DEBUG, INFO, WARNING, ERROR, or CRITICAL | Logging verbosity level (default: INFO) |
| --spectral-start-channel | SPECTRAL_START_CHANNEL as an integer | Optional inclusive start channel for spectral-axis cutout, set spectral-start-channel and spectral-stop-channel to the same value for a single channel. Default is all channels. Note: the channel number is zero-indexed, i.e. enter 0 to retrieve the first channel. |
| --spectral-stop-channel | SPECTRAL_STOP_CHANNEL as an integer | Optional inclusive stop channel for spectral-axis cutout, set spectral-start-channel and spectral-stop-channel to the same value for a single channel. Default is all channels. |
| --dry-run, -n | |       perform a dry-run, where the selected fits cube will be queried for extent and size. |
| --output | OUTPUT filename |      Output cutout FITS file |
| --backend | BACKEND | The backend to use to perform the cutout. The two supported options are 'astropy' and 'objstore'. Default is 'astropy'. |

### Example

```bash
cutouts-service 180.0 -30.0 0.1 "https://example.com/file.fits" --output cutout.fits
cutouts-service 180.0 -30.0 0.1 "s3://example-bucket/file.fits" --output cutout.fits
cutouts-service 180.0 -30.0 0.1 "s3://example-bucket/file.fits" --s3-endpoint-url "https://objects.example.org" --output cutout.fits
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

## Contributing

See [contributing.md](contributing.md) for developer environment setup, uv workflow, and dependency policy.
