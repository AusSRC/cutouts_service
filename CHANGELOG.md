# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased - 2026-09-04

## Changed
- Changed the longitude and latitude parsing to use astropy's Angle parsing, ensuring that and reasonable input (decimal or sexagesimal) should parse to the right coordinate.

## [1.0.4] - 2026-07-30

### Added
- Added a frequency unit input option
- Added frequency parsing to take any of "channels", "Hz", "kHz", or "GHz"

### Fixed
- changed the dry-run tests to ensure outputs match the expected output exactly

## [1.0.3] - 2026-07-30

### Changed
- Set cutout objects to initialise header information at creation rather than during the cutout.

## [1.0.2] - 2026-07-24

### Changed
- updated ruff dependency to 0.16.0

### Fixed
- FITS files with multiple HDUs will now copy down secondary HDUs along with the cutout as the primary HDU
- Ensured CASAMBM header card matches the HDU list

## [1.0.1] - 2026-07-22

### Added
- Added requirement to upgrade pip into README.md and contributing.md

## [1.0.0] - 2026-07-03

### Added
- Initial cutouts service scaffold and CLI.
- Query mode to check extents of remote fits file.
- Usage documentations
- Added Cutout abstract base class in preparation for Objstore implementation
- Changed current implementation to inherit from base Cutout class as an AstropyCutout class
- Rearanged file structure to match heirarchy
- Updated tests to match
- Added switch to change backend to use either Astropy or ObjStore