from cutouts_service.utils import is_remote_source
import logging

logger = logging.getLogger(__name__)
logger.propagate = True


def test_is_remote_source_for_object_storage_scheme() -> None:
    assert is_remote_source("s3://bucket/path/file.fits")
