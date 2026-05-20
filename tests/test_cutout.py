from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from cutouts_service.cutout import write_cutout


def _make_source_header(*, shape: tuple[int, int] = (20, 20)) -> fits.Header:
    data = np.arange(shape[0] * shape[1], dtype=np.float32).reshape(shape)
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [shape[1] / 2 + 0.5, shape[0] / 2 + 0.5]
    wcs.wcs.cdelt = np.array([-0.5, 0.5])
    wcs.wcs.crval = [180.0, -30.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return fits.PrimaryHDU(data=data, header=wcs.to_header()).header


def _make_cube_header(*, shape: tuple[int, int, int] = (2, 20, 20)) -> fits.Header:
    data = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    header = fits.Header()
    header["NAXIS"] = 3
    header["NAXIS1"] = shape[2]
    header["NAXIS2"] = shape[1]
    header["NAXIS3"] = shape[0]
    header["CRPIX1"] = shape[2] / 2 + 0.5
    header["CRPIX2"] = shape[1] / 2 + 0.5
    header["CRPIX3"] = 1.0
    header["CDELT1"] = -0.5
    header["CDELT2"] = 0.5
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["BITPIX"] = -32
    return fits.PrimaryHDU(data=data, header=header).header


def test_write_cutout_creates_output_file(tmp_path: Path, monkeypatch) -> None:
    source_file = tmp_path / "source.fits"
    output_file = tmp_path / "cutout.fits"
    source_header = _make_source_header()
    source_data = np.arange(20 * 20, dtype=np.float32).reshape((20, 20))
    fits.PrimaryHDU(data=source_data, header=source_header).writeto(source_file)

    monkeypatch.setattr(
        "cutouts_service.cutout.open_fits_source",
        lambda source: fits.open(source_file),
    )

    write_cutout(
        source="https://example.com/source.fits",
        output_path=output_file,
        ra=180.0,
        dec=-30.0,
        radius=1.0,
    )

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (4, 4)
    assert header["NAXIS1"] == 4
    assert header["NAXIS2"] == 4
    assert header["CRPIX1"] < source_header["CRPIX1"]
    assert header["CRPIX2"] < source_header["CRPIX2"]


def test_write_cutout_preserves_cube_leading_axis(tmp_path: Path, monkeypatch) -> None:
    source_file = tmp_path / "source_cube.fits"
    output_file = tmp_path / "cutout_cube.fits"
    source_header = _make_cube_header()
    source_data = np.arange(2 * 20 * 20, dtype=np.float32).reshape((2, 20, 20))
    fits.PrimaryHDU(data=source_data, header=source_header).writeto(source_file)

    monkeypatch.setattr(
        "cutouts_service.cutout.open_fits_source",
        lambda source: fits.open(source_file),
    )

    write_cutout(
        source="https://example.com/source_cube.fits",
        output_path=output_file,
        ra=180.0,
        dec=-30.0,
        radius=1.0,
    )

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (2, 4, 4)
    assert header["NAXIS1"] == 4
    assert header["NAXIS2"] == 4
    assert header["NAXIS3"] == 2