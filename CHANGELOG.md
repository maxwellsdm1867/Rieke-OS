# Disco changelog

## 0.1.3 - 2026-09-30

This desktop candidate uses the explicit unsigned testing channel, separate
from signed production distribution.

### Added
- Independent Disco source and explicit runtime application profile; MATLAB data export remains, while EpicTreeGUI/MATLAB GUI, plotting, launchers and UGM interaction are removed.
- Self-contained Apple Silicon desktop packaging with private Python and MySQL runtimes, folder selection, controlled installation, and testing-channel updates.
- Persistent native tag membership and autocomplete dictionaries, with Unicode prefix indexes, maintained usage counts, and exact author attribution.
- Transactional annotation history, incremental current-state recovery, and verified index migration and reuse.

### Improved
- Small annotation batches acknowledge durable saves promptly; cell tags inherit by cell UUID without copying annotations into every epoch.
- Large-project browsing, selection, metadata storage, cache validation, and protocol-scoped curation preserve exact scientific identities.
- Portable project handling, folder-boundary checks, draft preservation, and desktop service lifecycle validation.

At 100,000 synthetic epochs, tag autocomplete measured 21–26 ms. Initial native
index preparation took about two minutes; the paired two-save/filter API sequence
measured 192 ms. See the [reproducible benchmark report](docs/dev/scale-audit-2026-09-29/native-tag-sequence-results.md)
for scope, first-use measurements, and limitations.


## 0.1.2 — 2026-09-28

- Reject workspace roots inside an existing project or workspace before writing files.
- Preserve root selection across launch; report unavailable saved roots without silently recreating them.
- Verify both project identity and physical storage directory before reusing native databases or project servers.
- Reject moved imported projects with explicit recovery guidance; do not rewrite scientific references automatically.
- Require absolute path imports and keep upload/export writes inside their managed directories, including when symbolic links are present.
- Verify root selection, project creation, original-H5 import and complete chooser/API/database restart using paths with spaces and Unicode.

## 0.1.1 — 2026-09-28

- Preserve source cells and acquisition blocks that contain no epochs; verify
  complete source hierarchy membership after database import.
- Fix fresh macOS Python installation when compiler tools are on PATH.
- Serialize concurrent query/protocol database access and avoid sorting large
  audit payloads in MySQL.
- Retain project browser ports when available, preserving local author settings.
- Make epoch tag indicators compact and keep secondary controls under Tag tools.
- Use server-backed selection-mask downloads and informative protocol/date export
  names with underscores.
- Clarify rejected imports and source-refresh recovery; improve first-use guidance.
- Add real-data stress, independent H5/database audit and complete HTTP workflow
  verification harnesses, including export reads and restart persistence.

## 0.1.0 — 2026-09-28

- Initial standalone source distribution of the recording workspace and EpicTreeGUI.
- Application-local installer for native MySQL, Python, Node, and parser tools.
- Docker-free project creation, import, browsing, and exports.
- Private per-project credentials and database ownership validation.
- Quick start, source packaging, and real HTTP/H5/database integration verification.

## Earlier EpicTreeGUI history

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-28

### Added
- epicTreeTools hierarchical tree system for organizing neurophysiology epochs
- epicTreeGUI browser interface with 40/60 split tree and viewer panels
- 22+ splitter functions for dynamic tree reorganization by experimental parameters
- getSelectedData data extraction function respecting user selections
- .ugm (User-Generated Metadata) persistence system for selection state
- Selection state management with isSelected flags and propagation logic
- install.m script for automated MATLAB path setup
- Comprehensive test suite with 60+ test cases covering core functionality
- Documentation for tree navigation, selection patterns, and Python integration

### Changed
- Pure MATLAB replacement of legacy Java-based epoch tree system
- Simplified architecture with epoch.isSelected as source of truth (no centralized mask)
- Three-file architecture: H5/MAT (raw data), UGM (selection state), workspace (active tree)

## [Unreleased]

Future enhancements will be listed here.
