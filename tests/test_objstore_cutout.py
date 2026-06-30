"""Tests for the ObjectStore Backend for cutouts_service"""

import math
from pathlib import Path

import pytest
from astropy.io import fits

from cutouts_service.cutouts import CutoutConfig, IOConfig, ObjStoreCutout


def test_objstore_create_cutout(remote_fits_3d_objstore, tmp_path):
    output_file = tmp_path / "cutout.fits"
    source_url = remote_fits_3d_objstore["url"]
    source_header = remote_fits_3d_objstore["header"]
    io_config = IOConfig(source_url, output_file)
    cutout_config = CutoutConfig(180, -30, 1, (8, 9))
    ObjStoreCutout(io_config, cutout_config).create_cutout()

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (2, 1, 6, 6)
    assert not math.isnan(data.sum())
    assert header["NAXIS1"] == 6
    assert header["NAXIS2"] == 6
    assert header["NAXIS3"] == 1
    assert header["NAXIS4"] == 2
    assert header["CRPIX1"] < source_header["CRPIX1"]
    assert header["CRPIX2"] < source_header["CRPIX2"]


def test_fail_on_out_of_bounds(tmp_path: Path, remote_fits_3d):
    output_file = tmp_path / "cutout_cube.fits"
    source_url = remote_fits_3d["url"]

    io_config = IOConfig(source_url, output_file)
    cutout_config = CutoutConfig(180.0, -30.0, 2.0, (-5, 100))
    error_text = "The provided cutout configuration extends past the extents of the selected cube"
    with pytest.raises(ValueError, match=error_text):
        ObjStoreCutout(io_config, cutout_config).create_cutout()
