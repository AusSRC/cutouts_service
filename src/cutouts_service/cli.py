"""Command line interface for future cutout requests."""

from __future__ import annotations

import argparse

from cutouts_service.cutout import write_cutout
from cutouts_service.fits_utils import is_remote_source


def build_parser() -> argparse.ArgumentParser:
    """Create the command line parser for cutouts requests."""
    parser = argparse.ArgumentParser(description="Prepare a cutout request")
    parser.add_argument("ra", type=float, help="Right ascension")
    parser.add_argument("dec", type=float, help="Declination")
    parser.add_argument("radius", type=float, help="Cutout radius")
    parser.add_argument("file", help="Input file path or URL")
    parser.add_argument("--output", required=True, help="Output cutout FITS file")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the cutouts-service CLI."""
    args = build_parser().parse_args(argv)
    if not is_remote_source(args.file):
        raise ValueError("A remote FITS URL is required")
    write_cutout(
        source=args.file,
        output_path=args.output,
        ra=args.ra,
        dec=args.dec,
        radius=args.radius,
    )

    return 0
