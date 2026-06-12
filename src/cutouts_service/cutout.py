"""Cutout generation helpers."""

import logging
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from cutouts_service.fits_utils import build_cutout_header, open_fits_source,get_cube_details


logger = logging.getLogger(__name__)


ImageLikeHDU = fits.PrimaryHDU | fits.ImageHDU | fits.CompImageHDU
_SPECTRAL_CTYPE_PREFIXES = ("FREQ",)


def _header_shape(header: fits.Header) -> tuple[int, ...]:
    """Get the shape of the fits file form the header

    Parameters
    ----------
    header : fits.Header
        The fits header to get the shape from

    Returns
    -------
    tuple[int, ...]
        The shape of the fits data
    """
    naxis = int(header.get("NAXIS", 0))
    if naxis <= 0:
        return ()
    # FITS axis numbering is reverse of NumPy axis ordering.
    return tuple(int(header.get(f"NAXIS{axis}", 0)) for axis in range(naxis, 0, -1))


def _find_image_hdu(hdul: fits.HDUList) -> ImageLikeHDU:
    """Find the HDU that contains the image data, useful if there are more than one HDU within the HDUList

    Parameters
    ----------
    hdul : fits.HDUList
        The HDUList within which to search

    Returns
    -------
    ImageLikeHDU
        A fits HDU that contains the required image data

    Raises
    ------
    ValueError
        If there was no ImageHDU found within the fits file
    """
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


def compute_pixel_indices(header: fits.Header, position: SkyCoord, size: u.Quantity) -> dict[str, float | list[str]]:
    """Compute the array indices from the input celestial coordinates

    Parameters
    ----------
    header : fits.Header
        The header containing the WCS information needed to do the conversion
    position : SkyCoord
        The sky position of the center of the cutout
    size : u.Quantity
        The size of the intended cutout (assuming a square cutout)

    Returns
    -------
    dict[str, float | list[str]]
        Contains the pixel extents within the fits array as well as a list of axis types
    """

    wcs = WCS(header)
    ra_dec_min = position.spherical_offsets_by(-size/2, -size/2)
    ra_dec_max = position.spherical_offsets_by(size/2, size/2)
    x0, y0 = wcs.celestial.world_to_pixel(ra_dec_min)
    x1, y1 = wcs.celestial.world_to_pixel(ra_dec_max)
    x_min = np.floor(min(x0,x1))
    x_max = np.ceil(max(x0,x1))
    y_min = np.floor(min(y0,y1))
    y_max = np.ceil(max(y0,y1))

    axis_types = [
        header.get(f"CTYPE{i+1}", "").upper()
        for i in range(header["NAXIS"])
    ]

    return {"xmin":int(x_min),
            "xmax":int(x_max),
            "ymin":int(y_min),
            "ymax":int(y_max),
            "axis_types": axis_types}


def _build_spatial_cutout(
    image_hdu: ImageLikeHDU,
    ra: float,
    dec: float,
    radius: float,
    spectral_start_channel: int | None = None,
    spectral_stop_channel: int | None = None,
) -> tuple[np.ndarray, fits.Header, list[slice]]:
    """Generate a cutout of a fits file

    Parameters
    ----------
    image_hdu : ImageLikeHDU
        The HDU containing the image
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

    Returns
    -------
    tuple[np.ndarray, fits.Header, list[slice]]
        The data array, header, and slices generated for this cutout

    Raises
    ------
    ValueError
        If The selected FITS HDU does not contain image data or the dimensionality is unsupported
    """
    logger.info(
        f"Starting spatial cutout calculation ra_deg={ra} dec_deg={dec} radius_deg={radius}"
    )
    position = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
    size = 2 * radius * u.deg

    source_shape = _header_shape(image_hdu.header)
    if not source_shape:
        raise ValueError("The selected FITS HDU does not contain image data")
    source_ndim = len(source_shape)
    if source_ndim < 2:
        raise ValueError(f"Unsupported image dimensionality: {source_ndim}")

    indices = compute_pixel_indices(image_hdu.header, position, size)
    indices.update({"zmin":spectral_start_channel,
                    "zmax":spectral_stop_channel})
    
    slices = []
    for ctype in indices["axis_types"]:
        if "RA" in ctype:
            slices.append(slice(indices["xmin"], indices["xmax"]+1))
        elif "DEC" in ctype:
            slices.append(slice(indices["ymin"], indices["ymax"]+1))
        elif "FREQ" in ctype:
            slices.append(slice(indices["zmin"], indices["zmax"] if indices["zmax"] is None else indices["zmax"]+1))
        elif "STOKES" in ctype:
            slices.append(slice(None))
    
    slices = tuple(slices[::-1])
    logger.info("pixel slice calculated: %s", slices)
    logger.info("performing slice")

    data = image_hdu.section[slices]


    header = build_cutout_header(image_hdu.header, slices, data.shape, data.dtype)
    return data, header, slices


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
    dry_run: bool = False
) -> Path:
    """Extract a sky cutout and write it to a FITS file.

    Parameters
    ----------
    source : str | Path
        The URI where the file exists
    output_path : str | Path
        Where the output file should go
    ra : float
        The right ascension of the center of the cutout
    dec : float
        The declination of the center of the cutout
    radius : float
        The radius of the cutout in degrees
    s3_endpoint_url : str | None, optional
        The s3 endpoint to use, by default None
    spectral_start_pixel : int | None, optional
        The lower bound on the spectral axis, by default None
    spectral_stop_pixel : int | None, optional
        The upper bound on the spectral axis, by default None
    overwrite : bool, optional
        allow overwriting of the output file, by default False
    dry_run : bool, optional
        Access the remote file, read the header and return the extents, don't do any cutout, by default False

    Returns
    -------
    Path
        The path to the output file

    Raises
    ------
    FileExistsError
        If the output file already exists and `overwrite` is set to False
    """ 
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
        if dry_run:
            get_cube_details(image_hdu, ra, dec, radius, spectral_start_pixel, spectral_stop_pixel)
        else:
            data, header, _ = _build_spatial_cutout(
                image_hdu,
                ra,
                dec,
                radius,
                spectral_start_channel=spectral_start_pixel,
                spectral_stop_channel=spectral_stop_pixel,
            )
    if not dry_run:
        logger.info(f"Ensuring output directory exists output_directory={str(output_path.parent)}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"Writing cutout to output FITS output_path={str(output_path)} output_shape={tuple(data.shape)}"
        )
        fits.PrimaryHDU(data=data, header=header).writeto(output_path, overwrite=overwrite)
        logger.info(f"Cutout write complete output_path={str(output_path)}")
    return output_path