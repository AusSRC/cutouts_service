"""Cutout generation helpers."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata import Cutout2D
from astropy.wcs import WCS

from cutouts_service.fits_utils import build_cutout_header, open_fits_source


logger = logging.getLogger(__name__)


ImageLikeHDU = fits.PrimaryHDU | fits.ImageHDU | fits.CompImageHDU
_SPECTRAL_CTYPE_PREFIXES = ("FREQ",)


def _header_shape(header: fits.Header) -> tuple[int, ...]:
    naxis = int(header.get("NAXIS", 0))
    if naxis <= 0:
        return ()
    # FITS axis numbering is reverse of NumPy axis ordering.
    return tuple(int(header.get(f"NAXIS{axis}", 0)) for axis in range(naxis, 0, -1))


def _find_image_hdu(hdul: fits.HDUList) -> ImageLikeHDU:
    logger.info(f"Searching for first image HDU with data hdu_count={len(hdul)}")
    for index, hdu in enumerate(hdul):
        if not bool(getattr(hdu, "is_image", False)):
            continue

        header = getattr(hdu, "header", None)
        if header is None:
            continue

        source_shape = _header_shape(header)
        if not source_shape:
            continue
        if any(axis_len <= 0 for axis_len in source_shape):
            continue

        logger.info(
            f"Selected image HDU hdu_index={index} hdu_name={getattr(hdu, 'name', 'UNKNOWN')} "
            f"data_shape={source_shape} data_ndim={len(source_shape)}"
        )
        return hdu
    raise ValueError("No image HDU with data was found in the FITS source")


def _find_spectral_numpy_axis(header: fits.Header, ndim: int) -> int | None:
    for fits_axis in range(1, ndim + 1):
        ctype = str(header.get(f"CTYPE{fits_axis}", "")).upper()
        if any(ctype.startswith(prefix) for prefix in _SPECTRAL_CTYPE_PREFIXES):
            return ndim - fits_axis
    return None


def _build_spatial_cutout(
    image_hdu: ImageLikeHDU,
    ra: float,
    dec: float,
    radius: float,
    spectral_start_pixel: int | None = None,
    spectral_stop_pixel: int | None = None,
) -> tuple[np.ndarray, fits.Header, tuple[slice, ...]]:
    logger.info(
        f"Starting spatial cutout calculation ra_deg={ra} dec_deg={dec} radius_deg={radius}"
    )
    position = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
    size = 2 * radius * u.deg
    wcs = WCS(image_hdu.header)

    source_shape = _header_shape(image_hdu.header)
    if not source_shape:
        raise ValueError("The selected FITS HDU does not contain image data")
    source_ndim = len(source_shape)
    if source_ndim < 2:
        raise ValueError(f"Unsupported image dimensionality: {source_ndim}")

    leading_shape = source_shape[:-2]
    leading_slices: list[slice] = [slice(None)] * len(leading_shape)
    if (spectral_start_pixel is None) != (spectral_stop_pixel is None):
        raise ValueError("Both spectral_start_pixel and spectral_stop_pixel must be provided together")

    if spectral_start_pixel is not None:
        spectral_axis = _find_spectral_numpy_axis(image_hdu.header, source_ndim)
        if spectral_axis is None or spectral_axis >= len(leading_shape):
            raise ValueError("No spectral axis found in the source FITS cube")
        if spectral_start_pixel < 0:
            raise ValueError("spectral_start_pixel must be non-negative")
        if spectral_stop_pixel < spectral_start_pixel:
            raise ValueError("spectral_stop_pixel must be greater than or equal to spectral_start_pixel")

        spectral_axis_size = source_shape[spectral_axis]
        if spectral_stop_pixel >= spectral_axis_size:
            raise ValueError(
                f"spectral_stop_pixel {spectral_stop_pixel} is out of bounds for spectral axis size {spectral_axis_size}"
            )
        leading_slices[spectral_axis] = slice(spectral_start_pixel, spectral_stop_pixel + 1)

    selected_leading_shape = []
    for axis_size, axis_slice in zip(leading_shape, leading_slices):
        start = 0 if axis_slice.start is None else axis_slice.start
        stop = axis_size if axis_slice.stop is None else axis_slice.stop
        selected_leading_shape.append(stop - start)
    selected_leading_shape = tuple(selected_leading_shape)

    sample_prefix = tuple(
        (0 if axis_slice.start is None else axis_slice.start) for axis_slice in leading_slices
    )
    sample_plane = image_hdu.section[sample_prefix + (slice(None), slice(None))]
    cutout = Cutout2D(sample_plane, position=position, size=size, wcs=wcs.celestial)
    y_slice, x_slice = cutout.slices_original

    logger.info(
        f"Derived spatial slices source_shape={source_shape} spatial_slices={repr((y_slice, x_slice))}"
    )

    if not selected_leading_shape:
        data = np.asarray(cutout.data)
    else:
        slab_data = []
        for selected_index in np.ndindex(*selected_leading_shape):
            source_index = []
            for axis_index, axis_slice in enumerate(leading_slices):
                offset = 0 if axis_slice.start is None else axis_slice.start
                source_index.append(offset + selected_index[axis_index])
            slab_data.append(np.asarray(image_hdu.section[tuple(source_index) + (y_slice, x_slice)]))
        data = np.stack(slab_data, axis=0).reshape(selected_leading_shape + tuple(cutout.data.shape))

    slices_for_header = tuple(leading_slices) + (y_slice, x_slice)
    logger.info(
        f"Computed cutout source_shape={source_shape} cutout_shape={tuple(data.shape)} "
        f"leading_axes={leading_shape} selected_leading_axes={selected_leading_shape}"
    )
    header = build_cutout_header(image_hdu.header, slices_for_header, data.shape, data.dtype)
    header.update(cutout.wcs.to_header())
    return data, header, slices_for_header


def write_cutout(
    *,
    source: str | Path,
    output_path: str | Path,
    ra: float,
    dec: float,
    radius: float,
    s3_endpoint_url: str | None = None,
    spectral_start_pixel: int | None = None,
    spectral_stop_pixel: int | None = None,
    overwrite: bool = False,
) -> Path:
    """Extract a sky cutout and write it to a FITS file."""
    output_path = Path(output_path)
    logger.info(
        f"Preparing cutout request source={str(source)} output_path={str(output_path)} "
        f"ra_deg={ra} dec_deg={dec} radius_deg={radius} s3_endpoint_url={s3_endpoint_url} "
        f"spectral_start_pixel={spectral_start_pixel} spectral_stop_pixel={spectral_stop_pixel} overwrite={overwrite}"
    )
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {output_path}")

    logger.info("Opening FITS source")
    with open_fits_source(source, s3_endpoint_url=s3_endpoint_url) as hdul:
        logger.info(f"Opened FITS source hdu_count={len(hdul)}")
        image_hdu = _find_image_hdu(hdul)
        data, header, _ = _build_spatial_cutout(
            image_hdu,
            ra,
            dec,
            radius,
            spectral_start_pixel=spectral_start_pixel,
            spectral_stop_pixel=spectral_stop_pixel,
        )

    logger.info(f"Ensuring output directory exists output_directory={str(output_path.parent)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        f"Writing cutout to output FITS output_path={str(output_path)} output_shape={tuple(data.shape)}"
    )
    fits.PrimaryHDU(data=data, header=header).writeto(output_path, overwrite=overwrite)
    logger.info(f"Cutout write complete output_path={str(output_path)}")
    return output_path