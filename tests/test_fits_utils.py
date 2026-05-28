import numpy as np
import pytest
from astropy.io import fits

from cutouts_service.fits_utils import build_cutout_header, open_fits_source
from cutouts_service.fits_utils import is_remote_source


def test_open_fits_source_opens_remote_http_source(remote_fits_2d) -> None:
    with open_fits_source(remote_fits_2d["url"]) as hdul:
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

    monkeypatch.setattr("cutouts_service.fits_utils.fits.open", fake_open)

    with open_fits_source(
        "s3://bucket/catalog.fits",
        s3_endpoint_url="https://objects.example.org",
    ):
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
        with open_fits_source("./catalog.fits"):
            pass


def test_build_cutout_header_updates_spatial_axes(source_header_2d: fits.Header) -> None:
    slices = (slice(2, 6), slice(3, 7))

    cutout_header = build_cutout_header(
        source_header_2d,
        slices,
        (4, 4),
        np.dtype("float32"),
    )

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

    cutout_header = build_cutout_header(
        source_header,
        (slice(None), slice(2, 6), slice(3, 7)),
        (3, 4, 4),
        np.dtype("float32"),
    )

    assert cutout_header["NAXIS1"] == 4
    assert cutout_header["NAXIS2"] == 4
    assert cutout_header["NAXIS3"] == 3
    assert cutout_header["CRPIX1"] == source_header["CRPIX1"] - 3
    assert cutout_header["CRPIX2"] == source_header["CRPIX2"] - 2


def test_is_remote_source_for_object_storage_scheme() -> None:
    assert is_remote_source("s3://bucket/path/file.fits")