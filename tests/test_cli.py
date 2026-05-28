from pathlib import Path

from astropy.io import fits
from pytest import raises

from cutouts_service.cli import build_parser
from cutouts_service.cli import main
from cutouts_service.fits_utils import is_remote_source


def test_build_parser_parses_cli_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "13.0",
            "-42.0",
            "0.5",
            "https://example.com/catalog.fits",
            "--s3-endpoint-url",
            "https://objects.example.org",
            "--log-level",
            "DEBUG",
            "--output",
            "cutout.fits",
        ]
    )

    assert args.ra == 13.0
    assert args.dec == -42.0
    assert args.radius == 0.5
    assert args.file == "https://example.com/catalog.fits"
    assert args.s3_endpoint_url == "https://objects.example.org"
    assert args.log_level == "DEBUG"
    assert args.spectral_start_pixel is None
    assert args.spectral_stop_pixel is None
    assert args.output == "cutout.fits"


def test_build_parser_parses_spectral_pixel_range_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "13.0",
            "-42.0",
            "0.5",
            "https://example.com/catalog.fits",
            "--spectral-start-pixel",
            "10",
            "--spectral-stop-pixel",
            "25",
            "--output",
            "cutout.fits",
        ]
    )

    assert args.spectral_start_pixel == 10
    assert args.spectral_stop_pixel == 25


def test_is_remote_source_for_url() -> None:
    assert is_remote_source("https://example.com/catalog.fits")


def test_is_remote_source_for_s3_url() -> None:
    assert is_remote_source("s3://bucket/path/file.fits")

def test_is_remote_source_rejects_local_path() -> None:
    assert not is_remote_source("./catalog.fits")


def test_is_remote_source_rejects_invalid_url_shape() -> None:
    assert not is_remote_source("https:///missing-host.fits")


def test_main_converts_radius_from_arcmin_to_degrees(tmp_path: Path, remote_fits_2d) -> None:
    source_url = remote_fits_2d["url"]
    output_file = tmp_path / "cutout.fits"

    exit_code = main(
        [
            "180.0",
            "-30.0",
            "30.0",
            source_url,
            "--output",
            str(output_file),
        ]
    )

    with fits.open(output_file) as hdul:
        data = hdul[0].data

    assert exit_code == 0
    assert output_file.exists()
    assert data.shape == (2, 2)


def test_main_requires_both_spectral_pixel_arguments(tmp_path: Path, remote_fits_2d) -> None:
    source_url = remote_fits_2d["url"]
    output_file = tmp_path / "cutout.fits"

    with raises(ValueError, match="Both --spectral-start-pixel and --spectral-stop-pixel"):
        main(
            [
                "180.0",
                "-30.0",
                "30.0",
                source_url,
                "--spectral-start-pixel",
                "1",
                "--output",
                str(output_file),
            ]
        )
