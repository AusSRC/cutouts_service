"""Cutout generation helpers."""

import logging
from pathlib import Path

import numpy as np
from astropy.io import fits

from cutouts_service import FITSheader, URLObject
from cutouts_service.cutouts import (
    Cutout,
    CutoutConfig,
    IOConfig,
    Options,
)
from cutouts_service.cutouts.cutout import _DTYPE_TO_BITPIX

logger = logging.getLogger(__name__)


class ObjStoreCutout(Cutout):
    """A cutout class encapsulating the cutout from a remote source using astropy

    Parameters
    ----------
    io_config : IOConfig
        The config describing the IO details (eg. url)
    cutout_config : CutoutConfig
        The config describing the cutout details (eg. pointing)
    options : Options
        The extra options, currently contains only dry_run

    Attributes
    ----------
    header_from_url : FITSheader.FITSheaderFromURL
        The header in objstore native format
    """

    def __init__(
        self,
        io_config: IOConfig,
        cutout_config: CutoutConfig,
        options: Options | None = None,
    ) -> None:
        if options is None:
            options = Options()
        self.header_from_url = FITSheader.FITSheaderFromURL(io_config.source)
        super().__init__(io_config, cutout_config, options)

    def _get_header(self, io_config: IOConfig) -> fits.Header:
        """Retrieves the header from the remote fits source

        Parameters
        ----------
        io_config : IOConfig
            The config describing the source and destination parameters (currently unused, needed for overwriting the method)

        Returns
        -------
        fits.Header
            The header for the fits file
        """
        return self.header_from_url.getHeaderDict()

    def _build_cutout(
        self,
        source: str,
    ) -> tuple[np.ndarray, fits.Header]:
        """Generate a cutout of a fits file

        Parameters
        ----------
        source : str
            The url to the remote fits file

        Returns
        -------
        tuple[np.ndarray, fits.Header]
            The data array, header, and slices generated for this cutout

        Raises
        ------
        ValueError
            If The selected FITS HDU does not contain image data or the dimensionality is unsupported
        """
        longitude = self.cutout_config.longitude
        latitude = self.cutout_config.latitude
        radius = self.cutout_config.radius
        spectral_range = self.cutout_config.spectral_range
        source_shape = self.fits_shape

        logger.info(
            f"Starting spatial cutout calculation long_deg={longitude} lat_deg={latitude} radius_deg={radius}"
        )

        if not source_shape:
            raise ValueError("The selected FITS HDU does not contain image data")
        source_ndim = len(source_shape)
        if source_ndim < 2:
            raise ValueError(f"Unsupported image dimensionality: {source_ndim}")

        indices = self.pixel_indices
        indices.update({"zmin": spectral_range[0], "zmax": spectral_range[1]})

        slices = []
        coord_ctypes = (("RA", "GLON"), ("DEC", "DLAT"))
        for ctype in self.axis_types:
            if any(long in ctype for long in coord_ctypes[0]):
                slices.append(slice(indices["xmin"], indices["xmax"] + 1))
            elif any(lat in ctype for lat in coord_ctypes[1]):
                slices.append(slice(indices["ymin"], indices["ymax"] + 1))
            elif "FREQ" in ctype:
                slices.append(
                    slice(
                        indices["zmin"],
                        (indices["zmax"] + 1 if indices["zmax"] is not None else None),
                    )
                )
            elif "STOKES" in ctype:
                slices.append(slice(None))

        slices = tuple(slices[::-1])
        source_shape = self.fits_shape
        shape = []
        for i, s in enumerate(slices):
            if s.start is None:
                shape.append(source_shape[i])
            else:
                shape.append(s.stop - s.start)

        obj = URLObject.UrlObject(source)

        data = obj.getPartitionData(
            indices["xmin"],
            indices["xmax"],
            indices["ymin"],
            indices["ymax"],
            indices["zmin"] if indices["zmin"] else 0,
            indices["zmax"] if indices["zmax"] else self.fits_shape[0] - 1,
            self.header_from_url,
            num_threads=8,
        )

        bitpix_to_dtype = {v: k for k, v in _DTYPE_TO_BITPIX.items()}
        dtype = bitpix_to_dtype[self.source_header.get("BITPIX", -32)]
        data = np.array(data, dtype=dtype)
        data = data.reshape(shape)

        cutout_header = self.build_cutout_header(slices, data.shape, data.dtype)
        return data, cutout_header

    def create_cutout(self, overwrite: bool = False) -> Path:
        """Extract a sky cutout and write it to a FITS file.

        Parameters
        ----------
        overwrite : bool
            Allow overwriting the output file

        Returns
        -------
        Path
            The path to the output file

        Raises
        ------
        FileExistsError
            If the output file already exists and `overwrite` is set to False
        ValueError
            If the requested cutout falls outside of the source cube's extent
        """
        io_c = self.io_config
        co_c = self.cutout_config

        source = io_c.source
        s3_endpoint_url = io_c.s3_endpoint_url

        output_path = Path(io_c.output_path)
        logger.info(
            f"Preparing cutout request source={source!s} output_path={output_path!s} "
            f"long_deg={co_c.longitude} lat_deg={co_c.latitude} radius_deg={co_c.radius} s3_endpoint_url={s3_endpoint_url} "
            f"spectral_start={co_c.spectral_range[0]} spectral_stop={co_c.spectral_range[1]} spectral_units={co_c.spectral_units} overwrite={overwrite}"
        )
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Output file already exists: {output_path}")

        logger.info("Opening FITS source")

        if not self.check_cutout_fit():
            self._get_cube_details()
            raise ValueError(
                "The provided cutout configuration extends past the extents of the selected "
                "cube. Please check the coordinates and try again. Note, the cutout will round "
                "to the outer edge of the pixels."
            )

        if self.dry_run:
            self._get_cube_details()
        else:
            data, header = self._build_cutout(str(source))
            logger.info(
                f"Ensuring output directory exists output_directory={output_path.parent!s}"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Writing cutout to output FITS output_path={output_path!s} output_shape={tuple(data.shape)}"
            )
            fits.PrimaryHDU(data=data, header=header).writeto(
                output_path, overwrite=overwrite
            )
            logger.info(f"Cutout write complete output_path={output_path!s}")
        return output_path
