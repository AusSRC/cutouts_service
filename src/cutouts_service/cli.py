"""Command line interface for future cutout requests."""

import argparse
import logging

from cutouts_service.cutouts.astropy_cutout import (
    AstropyCutout,
    IOConfig,
    CutoutConfig,
    Options,
)


logger = logging.getLogger(__name__)
ARCMIN_PER_DEG = 60.0
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


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
    """Create the command line parser for cutouts requests."""

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
        "--spectral-start-channel",
        type=int,
        default=None,
        help="Optional inclusive start channel for spectral-axis cutout, set "
        "spectral-start-channel and spectral-stop-channel to the same value for "
        "a single channel. Default is all channels.",
    )
    parser.add_argument(
        "--spectral-stop-channel",
        type=int,
        default=None,
        help="Optional inclusive stop channel for spectral-axis cutout, set "
        "spectral-start-channel and spectral-stop-channel to the same value for "
        "a single channel. Default is all channels.",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="perform a dry-run, where the selected fits cube will be queried for extent and size.",
    )
    parser.add_argument("--output", required=True, help="Output cutout FITS file")
    return parser


def main(argv: list[str] | None = None):
    """Run the cutouts-service CLI.

    Example
    -------
    The service can be run using::

        cutouts-service [-h] [--s3-endpoint-url S3_ENDPOINT_URL] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--spectral-start-channel SPECTRAL_START_CHANNEL]
            [--spectral-stop-channel SPECTRAL_STOP_CHANNEL] [--dry-run] --output OUTPUT
            ra dec radius file

    Parameters
    ----------
    argv : list[str] | None
        The command line arguments

    Raises
    ------
    ValueError
        If the combination of `spectral-start-channel` and `spectral-stop-channel` is inconsistent (i.e. `start` > `stop`) or if the remote URL is invalid
    """
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)

    logger.info("Parsing CLI arguments")
    radius_deg = args.radius / ARCMIN_PER_DEG
    if (args.spectral_start_channel is None) != (args.spectral_stop_channel is None):
        raise ValueError(
            "Both --spectral-start-channel and --spectral-stop-channel must be provided together"
        )
    if (
        args.spectral_start_channel is not None
        and args.spectral_stop_channel < args.spectral_start_channel
    ):
        raise ValueError(
            "--spectral-stop-channel must be greater than or equal to --spectral-start-channel"
        )

    logger.info(
        f"Received cutout request ra_deg={args.ra} dec_deg={args.dec} "
        f"radius_arcmin={args.radius} radius_deg={radius_deg} source={args.file} output_path={args.output} "
        f"spectral_start_pixel={args.spectral_start_channel} spectral_stop_pixel={args.spectral_stop_channel}"
    )

    logger.info("Starting cutout write")
    io_config = IOConfig(args.file, args.output, args.s3_endpoint_url)
    cutout_config = CutoutConfig(
        args.ra,
        args.dec,
        radius_deg,
        (args.spectral_start_channel, args.spectral_stop_channel),
    )
    options = Options(args.dry_run)
    cutout = AstropyCutout(io_config, cutout_config, options)
    output_path = cutout.create_cutout()
    if args.dry_run:
        logger.info("Dry-run performed")
    else:
        logger.info(f"Cutout command finished successfully output_path={output_path}")
