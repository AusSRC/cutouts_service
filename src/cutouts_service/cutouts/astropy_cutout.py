"""Cutout generation helpers."""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


import numpy as np
from astropy.io import fits


from contextlib import contextmanager

from cutouts_service.utils import is_remote_source

from cutouts_service.cutouts import (
    ImageLikeHDU,
    IOConfig,
    CutoutConfig,
    Options,
    Cutout,
)

logger = logging.getLogger(__name__)


class AstropyCutout(Cutout):
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
    source_header: fits.Header
        The header of the source file
    """

    def __init__(
        self,
        io_config: IOConfig,
        cutout_config: CutoutConfig,
        options: Options = Options(),
    ) -> None:
        super().__init__(io_config, cutout_config, options)
        self.source_header: fits.Header

    def _find_image_hdu(self, hdul: fits.HDUList) -> ImageLikeHDU:
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

            self._set_header_shape(header)
            source_shape = self.fits_shape
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

    def _build_cutout(
        self, image_hdu: ImageLikeHDU
    ) -> tuple[np.ndarray, fits.Header, tuple[slice]]:
        """Generate a cutout of a fits file

        Parameters
        ----------
        image_hdu : ImageLikeHDU
            The HDU containing the image

        Returns
        -------
        tuple[np.ndarray, fits.Header, tuple[slice]]
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
        header = self.source_header
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
        logger.info("pixel slice calculated: %s", slices)
        logger.info("performing slice")

        data = image_hdu.section[slices]

        header = self.build_cutout_header(slices, data.shape, data.dtype)
        return data, header, slices

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
        with self._open_fits_source() as hdul:
            logger.info(f"Opened FITS source hdu_count={len(hdul)}")

            # set unset attributes
            image_hdu = self._find_image_hdu(hdul)
            self.source_header = image_hdu.header

            self._compute_pixel_indices()
            if not self.check_cutout_fit():
                logger.warning(
                    "The provided cutout configuration extends past the extents of the selected cube. The cutout extents will be clipped appropriately."
                )

            if self.dry_run:
                self._get_cube_details(image_hdu)
            else:
                data, header, _ = self._build_cutout(image_hdu)
        if not self.dry_run:
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

    @contextmanager
    def _open_fits_source(self):
        """Open the fits source, closing when done

        Yields
        ------
        HDUList
            The list of HDUs containing the image data

        Raises
        ------
        ValueError
            The input file is not a remote file
        """
        io_c = self.io_config
        logger.info(f"Opening FITS source source={str(io_c.source)}")
        if not is_remote_source(io_c.source):
            logger.error(f"Rejected non-remote FITS source source={str(io_c.source)}")
            raise ValueError("A remote FITS URL is required")

        open_args = (io_c.source,)
        open_kwargs: dict[str, Any] = {"use_fsspec": True, "lazy_load_hdus": True}
        parsed_source = urlparse(str(io_c.source))
        if parsed_source.scheme == "s3":
            fsspec_kwargs: dict[str, object] = {"anon": True}
            if io_c.s3_endpoint_url:
                fsspec_kwargs["client_kwargs"] = {"endpoint_url": io_c.s3_endpoint_url}
            open_kwargs["fsspec_kwargs"] = fsspec_kwargs

        logger.info(
            f"Calling astropy.io.fits.open source={str(io_c.source)} open_kwargs={open_kwargs}"
        )

        with fits.open(*open_args, **open_kwargs) as handle:
            try:
                hdu_count = len(handle)
            except TypeError:
                hdu_count = None

            logger.info(
                f"FITS source opened source={str(io_c.source)} hdu_count={hdu_count}"
            )
            yield handle
