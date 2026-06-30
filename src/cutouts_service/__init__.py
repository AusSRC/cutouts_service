"""Basic package for cutouts-service."""

from cutouts_service.objstore import (
    FITSheader,
    get_access_keys,
    ObjStore,
    S3Object,
    URLObject,
)

__all__ = ["FITSheader", "get_access_keys", "ObjStore", "S3Object", "URLObject"]
