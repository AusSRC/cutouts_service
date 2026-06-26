# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added
- Initial cutouts service scaffold and CLI.
- Query mode to check extents of remote fits file.
- Usage documentations
- Added Cutout abstract base class in preparation for Objstore implementation

### Changed
- Changed current implementation to inherit from base Cutout class as an AstropyCutout class
- Rearanged file structure to match heirarchy
- Updated tests to match
- Added switch to change backend to use either Astropy or ObjStore