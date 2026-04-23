from pathlib import Path

from cutouts_service.cli import main, parse_file_source


def test_parse_file_source_for_url() -> None:
    source_type, source_value = parse_file_source("https://example.com/catalog.fits")

    assert source_type == "url"
    assert source_value == "https://example.com/catalog.fits"


def test_parse_file_source_for_path(tmp_path: Path) -> None:
    test_file = tmp_path / "catalog.fits"
    test_file.write_text("data")

    source_type, source_value = parse_file_source(str(test_file))

    assert source_type == "path"
    assert source_value == str(test_file.resolve())


def test_main_outputs_parsed_arguments(tmp_path: Path, capsys) -> None:
    test_file = tmp_path / "catalog.fits"
    test_file.write_text("data")

    exit_code = main(["13.0", "-42.0", "0.5", str(test_file)])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "ra=13.0" in captured.out
    assert "dec=-42.0" in captured.out
    assert "radius=0.5" in captured.out
    assert "file_type=path" in captured.out
    assert f"file={test_file.resolve()}" in captured.out
