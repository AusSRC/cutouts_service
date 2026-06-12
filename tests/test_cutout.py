from pathlib import Path

from astropy.io import fits

from cutouts_service.cutout import _find_image_hdu
from cutouts_service.cutout import write_cutout


def test_write_cutout_creates_output_file(tmp_path: Path, remote_fits_2d) -> None:
    output_file = tmp_path / "cutout.fits"
    source_url = remote_fits_2d["url"]
    source_header = remote_fits_2d["header"]

    write_cutout(
        source=source_url,
        output_path=output_file,
        ra=180.0,
        dec=-30.0,
        radius=1.0,
    )

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (6, 6) # overestimate size (an extra pixel on each side)
    assert header["NAXIS1"] == 6
    assert header["NAXIS2"] == 6
    assert header["CRPIX1"] < source_header["CRPIX1"]
    assert header["CRPIX2"] < source_header["CRPIX2"]


def test_write_cutout_preserves_cube_leading_axis(tmp_path: Path, remote_fits_3d) -> None:
    output_file = tmp_path / "cutout_cube.fits"
    source_url = remote_fits_3d["url"]

    write_cutout(
        source=source_url,
        output_path=output_file,
        ra=180.0,
        dec=-30.0,
        radius=1.0,
    )

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (10, 2, 6, 6)
    assert header["NAXIS1"] == 6
    assert header["NAXIS2"] == 6
    assert header["NAXIS3"] == 2


def test_write_cutout_applies_spectral_axis_pixel_range(tmp_path: Path, remote_fits_3d) -> None:
    output_file = tmp_path / "cutout_cube_spectral_slice.fits"
    source_url = remote_fits_3d["url"]

    write_cutout(
        source=source_url,
        output_path=output_file,
        ra=180.0,
        dec=-30.0,
        radius=1.0,
        spectral_start_pixel=1,
        spectral_stop_pixel=1,
    )

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (1, 2, 6, 6)
    assert header["NAXIS1"] == 6
    assert header["NAXIS2"] == 6
    assert header["NAXIS3"] == 2
    assert header["NAXIS4"] == 1


def test_find_image_hdu_uses_header_metadata_without_loading_data() -> None:
    class FakeNonImageHDU:
        is_image = False
        name = "TABLE"

    class FakeImageHDU:
        is_image = True
        name = "SCI"

        def __init__(self) -> None:
            self.header = fits.Header()
            self.header["NAXIS"] = 2
            self.header["NAXIS1"] = 10
            self.header["NAXIS2"] = 10

        @property
        def data(self):
            raise AssertionError("_find_image_hdu must not access .data")

    image_hdu = FakeImageHDU()
    selected_hdu = _find_image_hdu([FakeNonImageHDU(), image_hdu])

    assert selected_hdu is image_hdu