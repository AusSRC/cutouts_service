"""Command line interface for future cutout requests."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse


URL_SCHEMES = {"http", "https"}


def build_parser() -> argparse.ArgumentParser:
    """Create the command line parser for cutouts requests."""
    parser = argparse.ArgumentParser(description="Prepare a cutout request")
    parser.add_argument("ra", type=float, help="Right ascension")
    parser.add_argument("dec", type=float, help="Declination")
    parser.add_argument("radius", type=float, help="Cutout radius")
    parser.add_argument("file", help="Input file path or URL")
    return parser


def parse_file_source(value: str) -> tuple[str, str]:
    """Return source kind and normalized value for a file input."""
    parsed = urlparse(value)
    if parsed.scheme in URL_SCHEMES and parsed.netloc:
        return "url", value
    return "path", str(Path(value).expanduser().resolve())


def main(argv: list[str] | None = None) -> int:
    """Run the cutouts-service CLI."""
    args = build_parser().parse_args(argv)
    file_type, file_value = parse_file_source(args.file)

    print(f"ra={args.ra}")
    print(f"dec={args.dec}")
    print(f"radius={args.radius}")
    print(f"file_type={file_type}")
    print(f"file={file_value}")

    return 0
