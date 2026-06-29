"""Cutout generation helpers."""

import logging
from pathlib import Path

from astropy.io import fits

from cutouts_service import FITSheader
from cutouts_service import URLObject

import numpy as np



from cutouts_service.cutouts import (
    IOConfig,
    CutoutConfig,
    Options,
    Cutout,
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
    source_header : fits.Header
        The header of the source file
    """

    def __init__(
        self,
        io_config: IOConfig,
        cutout_config: CutoutConfig,
        options: Options = Options(),
    ) -> None:
        super().__init__(io_config, cutout_config, options)
        self.header_from_url: FITSheader.FITSheaderFromURL
        self.source_header: fits.Header

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
        ra = self.cutout_config.ra
        dec = self.cutout_config.dec
        radius = self.cutout_config.radius
        channel_range = self.cutout_config.channel_range
        source_shape = self.fits_shape

        logger.info(
            f"Starting spatial cutout calculation ra_deg={ra} dec_deg={dec} radius_deg={radius}"
        )

        if not source_shape:
            raise ValueError("The selected FITS HDU does not contain image data")
        source_ndim = len(source_shape)
        if source_ndim < 2:
            raise ValueError(f"Unsupported image dimensionality: {source_ndim}")

        indices = self.pixel_indices
        indices.update({"zmin": channel_range[0], "zmax": channel_range[1]})

        slices = []
        for ctype in self.axis_types:
            if "RA" in ctype:
                slices.append(slice(indices["xmin"], indices["xmax"] + 1))
            elif "DEC" in ctype:
                slices.append(slice(indices["ymin"], indices["ymax"] + 1))
            elif "FREQ" in ctype:
                slices.append(
                    slice(
                        channel_range[0],
                        (
                            channel_range[1]
                            if channel_range[1] is None
                            else channel_range[1] + 1
                        ),
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
            num_threads=1,
        )

        bitpix_to_dtype = {v: k for k, v in _DTYPE_TO_BITPIX.items()}
        dtype = bitpix_to_dtype[self.source_header.get("BITPIX", -32)]
        data = np.array(data, dtype=dtype)
        data = data.reshape(shape)

        cutout_header = self.build_cutout_header(slices, shape, dtype)
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
        """
        io_c = self.io_config
        co_c = self.cutout_config

        source = io_c.source
        s3_endpoint_url = io_c.s3_endpoint_url

        output_path = Path(io_c.output_path)
        logger.info(
            f"Preparing cutout request source={str(source)} output_path={str(output_path)} "
            f"ra_deg={co_c.ra} dec_deg={co_c.dec} radius_deg={co_c.radius} s3_endpoint_url={s3_endpoint_url} "
            f"spectral_start_pixel={co_c.channel_range[0]} spectral_stop_pixel={co_c.channel_range[1]} overwrite={overwrite}"
        )
        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Output file already exists: {output_path}")

        logger.info("Opening FITS source")

        self.header_from_url = FITSheader.FITSheaderFromURL(source)
        self.source_header = self.header_from_url.getHeaderDict()
        self._set_header_shape(self.source_header)
        self._compute_pixel_indices()

        if not self.check_cutout_fit():
            raise ValueError(
                "The provided cutout configuration extends past the extents of the selected cube. Please use the astropy backend to clip the extents of the cutout to that of the cube."
            )

        if self.dry_run:
            self._get_cube_details()
        else:
            data, header = self._build_cutout(str(source))
            logger.info(
                f"Ensuring output directory exists output_directory={str(output_path.parent)}"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Writing cutout to output FITS output_path={str(output_path)} output_shape={tuple(data.shape)}"
            )
            fits.PrimaryHDU(data=data, header=header).writeto(
                output_path, overwrite=overwrite
            )
            logger.info(f"Cutout write complete output_path={str(output_path)}")
        return output_path
