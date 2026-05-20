"""Cutout generation helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata import Cutout2D
from astropy.wcs import WCS

from cutouts_service.fits_utils import build_cutout_header, open_fits_source


def _find_image_hdu(hdul: fits.HDUList) -> fits.ImageHDU | fits.PrimaryHDU:
    for hdu in hdul:
        if getattr(hdu, "data", None) is not None:
            return hdu
    raise ValueError("No image HDU with data was found in the FITS source")


def _build_spatial_cutout(
    image_hdu: fits.ImageHDU | fits.PrimaryHDU,
    ra: float,
    dec: float,
    radius: float,
) -> tuple[np.ndarray, fits.Header, tuple[slice, ...]]:
    position = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
    size = 2 * radius * u.deg
    wcs = WCS(image_hdu.header)

    if image_hdu.data is None:
        raise ValueError("The selected FITS HDU does not contain image data")

    if image_hdu.data.ndim == 2:
        cutout = Cutout2D(image_hdu.section, position=position, size=size, wcs=wcs)
        data = np.asarray(cutout.data)
        header = build_cutout_header(image_hdu.header, cutout.slices_original, data.shape, data.dtype)
        header.update(cutout.wcs.to_header())
        return data, header, cutout.slices_original

    if image_hdu.data.ndim == 3:
        celestial_wcs = wcs.celestial
        cutout = Cutout2D(image_hdu.section[0, :, :], position=position, size=size, wcs=celestial_wcs)
        spatial_slices = cutout.slices_original
        plane_data = []
        for plane_index in range(image_hdu.data.shape[0]):
            plane_data.append(np.asarray(image_hdu.section[plane_index, spatial_slices[0], spatial_slices[1]]))

        data = np.stack(plane_data, axis=0)
        header = build_cutout_header(
            image_hdu.header,
            (slice(None), spatial_slices[0], spatial_slices[1]),
            data.shape,
            data.dtype,
        )
        header.update(cutout.wcs.to_header())
        return data, header, (slice(None), spatial_slices[0], spatial_slices[1])

    raise ValueError(f"Unsupported image dimensionality: {image_hdu.data.ndim}")


def write_cutout(
    *,
    source: str | Path,
    output_path: str | Path,
    ra: float,
    dec: float,
    radius: float,
    overwrite: bool = False,
) -> Path:
    """Extract a sky cutout and write it to a FITS file."""
    output_path = Path(output_path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output file already exists: {output_path}")

    with open_fits_source(source) as hdul:
        image_hdu = _find_image_hdu(hdul)
        data, header, _ = _build_spatial_cutout(image_hdu, ra, dec, radius)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fits.PrimaryHDU(data=data, header=header).writeto(output_path, overwrite=overwrite)
    return output_path