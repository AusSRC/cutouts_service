"""Command line interface for future cutout requests."""

import argparse
import logging

from cutouts_service.cutouts import (
    AstropyCutout,
    CutoutConfig,
    IOConfig,
    ObjStoreCutout,
    Options,
    SPECTRAL_UNITS,
)

logger = logging.getLogger(__name__)
ARCMIN_PER_DEG = 60.0
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

BACKENDS = {"astropy": AstropyCutout, "objstore": ObjStoreCutout}


def configure_logging(level_name: str):
    """Configure root logging for the CLI.

    Parameters
    ----------
    level_name : str
        The logging level to use, one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`
    """
    requested_log_level = getattr(logging, level_name)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=requested_log_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    else:
        root_logger.setLevel(requested_log_level)


def build_parser() -> argparse.ArgumentParser:
    """Create the command line parser for cutouts requests.

    Returns
    -------
    argparse.ArgumentParser
        The parser containing the command line arguments
    """

    parser = argparse.ArgumentParser(description="Prepare a cutout request")
    parser.add_argument("ra", type=float, help="Right ascension in decimal degrees")
    parser.add_argument("dec", type=float, help="Declination in decimal degrees")
    parser.add_argument("radius", type=float, help="Cutout radius in arcminutes")
    parser.add_argument("file", help="Input file path or URL")
    parser.add_argument(
        "--s3-endpoint-url",
        default=None,
        help="Optional S3-compatible endpoint URL for s3:// sources",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=LOG_LEVELS,
        help="Logging verbosity level (default: INFO)",
    )
    parser.add_argument(
        "--spectral-units",
        choices=SPECTRAL_UNITS,
        default="channels",
        help=f"The unit selection for specifying the spectral bounds, can be one of {SPECTRAL_UNITS}, default is `channels`."
    )
    parser.add_argument(
        "--spectral-min",
        type=float,
        default=None,
        help="The lower bound of the cutout request along the spectral axis, the units are specified by the `--spectral-unit` option. Default is to request all channels. Note: the channel number is zero-indexed, i.e. enter 0 to retrieve the first channel.",
    )
    parser.add_argument(
        "--spectral-max",
        type=float,
        default=None,
        help="The lower bound of the cutout request along the spectral axis, the units are specified by the `--spectral-unit` option. Default is to request all channels. Note: the channel number is zero-indexed, i.e. enter 0 to retrieve the first channel.",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="perform a dry-run, where the selected fits cube will be queried for extent and size.",
    )
    parser.add_argument("--output", required=True, help="Output cutout FITS file")
    parser.add_argument(
        "--backend",
        choices=BACKENDS.keys(),
        default="astropy",
        help="The backend to use to perform the cutout. The two supported options are 'astropy' and 'objstore'. Default is 'astropy'.",
    )
    return parser


def main(argv: list[str] | None = None):
    """Run the cutouts-service CLI.

    Example
    -------
    The service can be run using::

        cutouts-service [-h] [--s3-endpoint-url S3_ENDPOINT_URL] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--spectral-unit {channels,Hz,KHz,MHz,GHz}] [--spectral-min SPECTRAL_MIN]
                       [--spectral-max SPECTRAL_MAX] [-n] --output OUTPUT [--backend {astropy,objstore}]
                       ra dec radius file

    Parameters
    ----------
    argv : list[str] | None
        The command line arguments

    Raises
    ------
    ValueError
        If the combination of `spectral-min` and `spectral-max` is inconsistent (i.e. `start` > `stop`) or if the remote URL is invalid
    ValueError
        If the backend argument is not one of 'astropy' or 'objstore'
    """
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)

    logger.info("Parsing CLI arguments")
    radius_deg = args.radius / ARCMIN_PER_DEG
    if (args.spectral_min is None) != (args.spectral_max is None):
        raise ValueError(
            "Both --spectral-min and --spectral-max must be provided together"
        )
    if (
        args.spectral_min is not None
        and args.spectral_max < args.spectral_min
    ):
        raise ValueError(
            "--spectral-min must be greater than or equal to --spectral-max"
        )
    if args.backend not in BACKENDS:
        raise ValueError(
            f"The --backend argument must be one of {', '.join(BACKENDS.keys())}"
        )

    logger.info(
        f"Received cutout request ra_deg={args.ra} dec_deg={args.dec} "
        f"radius_arcmin={args.radius} radius_deg={radius_deg} source={args.file} output_path={args.output} "
        f"spectral_min={args.spectral_min} spectral_max={args.spectral_max} spectral_units={args.spectral_units}"
    )

    logger.info("Starting cutout write")
    io_config = IOConfig(args.file, args.output, args.s3_endpoint_url)
    cutout_config = CutoutConfig(
        args.ra,
        args.dec,
        radius_deg,
        (args.spectral_min, args.spectral_max),
        args.spectral_units,
    )
    options = Options(args.dry_run)
    try:
        cutout = BACKENDS[args.backend](io_config, cutout_config, options)
    except IndexError:
        raise ValueError(
            f"The --backend argument must be one of {', '.join(BACKENDS.keys())}"
        )

    output_path = cutout.create_cutout()
    if args.dry_run:
        logger.info("Dry-run performed")
    else:
        logger.info(f"Cutout command finished successfully output_path={output_path}")
