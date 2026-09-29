# Rieke Lab OS changelog

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
