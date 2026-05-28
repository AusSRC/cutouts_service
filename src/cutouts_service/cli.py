"""Command line interface for future cutout requests."""

from __future__ import annotations

import argparse
import logging

from cutouts_service.cutout import write_cutout
from cutouts_service.fits_utils import is_remote_source


logger = logging.getLogger(__name__)
ARCMIN_PER_DEG = 60.0
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def configure_logging(level_name: str) -> None:
    """Configure root logging for the CLI."""
    requested_log_level = getattr(logging, level_name)
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=requested_log_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        return

    root_logger.setLevel(requested_log_level)


def build_parser() -> argparse.ArgumentParser:
    """Create the command line parser for cutouts requests."""
    parser = argparse.ArgumentParser(description="Prepare a cutout request")
    parser.add_argument("ra", type=float, help="Right ascension")
    parser.add_argument("dec", type=float, help="Declination")
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
        "--spectral-start-pixel",
        type=int,
        default=None,
        help="Optional inclusive start pixel for spectral-axis cutout",
    )
    parser.add_argument(
        "--spectral-stop-pixel",
        type=int,
        default=None,
        help="Optional inclusive stop pixel for spectral-axis cutout",
    )
    parser.add_argument("--output", required=True, help="Output cutout FITS file")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the cutouts-service CLI."""
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)

    logger.info("Parsing CLI arguments")
    radius_deg = args.radius / ARCMIN_PER_DEG
    if (args.spectral_start_pixel is None) != (args.spectral_stop_pixel is None):
        raise ValueError("Both --spectral-start-pixel and --spectral-stop-pixel must be provided together")
    if args.spectral_start_pixel is not None and args.spectral_stop_pixel < args.spectral_start_pixel:
        raise ValueError("--spectral-stop-pixel must be greater than or equal to --spectral-start-pixel")

    logger.info(
        f"Received cutout request ra_deg={args.ra} dec_deg={args.dec} "
        f"radius_arcmin={args.radius} radius_deg={radius_deg} source={args.file} output_path={args.output} "
        f"spectral_start_pixel={args.spectral_start_pixel} spectral_stop_pixel={args.spectral_stop_pixel}"
    )
    if not is_remote_source(args.file):
        logger.error(f"Source validation failed: source is not remote source={args.file}")
        raise ValueError("A remote FITS URL is required")
    logger.info(f"Source validation successful source={args.file}")

    logger.info("Starting cutout write")
    write_cutout(
        source=args.file,
        output_path=args.output,
        ra=args.ra,
        dec=args.dec,
        radius=radius_deg,
        s3_endpoint_url=args.s3_endpoint_url,
        spectral_start_pixel=args.spectral_start_pixel,
        spectral_stop_pixel=args.spectral_stop_pixel,
    )
    logger.info(f"Cutout command finished successfully output_path={args.output}")

    return 0
