"""Basic package for cutouts-service."""

from cutouts_service.objstore import (
    FITSheader,
    ObjStore,
    S3Object,
    URLObject,
    get_access_keys,
)

__all__ = ["FITSheader", "ObjStore", "S3Object", "URLObject", "get_access_keys"]
