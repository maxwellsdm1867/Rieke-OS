# Disco 0.2.16

## What's new

- Search recorded Symphony H5 attributes in Search predicate, Arrange tree and the live metadata sidebar. Each nested field keeps its original parent and name. Amp1 operating mode, offset and offset units are available when recorded. The value menu offers choices for the current search scope.
- Combine metadata and tag conditions in Filter view and Filter export. MATLAB data and Wheeler SQLite exports include the selected epochs’ physical H5 attributes, their types and shapes, and links to inherited attributes. In Wheeler SQLite, query `epoch_recorded_fields` for Amp1 mode, offset and nested fields. Use `epoch_h5_attributes` for the original H5 paths and encodings.
- Linked SQLite exports reference the project’s verified recording inventories. Use the bundled loader’s `h5_attributes(epoch_uuid)` method or its SQL function `epoch_h5_attributes(epoch_uuid)` to read the nested fields for an exported epoch. Keep the project’s `imports/h5-attributes` folder with the managed project when moving it.
- Text inputs use the blinking caret. Opening Recorded values moves typing into the filter. Use the arrow keys and Enter to choose a value or Escape to return to the condition. Selected rows and checked choices keep their highlights.

## Updating an existing project

Choose **App Updates → Download update → Restart to update**. Open your existing project with its recording drives connected. Disco automatically checks and builds the new searchable metadata on first open. Large projects can take longer on this first pass. To check coverage or repair a missing inventory after reconnecting a drive, use **Refresh metadata** and open its status details. Subsequent refreshes reuse verified recordings.

This is the unsigned Apple silicon testing distribution. The downloadable ZIP, update descriptor and SHA-256 checksums identify the same release.
