from pathlib import Path

from astropy.io import fits

from cutouts_service.cutouts import AstropyCutout, IOConfig, CutoutConfig
import pytest
import numpy as np
import logging


def test_write_cutout_creates_output_file(tmp_path: Path, remote_fits_2d):
    output_file = tmp_path / "cutout.fits"
    source_url = remote_fits_2d["url"]
    source_header = remote_fits_2d["header"]
    io_config = IOConfig(source_url, output_file)
    cutout_config = CutoutConfig(180.0, -30.0, 1.0)
    AstropyCutout(io_config, cutout_config).create_cutout()

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (6, 6)  # overestimate size (an extra pixel on each side)
    assert header["NAXIS1"] == 6
    assert header["NAXIS2"] == 6
    assert header["CRPIX1"] < source_header["CRPIX1"]
    assert header["CRPIX2"] < source_header["CRPIX2"]


def test_write_cutout_preserves_cube_leading_axis(tmp_path: Path, remote_fits_3d):
    output_file = tmp_path / "cutout_cube.fits"
    source_url = remote_fits_3d["url"]

    io_config = IOConfig(source_url, output_file)
    cutout_config = CutoutConfig(180.0, -30.0, 1.0)
    AstropyCutout(io_config, cutout_config).create_cutout()

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (10, 2, 6, 6)
    assert header["NAXIS1"] == 6
    assert header["NAXIS2"] == 6
    assert header["NAXIS3"] == 2


def test_write_cutout_applies_spectral_axis_pixel_range(tmp_path: Path, remote_fits_3d):
    output_file = tmp_path / "cutout_cube_spectral_slice.fits"
    source_url = remote_fits_3d["url"]

    io_config = IOConfig(source_url, output_file)
    cutout_config = CutoutConfig(180.0, -30.0, 1.0, (1, 1))
    AstropyCutout(io_config, cutout_config).create_cutout()

    with fits.open(output_file) as hdul:
        data = hdul[0].data
        header = hdul[0].header

    assert data.shape == (1, 2, 6, 6)
    assert header["NAXIS1"] == 6
    assert header["NAXIS2"] == 6
    assert header["NAXIS3"] == 2
    assert header["NAXIS4"] == 1


def test_find_image_hdu_uses_header_metadata_without_loading_data():
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
    selected_hdu = AstropyCutout(
        io_config=IOConfig("test", "test"), cutout_config=CutoutConfig(0, 0, 0)
    )._find_image_hdu([FakeNonImageHDU(), image_hdu])

    assert selected_hdu is image_hdu


def test_open_fits_source_opens_remote_http_source(remote_fits_2d) -> None:
    with AstropyCutout(
        io_config=IOConfig(remote_fits_2d["url"], "test"),
        cutout_config=CutoutConfig(0, 0, 0),
    )._open_fits_source() as hdul:
        assert len(hdul) == 1
        assert hdul[0].data is not None


def test_open_fits_source_sets_s3_endpoint_url_in_fsspec_kwargs(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(source, **kwargs):
        captured["source"] = source
        captured["kwargs"] = kwargs
        return DummyContext()

    monkeypatch.setattr("cutouts_service.utils.fits.open", fake_open)

    with AstropyCutout(
        IOConfig("s3://bucket/catalog.fits", "test", "https://objects.example.org"),
        CutoutConfig(1, 1, 1),
    )._open_fits_source():
        pass

    assert captured["source"] == "s3://bucket/catalog.fits"
    assert captured["kwargs"] == {
        "use_fsspec": True,
        "lazy_load_hdus": True,
        "fsspec_kwargs": {
            "anon": True,
            "client_kwargs": {"endpoint_url": "https://objects.example.org"},
        },
    }


def test_open_fits_source_rejects_local_files() -> None:
    with pytest.raises(ValueError, match="remote FITS URL"):
        with AstropyCutout(
            IOConfig("./catalog.fits", "test"), CutoutConfig(1, 1, 1)
        )._open_fits_source():
            pass


def test_build_cutout_header_updates_spatial_axes(
    source_header_2d: fits.Header,
) -> None:
    slices = (slice(2, 6), slice(3, 7))
    cutout = AstropyCutout(
        io_config=IOConfig("test", "test"), cutout_config=CutoutConfig(0, 0, 0)
    )
    cutout.source_header = source_header_2d
    cutout_header = cutout.build_cutout_header(slices, (4, 4), np.dtype("float32"))

    assert cutout_header["NAXIS1"] == 4
    assert cutout_header["NAXIS2"] == 4
    assert cutout_header["CRPIX1"] == source_header_2d["CRPIX1"] - 3
    assert cutout_header["CRPIX2"] == source_header_2d["CRPIX2"] - 2
    assert cutout_header["BITPIX"] == -32


def test_build_cutout_header_preserves_cube_depth() -> None:
    source_header = fits.Header()
    source_header["NAXIS"] = 3
    source_header["NAXIS1"] = 10
    source_header["NAXIS2"] = 10
    source_header["NAXIS3"] = 3
    source_header["CRPIX1"] = 5.5
    source_header["CRPIX2"] = 5.5
    source_header["CRPIX3"] = 2.0

    cutout = AstropyCutout(
        io_config=IOConfig("test", "test"), cutout_config=CutoutConfig(0, 0, 0)
    )
    cutout.source_header = source_header

    cutout_header = cutout.build_cutout_header(
        (slice(None), slice(2, 6), slice(3, 7)), (3, 4, 4), np.dtype("float32")
    )

    assert cutout_header["NAXIS1"] == 4
    assert cutout_header["NAXIS2"] == 4
    assert cutout_header["NAXIS3"] == 3
    assert cutout_header["CRPIX1"] == source_header["CRPIX1"] - 3
    assert cutout_header["CRPIX2"] == source_header["CRPIX2"] - 2


def test_get_cube_details(remote_fits_3d, caplog) -> None:
    with caplog.at_level(logging.INFO):
        source_url = remote_fits_3d["url"]
        cutout = AstropyCutout(
            io_config=IOConfig(source_url, "test"),
            cutout_config=CutoutConfig(180, -30, 1, (1, 1)),
        )
        cutout.source_header = remote_fits_3d["header"]
        cutout._get_cube_details()
    captured = caplog.records
    for record in captured[5:8]:
        assert len(record.msg) > 0
