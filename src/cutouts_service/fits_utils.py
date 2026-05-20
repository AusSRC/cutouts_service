"""Reusable FITS helpers for cutout operations."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from astropy.io import fits
import validators


_DTYPE_TO_BITPIX = {
    "uint8": 8,
    "int16": 16,
    "int32": 32,
    "int64": 64,
    "float32": -32,
    "float64": -64,
}


def is_remote_source(source: str) -> bool:
    """Return whether a source should be opened through fsspec."""
    parsed = urlparse(source)

    # Object-storage URLs are valid remote sources even when they are not HTTP URLs.
    if parsed.scheme == "s3":
        return bool(parsed.netloc)
    return bool(validators.url(source))


@contextmanager
def open_fits_source(source: str | Path):
    """Open a remote FITS source with lazy fsspec-backed access."""
    if not is_remote_source(source):
        raise ValueError("A remote FITS URL is required")

    open_args = (source,)
    open_kwargs = {"use_fsspec": True, "lazy_load_hdus": True}

    with fits.open(*open_args, **open_kwargs) as handle:
        yield handle


def build_cutout_header(
    source_header: fits.Header,
    slices: tuple[slice, ...],
    shape: tuple[int, ...],
    section_dtype,
) -> fits.Header:
    """Return a FITS header adjusted for a cutout region."""
    header = source_header.copy()
    ndim = len(shape)

    header["NAXIS"] = ndim
    header["BITPIX"] = _DTYPE_TO_BITPIX.get(getattr(section_dtype, "name", str(section_dtype)), -64)

    if float(source_header.get("BSCALE", 1)) != 1.0 or float(source_header.get("BZERO", 0)) != 0.0:
        header.set(keyword="BSCALE", value=1.0)
        header.set(keyword="BZERO", value=0.0)

    for numpy_axis, cutout_slice in enumerate(slices):
        fits_axis = ndim - numpy_axis
        start = cutout_slice.start if cutout_slice.start is not None else 0
        stop = cutout_slice.stop if cutout_slice.stop is not None else shape[numpy_axis]

        header[f"NAXIS{fits_axis}"] = stop - start
        crpix_key = f"CRPIX{fits_axis}"
        if crpix_key in source_header:
            header[crpix_key] = float(source_header[crpix_key]) - start

    return header