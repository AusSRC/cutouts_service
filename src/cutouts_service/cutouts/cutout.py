"""Cutout generation helpers."""

from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any


import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from dataclasses import dataclass

logger = logging.getLogger(__name__)

_DTYPE_TO_BITPIX = {
    "uint8": 8,
    "int16": 16,
    "int32": 32,
    "int64": 64,
    "float32": -32,
    "float64": -64,
}

ImageLikeHDU = fits.PrimaryHDU | fits.ImageHDU | fits.CompImageHDU


@dataclass
class IOConfig:
    source: str | Path
    output_path: str | Path
    s3_endpoint_url: str | None = None


@dataclass
class CutoutConfig:
    ra: float
    dec: float
    radius: float
    channel_range: tuple[int, ...] | tuple[None, ...] = (None, None)


@dataclass
class Options:
    dry_run: bool = False


class Cutout(ABC):
    """A general cutout class that needs a to be overwritten with a specific tool"""

    def __init__(
        self,
        io_config: IOConfig,
        cutout_config: CutoutConfig,
        options: Options = Options(),
    ) -> None:
        # input attributes
        self.io_config = io_config
        self.cutout_config = cutout_config
        self.dry_run = options.dry_run

        # to be set while opening remote file
        self.source_header: dict[str, Any]
        self.fits_shape: tuple[int, ...]
        self.pixel_indices: dict[str, int]
        self.axis_types: tuple[str]

    def _set_header_shape(self, header: dict[str, Any]):
        """Get the shape of the fits file form the header

        Returns
        -------
        tuple[int, ...]
            The shape of the fits data
        """

        if not header:
            raise TypeError("The header has not yet been retrieved")
        naxis = int(header.get("NAXIS", 0))
        if naxis <= 0:
            self.fits_shape = ()
        # FITS axis numbering is reverse of NumPy axis ordering.
        self.fits_shape = tuple(
            int(header.get(f"NAXIS{axis}", 0)) for axis in range(naxis, 0, -1)
        )

    def _compute_pixel_indices(self):
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
        dict[str, int | list[str]]
            Contains the pixel extents within the fits array as well as a list of axis types
        """

        header = self.source_header
        position = SkyCoord(
            ra=self.cutout_config.ra * u.deg, dec=self.cutout_config.dec * u.deg
        )
        size = 2 * self.cutout_config.radius * u.deg
        wcs = WCS(fits.Header(header))
        ra_dec_min = position.spherical_offsets_by(-size / 2, -size / 2)
        ra_dec_max = position.spherical_offsets_by(size / 2, size / 2)
        x0, y0 = wcs.celestial.world_to_pixel(ra_dec_min)
        x1, y1 = wcs.celestial.world_to_pixel(ra_dec_max)
        x_min = np.floor(min(x0, x1))
        x_max = np.ceil(max(x0, x1))
        y_min = np.floor(min(y0, y1))
        y_max = np.ceil(max(y0, y1))

        axis_types = tuple(
            header.get(f"CTYPE{i + 1}", "").upper() for i in range(header["NAXIS"])
        )
        self.pixel_indices = {
            "xmin": int(x_min),
            "xmax": int(x_max),
            "ymin": int(y_min),
            "ymax": int(y_max),
        }
        self.axis_types = axis_types

    @abstractmethod
    def create_cutout(self, overwrite: bool = False):
        """Extract a sky cutout and write it to a FITS file."""
        raise NotImplementedError(
            "This method must be overwritten with the specific cutout implementation"
        )

    def check_cutout_fit(self) -> bool:
        """Checks if the requested cutout fits in the given cube

        Returns
        -------
        bool
            True if the cutout fits, False if it doesn't.
        """
        shape = self.fits_shape[::-1]
        chans = self.cutout_config.channel_range
        cutout_indices = self.pixel_indices
        if cutout_indices["xmin"] < 0 or cutout_indices["xmax"] > (shape[0] - 1):
            return False
        if cutout_indices["ymin"] < 0 or cutout_indices["ymax"] > (shape[1] - 1):
            return False
        if chans[0] is not None and chans[1] is not None:
            if chans[0] < 0 or chans[1] > (shape[-1] - 1):
                return False
        return True

    def _get_cube_details(self):
        """Query and print key Cube details from header"""

        co_c = self.cutout_config
        ra = co_c.ra * u.deg
        dec = co_c.dec * u.deg
        radius = co_c.radius * u.deg
        wcs = WCS(self.source_header)

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
            if co_c.channel_range[0] is None or co_c.channel_range[1] is None:
                spec_req = None
            else:
                spec_req = wcs.spectral.pixel_to_world_values(co_c.channel_range)
            spec_units = wcs.spectral.world_axis_units[0]
            logger.info(
                f"\n\nThere are {nchans} channels\n"
                f"\tThe frequency range is {spec_lims[0]:.3e} -> {spec_lims[1]:.3e} {spec_units}\n"
            )
            if spec_req is None:
                print("All channels have been requested")
            else:
                print(
                    f"\tYour request is from channel {co_c.channel_range[0]} ({spec_req[0]:.3e} {spec_units}) to {co_c.channel_range[1]} ({spec_req[1]:.3e} {spec_units})\n"
                )
        if stokes_axis is not None:
            stokes_size = wcs.array_shape[::-1][stokes_axis]
            logger.info(
                f"\n\nThe STOKES axis has {stokes_size} elements, we will collect all elements\n"
            )

    def build_cutout_header(
        self, slices: list[slice], shape: tuple[int, ...], section_dtype: np.dtype
    ) -> fits.Header:
        """Return a FITS header adjusted for a cutout region.

        Parameters
        ----------
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
            f"Building cutout header source_naxis={int(self.source_header.get('NAXIS', len(shape)))} "
            f"shape={tuple(shape)} slices={repr(slices)} section_dtype={getattr(section_dtype, 'name', str(section_dtype))}"
        )
        header = fits.Header(self.source_header.copy())
        ndim = len(shape)

        header["NAXIS"] = ndim
        header["BITPIX"] = _DTYPE_TO_BITPIX.get(
            getattr(section_dtype, "name", str(section_dtype)), -64
        )

        if (
            float(header.get("BSCALE", 1)) != 1.0
            or float(header.get("BZERO", 0)) != 0.0
        ):
            header.remove(keyword="BSCALE", remove_all=True)
            header.remove(keyword="BZERO", remove_all=True)

        if header.get("CASAMBM", False):
            logger.info("Setting CASAMBM to False, this is not present in the file")
            header.set("CASAMBM", False)

        for numpy_axis, cutout_slice in enumerate(slices):
            fits_axis = ndim - numpy_axis
            start = cutout_slice.start if cutout_slice.start is not None else 0
            stop = (
                cutout_slice.stop
                if cutout_slice.stop is not None
                else shape[numpy_axis]
            )

            naxis_key = f"NAXIS{fits_axis}"
            previous_naxis = self.source_header.get(naxis_key, "undefined")
            header[naxis_key] = stop - start
            crpix_key = f"CRPIX{fits_axis}"
            if crpix_key in self.source_header:
                old_crpix = float(self.source_header[crpix_key])
                header[crpix_key] = float(self.source_header[crpix_key]) - start
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
