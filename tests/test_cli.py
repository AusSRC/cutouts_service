from pathlib import Path

from astropy.io import fits
from pytest import raises

from cutouts_service.cli import build_parser, main
from cutouts_service.utils import is_remote_source


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

    assert args.ra.degree == 13.0
    assert args.dec.degree == -42.0
    assert args.radius == 0.5
    assert args.file == "https://example.com/catalog.fits"
    assert args.s3_endpoint_url == "https://objects.example.org"
    assert args.log_level == "DEBUG"
    assert args.spectral_min is None
    assert args.spectral_max is None
    assert args.output == "cutout.fits"


def test_build_parser_parses_spectral_pixel_range_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "13.0",
            "-42.0",
            "0.5",
            "https://example.com/catalog.fits",
            "--spectral-min",
            "10",
            "--spectral-max",
            "25",
            "--output",
            "cutout.fits",
        ]
    )

    assert args.spectral_min == 10
    assert args.spectral_max == 25
    assert args.spectral_units == "channels"


def test_is_remote_source_for_url() -> None:
    assert is_remote_source("https://example.com/catalog.fits")


def test_is_remote_source_for_s3_url() -> None:
    assert is_remote_source("s3://bucket/path/file.fits")


def test_is_remote_source_rejects_local_path() -> None:
    assert not is_remote_source("./catalog.fits")


def test_is_remote_source_rejects_invalid_url_shape() -> None:
    assert not is_remote_source("https:///missing-host.fits")


def test_main_converts_radius_from_arcmin_to_degrees(
    tmp_path: Path, remote_fits_2d
) -> None:
    source_url = remote_fits_2d["url"]
    output_file = tmp_path / "cutout.fits"

    main(["180.0", "-30.0", "30.0", source_url, "--output", str(output_file)])

    with fits.open(output_file) as hdul:
        data = hdul[0].data

    assert output_file.exists()
    assert data.shape == (4, 4)


def test_main_requires_both_spectral_pixel_arguments(
    tmp_path: Path, remote_fits_2d
) -> None:
    source_url = remote_fits_2d["url"]
    output_file = tmp_path / "cutout.fits"

    with raises(ValueError, match="Both --spectral-min and --spectral-max"):
        main(
            [
                "180.0",
                "-30.0",
                "30.0",
                source_url,
                "--spectral-min",
                "1",
                "--output",
                str(output_file),
            ]
        )


def test_build_parser_parses_spectral_frequency_units_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "13.0",
            "-42.0",
            "0.5",
            "https://example.com/catalog.fits",
            "--spectral-min",
            "10",
            "--spectral-max",
            "25",
            "--spectral-units",
            "GHz",
            "--output",
            "cutout.fits",
        ]
    )

    assert args.spectral_min == 10
    assert args.spectral_max == 25
    assert args.spectral_units == "GHz"


def test_unrecognised_spectral_units(tmp_path: Path, remote_fits_2d) -> None:
    source_url = remote_fits_2d["url"]
    output_file = tmp_path / "cutout.fits"

    with raises(SystemExit) as e:
        main(
            [
                "13.0",
                "-42.0",
                "0.5",
                source_url,
                "--spectral-min",
                "10",
                "--spectral-max",
                "25",
                "--spectral-units",
                "Gz",
                "--output",
                str(output_file),
            ]
        )
    error_out = next(tb for tb in e.traceback if tb.name == "error").locals["message"]
    if "argument --spectral-units: invalid choice: 'Gz'" not in error_out:
        raise AssertionError


def test_sexagesimal_input() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "00h42m42s",
            "40d51m55s",
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

    assert args.ra.degree == 10.674999999999999
    assert args.dec.degree == 40.86527777777778


def test_main_handles_sexagesimal_input(tmp_path: Path, remote_fits_2d) -> None:
    source_url = remote_fits_2d["url"]
    output_file = tmp_path / "cutout.fits"

    main(["12h0m0s", "-30d00m00s", "30.0", source_url, "--output", str(output_file)])

    with fits.open(output_file) as hdul:
        data = hdul[0].data

    assert output_file.exists()
    assert data.shape == (4, 4)
