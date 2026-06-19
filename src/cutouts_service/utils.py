"""Reusable FITS helpers for cutout operations."""

from __future__ import annotations


import logging
from pathlib import Path
from urllib.parse import urlparse

from astropy.io import fits
import validators

ImageLikeHDU = fits.PrimaryHDU | fits.ImageHDU | fits.CompImageHDU
logger = logging.getLogger(__name__)


def is_remote_source(source: str | Path) -> bool:
    """Return whether a source should be opened through fsspec.

    Parameters
    ----------
    source : str | Path
        A URL or Path to the desired file

    Returns
    -------
    bool
        True if URL, False if local file
    """
    logger.info(f"Checking if source is remote source={source}")
    parsed = urlparse(str(source))

    # Object-storage URLs are valid remote sources even when they are not HTTP URLs.
    if parsed.scheme == "s3":
        result = bool(parsed.netloc)
        logger.info(f"Remote source check (s3) source={source} is_remote={result}")
        return result
    result = bool(validators.url(source))
    logger.info(f"Remote source check source={source} is_remote={result}")
    return result
