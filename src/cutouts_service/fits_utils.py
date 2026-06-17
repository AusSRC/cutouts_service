"""Reusable FITS helpers for cutout operations."""

from __future__ import annotations

from contextlib import contextmanager
import logging
from pathlib import Path
from urllib.parse import urlparse

from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy import units as u
import validators
from typing import Any
import numpy as np


_DTYPE_TO_BITPIX = {
    "uint8": 8,
    "int16": 16,
    "int32": 32,
    "int64": 64,
    "float32": -32,
    "float64": -64,
}

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


@contextmanager
def open_fits_source(source: str | Path, s3_endpoint_url: str | None = None):
    """Open the fits source, closing when done

    Parameters
    ----------
    source : str | Path
        The source file
    s3_endpoint_url : str | None, optional
        The s3 endoint to use, by default None

    Yields
    ------
    HDUList
        The list of HDUs containing the image data

    Raises
    ------
    ValueError
        The input file is not a remote file
    """
    logger.info(f"Opening FITS source source={str(source)}")
    if not is_remote_source(source):
        logger.error(f"Rejected non-remote FITS source source={str(source)}")
        raise ValueError("A remote FITS URL is required")

    open_args = (source,)
    open_kwargs: dict[str, Any] = {"use_fsspec": True, "lazy_load_hdus": True}
    parsed_source = urlparse(str(source))
    if parsed_source.scheme == "s3":
        fsspec_kwargs: dict[str, object] = {"anon": True}
        if s3_endpoint_url:
            fsspec_kwargs["client_kwargs"] = {"endpoint_url": s3_endpoint_url}
        open_kwargs["fsspec_kwargs"] = fsspec_kwargs

    logger.info(
        f"Calling astropy.io.fits.open source={str(source)} open_kwargs={open_kwargs}"
    )

    with fits.open(*open_args, **open_kwargs) as handle:
        try:
            hdu_count = len(handle)
        except TypeError:
            hdu_count = None

        logger.info(f"FITS source opened source={str(source)} hdu_count={hdu_count}")
        yield handle


def build_cutout_header(
    source_header: fits.Header,
    slices: list[slice],
    shape: tuple[int, ...],
    section_dtype: np.dtype,
) -> fits.Header:
    """Return a FITS header adjusted for a cutout region.

    Parameters
    ----------
    source_header : fits.Header
        The header of the original fits file
    slices : list[slice]
        The slices that were performed on the fits data
    shape : tuple[int, ...]
        The shape of the data
    section_dtype : np.dtype
        The datatype of the input data

    Returns
    -------
    fits.Header
        The adjusted header to be written with the fits data
    """
    logger.info(
        f"Building cutout header source_naxis={int(source_header.get('NAXIS', len(shape)))} "
        f"shape={tuple(shape)} slices={repr(slices)} section_dtype={getattr(section_dtype, 'name', str(section_dtype))}"
    )
    header = source_header.copy()
    ndim = len(shape)

    header["NAXIS"] = ndim
    header["BITPIX"] = _DTYPE_TO_BITPIX.get(
        getattr(section_dtype, "name", str(section_dtype)), -64
    )

    if (
        float(source_header.get("BSCALE", 1)) != 1.0
        or float(source_header.get("BZERO", 0)) != 0.0
    ):
        header.remove(keyword="BSCALE", remove_all=True)
        header.remove(keyword="BZERO", remove_all=True)

    if source_header.get("CASAMBM", False):
        logger.info("Setting CASAMBM to False, this is not present in the file")
        header.set("CASAMBM", False)

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


def get_cube_details(
    image_hdu: ImageLikeHDU,
    ra: float,
    dec: float,
    radius: float,
    spectral_start_channel: int | None = None,
    spectral_stop_channel: int | None = None,
):
    """Query and print key Cube details from header

    Parameters
    ----------
    image_hdu : ImageLikeHDU
        The HDU containing the image data
    ra : float
        The right ascension of the center of the cutout
    dec : float
        The declination of the center of the cutout
    radius : float
        The radius of the cutout (measured from centre to any edge)
    spectral_start_channel : int | None, optional
        The lower bound for the cutout of the spectral axis, `None` will generate a cutout using the whole spectral range, by default None
    spectral_stop_channel : int | None, optional
        The upper bound for the cutout of the spectral axis, `None` will generate a cutout using the whole spectral range, by default None
    """
    ra = ra * u.deg
    dec = dec * u.deg
    radius = radius * u.deg
    wcs = WCS(image_hdu.header)
    corners = wcs.celestial.calc_footprint()
    axes = wcs.get_axis_types()
    stokes_axis = None
    for i, a in enumerate(axes):
        if a["coordinate_type"] == "stokes":
            stokes_axis = i
    ra_dec_min = SkyCoord(ra=ra - radius, dec=dec - radius)
    ra_dec_max = SkyCoord(ra=ra + radius, dec=dec + radius)

    logger.info(
        "\n\nThe extent of the cube is:\n"
        f"\tRA: {corners[:, 0].min():.3f} -> {corners[:, 0].max():.3f}\n"
        f"\tDec: {corners[:, 1].min():.4f} -> {corners[:, 1].max():.4f}\n"
        f"\tYour request is to create a cutout from {ra_dec_min.to_string()} to {ra_dec_max.to_string()} (corner to corner)\n"
    )
    if wcs.has_spectral:
        nchans = wcs.spectral.array_shape[0]
        spec_lims = wcs.spectral.pixel_to_world_values([0, nchans])
        spec_req = wcs.spectral.pixel_to_world_values(
            [spectral_start_channel, spectral_stop_channel]
        )
        spec_units = wcs.spectral.world_axis_units[0]
        logger.info(
            f"\n\nThere are {nchans} channels\n"
            f"\tThe frequency range is {spec_lims[0]:.3e} -> {spec_lims[1]:.3e} {spec_units}\n"
            f"\tYour request is from channel {spectral_start_channel} ({spec_req[0]:.3e} {spec_units}) to {spectral_stop_channel} ({spec_req[1]:.3e} {spec_units})\n"
        )
    if stokes_axis is not None:
        stokes_size = wcs.array_shape[::-1][stokes_axis]
        logger.info(
            f"\n\nThe STOKES axis has {stokes_size} elements, we will collect all elements\n"
        )
