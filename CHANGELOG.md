# Disco changelog

## 0.1.10 - 2026-10-09

Combined unsigned Apple silicon testing build.

- Allow complete Workbench selections above 1,000 epochs using bounded transfer, exact membership and durable merge recovery.
- Merge a held imported recording directly into Main with source-specific acceptance authority; keep review details in More and toolbar controls reachable.
- Admit verified MySQL JSON representations of acquisition floats while retaining exact source metadata, searches, grouping and identities.
- Preserve exact numeric values in saved filters, sealed recipes, snapshots and prepared transfers, with transactional readback verification.


## 0.1.5 - 2026-09-30

Unsigned Apple Silicon testing release of **Disco**, with updates and source
remaining in **maxwellsdm1867/Rieke-OS**. This release includes 19 merged fixes;
issue #5's proposed three precomputed Cell QC analyses remain open and are not
part of this release.

- Cell QC opens per-epoch bath-temperature observations, uses the measured first-epoch block baseline for resting voltage, and removes unmeasured input resistance (#2–#4).
- Simplify window/project titles; preserve original H5 names through migration and restore; contain long names; support confirmed managed-H5 deletion, propagation and clean re-import; clarify archive and restore actions (#6–#10).
- Show retained protocol totals beside temporary matches, keep tag predicates synchronized across browsing and export, and provide consistent scrollbars and pane resize handles (#11–#12).
- Combine Activity and Exports under Logs; expose whole-project share/export and opening in Project files; consolidate setup in the side rail and working/portable folders in one browse-first Open a project flow (#13–#14, #16–#17).
- Rename App Updates and notify once for newly discovered versions; recover orderly Quit when the scientific page is unavailable, preserving known persistence outcomes (#15, #18).
- Add revision-checked Cmd+Z/Ctrl+Z for saved tags and analysis inclusion with bounded session memory, original target identities and local search-selection undo. Native and mounted performance measurements are published in [the validation report](docs/dev/undo-2026-09-30/README.md) (#19).
- Use Disco branding and the Disco ball by default, with the Rieke emblem available as an appearance Easter egg (#20–#21).
- Preserve the internal macOS bundle name required by Electron to locate the existing Rieke OS helper executables, while displaying Disco. The unpublished 0.1.4 candidate failed native startup; 0.1.5 carries its fixes and this compatibility correction.

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
