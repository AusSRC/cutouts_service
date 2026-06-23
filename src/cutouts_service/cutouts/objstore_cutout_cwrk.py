"""Cutout generation helpers."""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from __future__ import annotations

# import argparse
# import sys
# import time
# from pathlib import Path

from astropy.io import fits

from cutouts_service import FITSheader
from cutouts_service import URLObject
# from FITSheader import FITSheaderFromURL
# from URLObject import UrlObject

import numpy as np
from astropy.io import fits

#ObjStore Imports


# from get_access_keys import *
# from S3Object import S3Object
# from URLObject import UrlObject
# from FITSheader import FITSheaderFromURL
# from FITSheader import FITSheaderFromS3

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


class ObjStoreCutout(Cutout):
    """A cutout class encapsulating the cutout from a remote source using astropy"""

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
    
    # def _get_axis_ranges(self,
    #     length: int, scale_factor: float, position: str
    # ) -> tuple[int, int, int]:
    #     """Return 0-based start index, exclusive end index, and size for one axis."""
    #     size = max(1, int(round(scale_factor * length)))

    #     if position == "start":
    #         start = 0
    #     elif position == "end":
    #         start = length - size
    #     else:  # middle
    #         start = (length - size) // 2

    #     end = start + size
    #     return start, end, size
    
    def _build_source_header(hdr: FITSheader.FITSheaderFromURL) -> fits.Header:
        """Parse an astropy FITS Header from a FITSheaderFromURL object."""
        return fits.Header.fromstring(hdr.rawHdrData().decode("latin-1"), sep="")
    
    def _make_cutout_header(self,
        source_header: fits.Header,
        x_start: int,
        y_start: int,
        z_start: int,
        x_size: int,
        y_size: int,
        z_size: int,
        naxis: int,
    ) -> fits.Header:
        """Return an updated FITS header for the ObjStore cutout region.

        Adjusts NAXISi sizes and CRPIXi reference-pixel offsets.  ObjStore always
        returns big-endian float32 data, so BITPIX is forced to -32 and any
        BSCALE/BZERO scaling cards are removed.
        """
        header = source_header.copy()
        header["BITPIX"] = -32
        header.pop("BSCALE", None)
        header.pop("BZERO", None)

        header["NAXIS1"] = x_size
        header["NAXIS2"] = y_size
        if "CRPIX1" in source_header:
            header["CRPIX1"] = float(source_header["CRPIX1"]) - x_start
        if "CRPIX2" in source_header:
            header["CRPIX2"] = float(source_header["CRPIX2"]) - y_start

        if naxis == 3 and "NAXIS3" in header:
            header["NAXIS3"] = z_size
            if "CRPIX3" in source_header:
                header["CRPIX3"] = float(source_header["CRPIX3"]) - z_start
        elif naxis == 4 and "NAXIS4" in header:
            header["NAXIS4"] = z_size
            if "CRPIX4" in source_header:
                header["CRPIX4"] = float(source_header["CRPIX4"]) - z_start

        return header
    
    def write_cutout_to_file(self,
        obj: URLObject.UrlObject,
        hdr: FITSheader.FITSheaderFromURL,
        cutout_header: fits.Header,
        x_start: int,
        x_end: int,
        y_start: int,
        y_end: int,
        z_start: int,
        x_size: int,
        y_size: int,
        z_size: int,
        xsize: int,
        ysize: int,
        output_path: Path,
        overwrite: bool = False,
    ) -> int:
        """Stream the ObjStore cutout to a FITS file one spatial plane at a time.

        Manually primes the UrlObject properties required by getWholeChannel so
        that only one plane is held in memory at a time — analogous to the
        hdu.section streaming in test_astropy.py.

        Returns the number of data bytes written.
        """
        if output_path.exists() and not overwrite:
            raise FileExistsError(
                f"Output file already exists: {output_path}  "
                "(pass --overwrite to replace it)"
            )

        # Prime the UrlObject internals needed by getWholeChannel.
        obj.hdrsize = hdr.len()
        obj.xsize = xsize
        obj.ysize = ysize
        obj.chsize = xsize * ysize
        obj.xlen = x_size
        obj.ylen = y_size
        obj.zlen = z_size

        output_path.parent.mkdir(parents=True, exist_ok=True)
        total_bytes = 0

        with fits.StreamingHDU(str(output_path), cutout_header) as shdu:
            for ch in range(z_size):
                plane_data = obj.getWholeChannel(
                    x_start, x_end - 1, y_start, y_end - 1, z_start, 0, ch
                )
                plane = plane_data.reshape(y_size, x_size)
                shdu.write(plane)
                total_bytes += plane.nbytes
                if z_size > 1:
                    print(f"  Written channel {ch + 1}/{z_size}", flush=True)

        return total_bytes


    # def run_objstore_cutout(self,
    #     url: str,
    #     percentage: float,
    #     output_path: Path,
    #     position: str = "start",
    #     include_frequency: bool = False,
    #     num_threads: int = 1,
    #     overwrite: bool = False,
    # ) -> int:
    #     """Fetch a FITS cutout from remote storage via presigned URL using ObjStore."""
    #     position = position.lower()
    #     if position not in {"start", "middle", "end"}:
    #         raise ValueError(
    #             f"Position must be one of 'start', 'middle', or 'end', got '{position}'"
    #         )

    #     if not 0 < percentage <= 100:
    #         raise ValueError(f"Percentage must be between 0 and 100, got {percentage}")

    #     print(f"Opening FITS URL: {url}")
    #     overall_start = time.time()

    #     # Fetch FITS header from the remote URL
    #     header_fetch_start = time.time()
    #     hdr = FITSheaderFromURL(url)
    #     header_dict = hdr.getHeaderDict()
    #     header_fetch_elapsed = time.time() - header_fetch_start

    #     xsize = int(header_dict.get("NAXIS1", 0))
    #     ysize = int(header_dict.get("NAXIS2", 0))
    #     naxis = int(header_dict.get("NAXIS", 0))
    #     zsize = 1

    #     if naxis == 3:
    #         zsize = int(header_dict.get("NAXIS3", 0))
    #     elif naxis == 4:
    #         zsize = int(header_dict.get("NAXIS4", 0))

    #     if xsize == 0 or ysize == 0:
    #         raise ValueError(
    #             f"Could not read NAXIS1 ({xsize}) or NAXIS2 ({ysize}) from FITS header"
    #         )

    #     print(f"FITS dimensions: {xsize} x {ysize} pixels", end="")
    #     if zsize > 1:
    #         print(f" x {zsize} channels", end="")
    #     print()

    #     # Calculate cutout dimensions
    #     num_axes = 2
    #     if include_frequency and zsize > 1:
    #         num_axes = 3
    #     scale_factor = (percentage / 100.0) ** (1.0 / num_axes)

    #     # Calculate spatial ranges (0-based for ObjStore)
    #     x_start, x_end, x_size = self._get_axis_ranges(xsize, scale_factor, position)
    #     y_start, y_end, y_size = self._get_axis_ranges(ysize, scale_factor, position)

    #     # Calculate spectral range if applicable
    #     z_start, z_end, z_size = 0, zsize, zsize
    #     if include_frequency and zsize > 1:
    #         z_start, z_end, z_size = self._get_axis_ranges(zsize, scale_factor, position)

    #     print(f"Cutout percentage: {percentage}% of total {'volume' if zsize > 1 else 'area'}")
    #     print(f"Scale factor per cut axis: {scale_factor:.6f}")
    #     print(f"Position: {position}")
    #     print(f"Include frequency axis: {'yes' if include_frequency else 'no'}")

    #     if zsize > 1:
    #         print(f"Spectral range: {z_start}:{z_end} ({z_size} channels)")

    #     print(
    #         f"Spatial ranges: "
    #         f"Y={y_start}:{y_end} ({y_size} pixels), "
    #         f"X={x_start}:{x_end} ({x_size} pixels)"
    #     )

    #     if x_size == 0 or y_size == 0 or z_size == 0:
    #         raise RuntimeError("Cutout produced an empty result.")

    #     # Build the cutout FITS header
    #     source_header = self._build_source_header(hdr)
    #     cutout_header = self._make_cutout_header(
    #         source_header, x_start, y_start, z_start, x_size, y_size, z_size, naxis
    #     )

    #     # Stream the cutout to disk one channel at a time
    #     print(f"Writing cutout to: {output_path}")
    #     obj = UrlObject(url)
    #     data_fetch_start = time.time()
    #     data_bytes = self.write_cutout_to_file(
    #         obj, hdr, cutout_header,
    #         x_start, x_end, y_start, y_end, z_start,
    #         x_size, y_size, z_size,
    #         xsize, ysize,
    #         output_path, overwrite,
    #     )
    #     data_fetch_elapsed = time.time() - data_fetch_start

    #     elapsed_time = time.time() - overall_start
    #     size_mb = data_bytes / (1024 * 1024)
    #     file_size_mb = output_path.stat().st_size / (1024 * 1024)
    #     throughput = size_mb / data_fetch_elapsed if data_fetch_elapsed > 0 else float("inf")

    #     print("Cutout written successfully!")
    #     print(f"Header fetch time: {header_fetch_elapsed:.3f} seconds")
    #     print(f"Data fetch time: {data_fetch_elapsed:.3f} seconds ({data_fetch_elapsed / 60:.3f} minutes)")
    #     print(f"Total elapsed time: {elapsed_time:.3f} seconds ({elapsed_time / 60:.3f} minutes)")
    #     print(f"Output file: {output_path}")
    #     print(f"Output file size (with FITS overhead): {file_size_mb:.3f} MB")
    #     print(f"Data bytes written: {size_mb:.3f} MB")
    #     print(f"Throughput: {throughput:.3f} MB/s")

    #     return 0
    

    def _build_spatial_cutout(
        self, image_hdu: ImageLikeHDU, source: str, thread_count: int = 6
    ) -> tuple[np.ndarray, fits.Header, list[slice]]:
        """Generate a cutout of a fits file

        Parameters
        ----------
        image_hdu : ImageLikeHDU
            The HDU containing the image

        Returns
        -------
        tuple[np.ndarray, fits.Header, list[slice]]
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
        indices.update({"zmin": channel_range[0], "zmax": channel_range[1]})

        
        # NUM_THREADS = thread_count #Needs to be an argument
        header = FITSheader.FITSheaderFromURL(source)        
        header_dict = header.getHeaderDict()

        xsize = int(header_dict.get("NAXIS1", 0))
        ysize = int(header_dict.get("NAXIS2", 0))
        naxis = int(header_dict.get("NAXIS", 0))
        zsize = 1

        if naxis == 3:
            zsize = int(header_dict.get("NAXIS3", 0))
        elif naxis == 4:
            zsize = int(header_dict.get("NAXIS4", 0))

        if xsize == 0 or ysize == 0:
            raise ValueError(
                f"Could not read NAXIS1 ({xsize}) or NAXIS2 ({ysize}) from FITS header"
            )

        print(f"FITS dimensions: {xsize} x {ysize} pixels", end="")
        if zsize > 1:
            print(f" x {zsize} channels", end="")

        # Build the cutout FITS header
        source_header = self._build_source_header(header)
        x_size = indices['xmax'] - indices['xmin']
        y_size = indices['ymax'] - indices['ymin']
        z_size = indices['zmax'] - indices['zmin']
        cutout_header = self._make_cutout_header(
            source_header, indices['xmin'],indices['ymin'],indices['zmin'], x_size, y_size, z_size, naxis
        )



        obj = URLObject.UrlObject(source)
        overwrite = False
        io_c = self.io_config

        output_path = Path(io_c.output_path)

        data = self.write_cutout_to_file(
            obj, header, cutout_header,
            indices['xmin'], indices['xmax'], indices['ymin'], indices['ymax'], indices['zmin'],
            x_size, y_size, z_size,
            xsize, ysize,
            output_path, overwrite,
        )

        # obj.setDebugFlag()

        # data = obj.getPartitionData(indices['xmin'],indices['xmax'],indices['ymin'],indices['ymax'],indices['zmin'],indices['zmax'],header,NUM_THREADS)

        # slices = []
        # for ctype in self.axis_types:
        #     if "RA" in ctype:
        #         slices.append(slice(indices["xmin"], indices["xmax"] + 1))
        #     elif "DEC" in ctype:
        #         slices.append(slice(indices["ymin"], indices["ymax"] + 1))
        #     elif "FREQ" in ctype:
        #         slices.append(
        #             slice(
        #                 channel_range[0],
        #                 (
        #                     channel_range[1]
        #                     if channel_range[1] is None
        #                     else channel_range[1] + 1
        #                 ),
        #             )
        #         )
        #     elif "STOKES" in ctype:
        #         slices.append(slice(None))

        # slices = tuple(slices[::-1])
        # logger.info("pixel slice calculated: %s", slices)
        # logger.info("performing slice")

        # data = image_hdu.section[slices]

        # header = self.build_cutout_header(slices, data.shape, data.dtype)
        return data, header, #slices

    def create_cutout(self, overwrite: bool = False) -> Path:
        """Extract a sky cutout and write it to a FITS file.

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

            if self.dry_run:
                self._get_cube_details(image_hdu)
            else:
                data, header = self._build_spatial_cutout(image_hdu,s3_endpoint_url)
        if not self.dry_run:
            logger.info(
                f"Ensuring output directory exists output_directory={str(output_path.parent)}"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(
                f"Writing cutout to output FITS output_path={str(output_path)} output_shape={tuple(data.shape)}"
            )
            # fits.PrimaryHDU(data=data, header=header).writeto(
            #     output_path, overwrite=overwrite
            # )
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
