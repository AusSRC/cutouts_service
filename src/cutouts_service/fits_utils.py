"""Reusable FITS helpers for cutout operations."""

from __future__ import annotations

from contextlib import contextmanager
import logging
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


logger = logging.getLogger(__name__)


def is_remote_source(source: str) -> bool:
    """Return whether a source should be opened through fsspec."""
    logger.info(f"Checking if source is remote source={source}")
    parsed = urlparse(source)

    # Object-storage URLs are valid remote sources even when they are not HTTP URLs.
    if parsed.scheme == "s3":
        result = bool(parsed.netloc)
        logger.info(f"Remote source check (s3) source={source} is_remote={result}")
        return result
    result = bool(validators.url(source))
    logger.info(f"Remote source check source={source} is_remote={result}")
    return result


@contextmanager
def open_fits_source(source: str | Path, s3_endpoint_url: str | None = None):
    """Open a remote FITS source with lazy fsspec-backed access."""
    logger.info(f"Opening FITS source source={str(source)}")
    if not is_remote_source(source):
        logger.error(f"Rejected non-remote FITS source source={str(source)}")
        raise ValueError("A remote FITS URL is required")

    open_args = (source,)
    open_kwargs: dict[str, object] = {"use_fsspec": True, "lazy_load_hdus": True}
    parsed_source = urlparse(str(source))
    if parsed_source.scheme == "s3":
        fsspec_kwargs: dict[str, object] = {"anon": True}
        if s3_endpoint_url:
            fsspec_kwargs["client_kwargs"] = {"endpoint_url": s3_endpoint_url}
        open_kwargs["fsspec_kwargs"] = fsspec_kwargs

    logger.info(f"Calling astropy.io.fits.open source={str(source)} open_kwargs={open_kwargs}")

    with fits.open(*open_args, **open_kwargs) as handle:
        try:
            hdu_count = len(handle)
        except TypeError:
            hdu_count = None

        logger.info(
            f"FITS source opened source={str(source)} hdu_count={hdu_count}"
        )
        yield handle


def build_cutout_header(
    source_header: fits.Header,
    slices: tuple[slice, ...],
    shape: tuple[int, ...],
    section_dtype,
) -> fits.Header:
    """Return a FITS header adjusted for a cutout region."""
    logger.info(
        f"Building cutout header source_naxis={int(source_header.get('NAXIS', len(shape)))} "
        f"shape={tuple(shape)} slices={repr(slices)} section_dtype={getattr(section_dtype, 'name', str(section_dtype))}"
    )
    header = source_header.copy()
    ndim = len(shape)

    header["NAXIS"] = ndim
    header["BITPIX"] = _DTYPE_TO_BITPIX.get(getattr(section_dtype, "name", str(section_dtype)), -64)

    if float(source_header.get("BSCALE", 1)) != 1.0 or float(source_header.get("BZERO", 0)) != 0.0:
        header.remove(keyword="BSCALE", remove_all=True)
        header.remove(keyword="BZERO", remove_all=True)

    for numpy_axis, cutout_slice in enumerate(slices):
        fits_axis = ndim - numpy_axis
        start = cutout_slice.start if cutout_slice.start is not None else 0
        stop = cutout_slice.stop if cutout_slice.stop is not None else shape[numpy_axis]

        naxis_key = f"NAXIS{fits_axis}" 
        previous_naxis = source_header.get(naxis_key, "undefined")
        header[naxis_key] = stop - start
        crpix_key = f"CRPIX{fits_axis}"
        if crpix_key in source_header:
            old_crpix = float(source_header[crpix_key])
            header[crpix_key] = float(source_header[crpix_key]) - start
            logger.info(
                f"Updated WCS reference pixel axis={fits_axis} slice_start={start} "
                f"slice_stop={stop} old_crpix={old_crpix} new_crpix={float(header[crpix_key])}"
            )

        logger.info(
            f"Updated axis length axis={fits_axis} old_naxis={previous_naxis} "
            f"new_naxis={int(header[naxis_key])} slice_start={start} slice_stop={stop}"
        )

    logger.info(
        f"Cutout header build complete naxis={int(header['NAXIS'])} "
        f"shape={tuple(shape)} bitpix={int(header['BITPIX'])}"
    )
    return header