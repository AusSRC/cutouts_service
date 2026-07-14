from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from astropy.io import fits
import numpy as np
import pytest
from astropy.wcs import WCS


@pytest.fixture
def source_header_2d() -> fits.Header:
    shape = (20, 20)
    data = np.arange(shape[0] * shape[1], dtype=np.float32).reshape(shape)
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [shape[1] / 2 + 0.5, shape[0] / 2 + 0.5]
    wcs.wcs.cdelt = np.array([-0.5, 0.5])
    wcs.wcs.crval = [180.0, -30.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return fits.PrimaryHDU(data=data, header=wcs.to_header()).header


@pytest.fixture
def source_header_3d() -> fits.Header:
    shape = (10, 2, 20, 20)
    header = fits.Header()
    header["NAXIS"] = 4
    header["NAXIS1"] = shape[3]
    header["NAXIS2"] = shape[2]
    header["NAXIS3"] = shape[0]
    header["NAXIS4"] = shape[1]
    header["CRPIX1"] = shape[3] / 2 + 0.5
    header["CRPIX2"] = shape[2] / 2 + 0.5
    header["CRPIX3"] = 1.0
    header["CRPIX4"] = 1.0
    header["CDELT1"] = -0.5
    header["CDELT2"] = 0.5
    header["CRVAL1"] = 180.0
    header["CRVAL2"] = -30.0
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CTYPE3"] = "STOKES"
    header["CTYPE4"] = "FREQ"
    header["BITPIX"] = -32
    return header

@pytest.fixture
def beam_table():
    table_data = np.array([[1.7200001e+01, 1.4300000e+01, 8.1239998e+01, 0, 0],
                  [1.7400000e+01, 1.4700000e+01, 7.6949997e+01, 1, 0],
                  [1.7500000e+01, 1.4600000e+01, 8.4230003e+01, 2, 0],
                  [1.7299999e+01, 1.4600000e+01, 8.1400002e+01, 3, 0],
                  [1.7700001e+01, 1.4500000e+01, 7.7349998e+01, 4, 0],
                  [1.7500000e+01, 1.4700000e+01, 7.9250000e+01, 5, 0],
                  [1.7400000e+01, 1.4900000e+01, 7.8629997e+01, 6, 0],
                  [1.7600000e+01, 1.4800000e+01, 7.9059998e+01, 7, 0],
                  [1.7400000e+01, 1.5000000e+01, 8.0629997e+01, 8, 0],
                  [1.6700001e+01, 1.4000000e+01, 8.6949997e+01, 9, 0]])
    table_names = ('BMAJ', 'BMIN', 'BPA', 'CHAN', 'POL')
    cols = []
    for i, name in enumerate(table_names):
        col = fits.Column(name=name, array=table_data[:, i], format='K')
        cols.append(col)
    return fits.BinTableHDU.from_columns(cols)


@pytest.fixture
def http_file_server(tmp_path: Path):
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

    handler_cls = partial(QuietHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base_url = f"http://{host}:{port}"

    try:
        yield {"base_url": base_url, "root": tmp_path}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def remote_fits_2d(http_file_server, source_header_2d: fits.Header):
    root = http_file_server["root"]
    base_url = http_file_server["base_url"]
    source_file = root / "source.fits"
    source_data = np.arange(20 * 20, dtype=np.float32).reshape((20, 20))
    fits.PrimaryHDU(data=source_data, header=source_header_2d).writeto(source_file)
    return {
        "url": f"{base_url}/{source_file.name}",
        "header": source_header_2d,
    }


@pytest.fixture
def remote_fits_3d(http_file_server, source_header_3d: fits.Header):
    root = http_file_server["root"]
    base_url = http_file_server["base_url"]
    source_file = root / "source_cube.fits"
    source_data = np.arange(10 * 2 * 20 * 20, dtype=np.float32).reshape((10, 2, 20, 20))
    fits.PrimaryHDU(data=source_data, header=source_header_3d).writeto(source_file)
    return {
        "url": f"{base_url}/{source_file.name}",
        "header": source_header_3d,
    }


@pytest.fixture
def remote_fits_3d_objstore(http_file_server, source_header_3d: fits.Header):
    root = http_file_server["root"]
    base_url = http_file_server["base_url"]
    source_file = root / "source_cube_objstore.fits"
    source_data = np.arange(10 * 1 * 20 * 20, dtype=np.float32).reshape((10, 1, 20, 20))
    source_header_3d_objstore = source_header_3d
    source_header_3d_objstore.set("NAXIS4", 1)
    fits.PrimaryHDU(data=source_data, header=source_header_3d).writeto(source_file)
    return {
        "url": f"{base_url}/{source_file.name}",
        "header": source_header_3d_objstore,
    }

@pytest.fixture
def remote_fits_3d_multitable(http_file_server, source_header_3d: fits.Header, beam_table):
    root = http_file_server["root"]
    base_url = http_file_server["base_url"]
    source_header_3d.set("CASAMBM", True)
    source_file = root / "source_cube_multitable.fits"
    source_data = np.arange(10 * 2 * 20 * 20, dtype=np.float32).reshape((10, 2, 20, 20))
    hdulist = [fits.PrimaryHDU(data=source_data, header=source_header_3d), beam_table]
    hdulist = fits.HDUList(hdulist)
    hdulist.writeto(source_file)
    return {
        "url": f"{base_url}/{source_file.name}",
        "header": source_header_3d,
    }