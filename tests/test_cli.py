from cutouts_service.cli import build_parser
from cutouts_service.fits_utils import is_remote_source


def test_build_parser_parses_cli_arguments() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["13.0", "-42.0", "0.5", "https://example.com/catalog.fits", "--output", "cutout.fits"]
    )

    assert args.ra == 13.0
    assert args.dec == -42.0
    assert args.radius == 0.5
    assert args.file == "https://example.com/catalog.fits"
    assert args.output == "cutout.fits"


def test_is_remote_source_for_url() -> None:
    assert is_remote_source("https://example.com/catalog.fits")


def test_is_remote_source_for_s3_url() -> None:
    assert is_remote_source("s3://bucket/path/file.fits")

def test_is_remote_source_rejects_local_path() -> None:
    assert not is_remote_source("./catalog.fits")


def test_is_remote_source_rejects_invalid_url_shape() -> None:
    assert not is_remote_source("https:///missing-host.fits")
