# Selection State Architecture

## Overview

The epicTreeGUI system uses a selection filtering mechanism to allow users to choose which epochs to include in analysis workflows. This document describes the complete architecture of the selection state system, including storage, propagation, persistence, and Python integration.

**Key Design Principle:** During active work sessions, the `epoch.isSelected` flag on each epoch struct is the single source of truth. Selection masks are built/copied only during save/load operations (one-time), not continuously synchronized in real-time.

**Three-File Architecture:**
1. **`.mat` file** - Raw experiment data exported from Python (never modified by GUI)
2. **`.ugm` file** - User-Generated Metadata containing selection masks (versioned by timestamp)
3. **MATLAB workspace** - Active tree with `isSelected` flags (source of truth during session)

This separation keeps raw data pristine while allowing multiple saved selection states.

---

## Storage Model

### Primary Storage: epoch.isSelected Flag

Each epoch struct has an `isSelected` field (logical scalar) that determines whether it's included in filtered queries:

```matlab
epoch = struct(...
    'cellInfo', cellInfo, ...
    'parameters', parameters, ...
    'responses', responses, ...
    'isSelected', true  % <-- Selection state stored here
);
```

**Default state:** `true` (all epochs selected when first loaded)

**Modification:** Use `setSelected()` method on tree nodes, NOT direct field access

### Secondary Storage: Node Custom Cache

Tree nodes cache selection state in `node.custom.isSelected` for fast hierarchical queries:

```matlab
% Internal node: true if any child is selected
node.custom.isSelected = true;

% Leaf node: true if any epoch in epochList is selected
node.custom.isSelected = any(cellfun(@(e) e.isSelected, node.epochList));
```

**Purpose:** Avoid walking entire tree to determine if a branch has selected data

**Synchronization:** `refreshNodeSelectionState()` rebuilds cache from actual epoch states

**Important:** Node cache is derived state, not source of truth. Always sync after direct epoch modifications.

---

## Simplified Architecture: One-Time Mask Building

**Design principle:** Build mask only when needed (save/close), not during session.

### During Session (Source of Truth)

- `epoch.isSelected` flag on each epoch struct
- User clicks update `isSelected` via `setSelected()` method
- `getAllEpochs(true)` filters by `isSelected` (loop is fine for typical dataset sizes <10k epochs)
- No centralized `selectionMask` property
- No real-time synchronization overhead

### On Save (One-Time Operation)

```matlab
% Build mask from isSelected flags ONE-TIME
allEps = tree.getAllEpochs(false);  % Get all epochs (unfiltered)
mask = false(length(allEps), 1);

for i = 1:length(allEps)
    mask(i) = allEps{i}.isSelected;
end

% Save to .ugm file
ugm.selection_mask = mask;
save(filepath, 'ugm', '-v7.3');

fprintf('Saved selection mask: %d of %d epochs selected (%.1f%%)\n', ...
    sum(mask), length(mask), 100*sum(mask)/length(mask));
```

### On Load (One-Time Operation)

```matlab
% Load mask from .ugm file
loaded = load(filepath);
mask = loaded.ugm.selection_mask;

% Copy to isSelected flags ONE-TIME
allEps = tree.getAllEpochs(false);
for i = 1:length(allEps)
    allEps{i}.isSelected = mask(i);
end

% Sync node cache
tree.refreshNodeSelectionState();

fprintf('Selection mask loaded: %d of %d epochs excluded (%.1f%%)\n', ...
    sum(~mask), length(mask), 100*sum(~mask)/length(mask));
```

### Rationale

- **Simple:** isSelected is single source of truth during work
- **Fast:** No sync overhead on every click
- **One-time comparison on close is not performance critical**
- **Avoids dual-storage synchronization bugs**
- **Follows separation of concerns:** epoch selection state lives on epochs

---

## Hierarchy Propagation

Selection state propagates from parent to children when using recursive mode:

### Recursive Deselect

```matlab
% Deselect this node and all descendants
node.setSelected(false, true);
```

**Behavior:**
1. If leaf node: sets `epoch.isSelected = false` for all epochs in `node.epochList`
2. If internal node: recursively calls `setSelected(false, true)` on all children
3. Updates `node.custom.isSelected = false` for this node

**Use case:** User deselects a cell type → all experiments for that cell type excluded

### Non-Recursive Select/Deselect

```matlab
% Deselect only this leaf node's epochs, not siblings
leafNode.setSelected(false, false);
```

**Behavior:** Only affects epochs directly attached to this node, not related nodes

**Use case:** User deselects specific contrast condition while keeping others selected

### Root Select All / Deselect All

```matlab
% Deselect entire tree
tree.setSelected(false, true);

% Reselect entire tree
tree.setSelected(true, true);
```

**Behavior:** Walks entire tree recursively, updating all `epoch.isSelected` flags

**Use case:** User wants to start fresh selection or select all for export

---

## Filtering API

### getAllEpochs(onlySelected)

Primary method for retrieving epochs with optional selection filtering:

```matlab
% Get only selected epochs
selectedEpochs = tree.getAllEpochs(true);

% Get all epochs regardless of selection
allEpochs = tree.getAllEpochs(false);
```

**Implementation:** Recursively walks tree, collects epochs from leaf nodes, filters by `isSelected` flag

**Performance:** O(n) where n = total epochs. Acceptable for typical dataset sizes (<10k epochs).

### getSelectedData(nodeOrEpochs, streamName)

**Critical function** used by ALL analysis workflows:

```matlab
% Get data matrix from selected epochs only
[dataMatrix, selectedEpochs, sampleRate] = getSelectedData(treeNode, 'Amp1');
```

**Filtering behavior:**
1. If input is `epicTreeTools` node: calls `getAllEpochs(true)` to filter
2. If input is cell array of epochs: filters to epochs where `isSelected == true`
3. Returns data only from selected epochs

**Impact:** This ensures analysis functions respect user selection filtering automatically

### selectedCount() and epochCount()

```matlab
% Total epochs at this node
total = node.epochCount();

% Selected epochs at this node
selected = node.selectedCount();

% Calculate percentage
pctSelected = 100 * selected / total;
```

**Use case:** Display selection statistics in GUI, validate filtering working correctly

---

## .ugm File Persistence

### Purpose

The .ugm (User-Generated Metadata) file stores selection state separately from raw experiment data, enabling:

- Selection state survives MATLAB session restarts
- Multiple saved selection states (versioned by timestamp)
- Raw `.mat` files never modified (pristine data preservation)
- User can share selection states independently from data

### When Persistence Happens

**On Save:**
- User clicks File → Save Epoch Mask in GUI
- Manual call to `tree.saveUserMetadata(filepath)`

**On Load:**
- Constructor option: `epicTreeTools(data, 'LoadUserMetadata', 'auto')` (default)
- Manual call to `tree.loadUserMetadata(filepath)`

**On Close:**
- GUI close handler compares current mask to loaded mask
- If different, prompts: "Update mask with session changes?"
- If user confirms, updates latest .ugm file

---

## Three-File Architecture

### File Roles

| File | Purpose | Modified by GUI? | Shared? |
|------|---------|------------------|---------|
| `.h5` | Raw experiment data from acquisition | Never | Between users |
| `.mat` | Exported epoch structure from Python | Never | Between users |
| `.ugm` | Selection masks, user metadata | Yes (only this) | Optional |

### Workflow

1. **Python pipeline:** Export H5 → MAT (via `export_to_epictree.py`)
2. **MATLAB session:** Load MAT → build tree → make selections → save .ugm
3. **Subsequent sessions:** Load MAT + .ugm → resume with previous selections
4. **Python analysis:** Read MAT + .ugm → filter epochs → export to database

### Directory Structure

```
/experiment_data/
├── 2025-12-02_F.h5                           # Raw acquisition data
├── 2025-12-02_F.mat                          # Exported epoch structure
├── 2025-12-02_F_2026-02-15_10-30-00.ugm     # Selection state v1
└── 2025-12-02_F_2026-02-16_14-45-00.ugm     # Selection state v2
```

**Note:** Multiple .ugm files can exist (versioned by timestamp). System auto-loads latest by default.

---

## .ugm File Format

### Structure (v1.1)

The .ugm file is a MATLAB MAT file (v7.3 / HDF5 format) containing a single struct:

```matlab
ugm = struct(...
    'version',          '1.1', ...              % Format version string
    'created',          '2026-02-16 10:00:00', ...  % Creation timestamp (string)
    'epoch_count',      length(allEps), ...     % Total epoch count (validation)
    'mat_file_basename', 'data_file', ...       % Source .mat basename
    'selection_mask',   logical([1; 0; 1; ...]),% Boolean mask (length = epoch_count)
    'epoch_h5_uuids',  {uuid1, uuid2, ...}     % Cell array of h5_uuid strings
);
```

### Field Descriptions

- **`version`**: Format version. Current version is `'1.1'` (added `epoch_h5_uuids`).
- **`created`**: Timestamp string (`'yyyy-mm-dd HH:MM:SS'`) showing when .ugm was created.
- **`epoch_count`**: Total number of epochs. Used to validate mask matches current tree.
- **`mat_file_basename`**: Basename of source .mat file (without extension). Helps identify which .mat this .ugm belongs to.
- **`selection_mask`**: Logical column vector. Index i = true means epoch i is selected.
- **`epoch_h5_uuids`**: Cell array of h5_uuid strings, one per epoch. Used for UUID-based matching on load (not positional). Epochs without h5_uuid get empty string `''`.

### Loading Strategy: UUID-Based Matching

`loadUserMetadata()` matches epochs by `h5_uuid`, not by position:

1. Build a lookup map from the .ugm: `h5_uuid → selected (true/false)`
2. For each epoch in the tree, find its h5_uuid in the map
3. Apply the corresponding selection state
4. Unmatched epochs default to selected

This is robust to:
- Epoch reordering between exports
- Database repopulation adding/removing epochs
- Different splitter configurations changing tree structure

**Requirement:** Both the .ugm file and the loaded epochs must have h5_uuid. If either is missing, `loadUserMetadata()` warns and refuses to load (no positional fallback).

### Filename Convention

```
{mat_basename}_{YYYY-MM-DD}_{HH-mm-ss}.ugm
```

**Examples:**
- `experiment_2025-12-02_2026-02-15_10-30-00.ugm`
- `data_file_2026-01-20_08-45-30.ugm`

**Timestamp:** ISO 8601-like format ensures lexicographic sorting equals chronological sorting

---

## Discovery Logic

### Finding Latest .ugm File

The `findLatestUGM()` static method discovers the most recent .ugm file:

```matlab
latestUGM = epicTreeTools.findLatestUGM('/path/to/data_file.mat');
```

**Algorithm:**
1. Extract directory and basename from .mat file path
2. Use `dir()` to find all files matching `{basename}_*.ugm` pattern
3. Sort filenames in descending order (newest first)
4. Return path to first match, or `''` if no .ugm files exist

**Why sorting works:** ISO 8601 timestamps sort lexicographically == chronologically

**Example:**
```
data_file_2026-02-10_12-00-00.ugm  # Older
data_file_2026-02-15_14-30-00.ugm  # Newer
data_file_2026-02-16_08-00-00.ugm  # Newest <-- returned
```

### Auto-Loading Behavior

Constructor default behavior:

```matlab
% Auto-load latest .ugm if exists (default)
tree = epicTreeTools(data);
```

**Implementation:**
1. Check if `data.source_file` field exists (provided by `loadEpicTreeData`)
2. Call `findLatestUGM(data.source_file)`
3. If .ugm found: call `loadUserMetadata(ugmPath)` and print message
4. If not found: silently continue (all epochs selected by default)

**User-facing message:**
```
Auto-loading selection mask: /path/to/data_file_2026-02-16_08-00-00.ugm
Selection mask loaded: 450 of 1200 epochs excluded (37.5%)
```

---

## Save/Load API

### Save Methods

#### saveUserMetadata(filepath)

```matlab
% Save current selection state to .ugm file
filepath = '/path/to/data_file_2026-02-16_10-00-00.ugm';
tree.saveUserMetadata(filepath);
```

**Behavior:**
1. Get all epochs (unfiltered): `allEps = tree.getAllEpochs(false)`
2. Build mask from `isSelected` flags (one-time loop)
3. Create `ugm` struct with version, created, epoch_count, mat_file_basename, selection_mask
4. Save to filepath using MATLAB v7.3 format
5. Print confirmation message with selection count

**Error handling:** Throws error if save fails (permission denied, disk full, etc.)

#### generateUGMFilename(matFilePath) [static]

```matlab
% Generate timestamped .ugm filename for a .mat file
ugmPath = epicTreeTools.generateUGMFilename('/path/to/data_file.mat');
% Returns: /path/to/data_file_2026-02-16_10-30-45.ugm
```

**Behavior:**
1. Extract directory and basename from matFilePath
2. Create timestamp: `datestr(now, 'yyyy-mm-dd_HH-MM-SS')`
3. Return `fullfile(directory, sprintf('%s_%s.ugm', basename, timestamp))`

### Load Methods

#### loadUserMetadata(filepath)

```matlab
% Load selection state from .ugm file
success = tree.loadUserMetadata('/path/to/data_file_2026-02-16.ugm');
if ~success
    warning('Failed to load .ugm file');
end
```

**Behavior:**
1. Validate file exists
2. Load .ugm file and check for `ugm` struct
3. Validate `epoch_count` matches current tree (warn and return false if mismatch)
4. Copy `selection_mask` to `epoch.isSelected` flags (one-time loop)
5. Call `refreshNodeSelectionState()` to sync node cache
6. Print message showing excluded epoch count
7. Return true on success, false on failure

**Error handling:** Returns false and warns on: missing file, corrupted file, epoch count mismatch

#### findLatestUGM(matFilePath) [static]

```matlab
% Find most recent .ugm file for a .mat file
latestUGM = epicTreeTools.findLatestUGM('/path/to/data_file.mat');
if isempty(latestUGM)
    disp('No .ugm files found');
else
    disp(['Latest: ' latestUGM]);
end
```

**Behavior:**
1. Extract directory and basename from matFilePath
2. Search for `{basename}_*.ugm` files in same directory
3. Sort filenames descending (newest first)
4. Return path to newest file, or `''` if none exist

---

## Constructor Options

The `epicTreeTools` constructor accepts a `LoadUserMetadata` option to control .ugm auto-loading:

### Option: 'auto' (default)

```matlab
tree = epicTreeTools(data);
% OR explicitly:
tree = epicTreeTools(data, 'LoadUserMetadata', 'auto');
```

**Behavior:**
- If latest .ugm exists: auto-load it and print message
- If no .ugm exists: silently continue (all epochs selected)
- User-friendly default for most workflows

### Option: 'latest'

```matlab
tree = epicTreeTools(data, 'LoadUserMetadata', 'latest');
```

**Behavior:**
- Throws error if no .ugm file exists
- Use when you require selection mask to be present

### Option: 'none'

```matlab
tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
```

**Behavior:**
- Skip .ugm loading entirely
- All epochs selected by default
- Use when starting fresh selection from scratch

### Option: '/path/to/file.ugm'

```matlab
tree = epicTreeTools(data, 'LoadUserMetadata', '/path/to/specific_file.ugm');
```

**Behavior:**
- Load specific .ugm file (not auto-discover latest)
- Throws error if file doesn't exist or loading fails
- Use when you want to load a specific saved selection state (not latest)

---

## GUI Integration

### epicTreeGUI Constructor

When GUI is launched with a pre-built tree, it automatically captures .ugm state:

```matlab
% Build tree (auto-loads latest .ugm if exists)
tree = epicTreeTools(data);

% Launch GUI
gui = epicTreeGUI(tree);
```

**GUI initialization:**
1. Copies `tree.sourceFile` to `gui.matFilePath` (for .ugm discovery)
2. Calls `buildCurrentMask()` to snapshot initial selection state
3. Stores snapshot in `gui.loadedMask` for close comparison

### File Menu: Save Epoch Mask

**Menu item:** File → Save Epoch Mask...

**Behavior:**
1. Validate data loaded and `matFilePath` available
2. If `matFilePath` empty: prompt user to locate .mat file
3. Call `findLatestUGM(matFilePath)` to check for existing .ugm
4. If no .ugm exists: create new with timestamped filename
5. If .ugm exists: show questdlg with "Replace Latest" or "Create New" options
6. Call `tree.saveUserMetadata(filepath)` to persist
7. Update `loadedMask` to current state (for close comparison)
8. Show confirmation message with saved file path

**User experience:** Explicit control over when to save, option to version or replace

---

## Close Handler Workflow

### On GUI Window Close

When user closes GUI (File → Close or window X button), the close handler executes:

**Step 1: Build current mask from isSelected flags (one-time)**

```matlab
currentMask = self.buildCurrentMask();
```

**Step 2: Compare to loaded mask**

```matlab
if ~isequal(currentMask, self.loadedMask)
    % Masks differ - user made changes
    changed = true;
else
    % No changes - skip prompt
    changed = false;
end
```

**Step 3: Prompt user if changed**

```matlab
if changed
    choice = questdlg(...
        'Selection state has changed since loading. Update mask with session changes?', ...
        'Save Changes?', ...
        'Update Mask', 'Discard Changes', 'Cancel', ...
        'Update Mask');  % Default
end
```

**Step 4: Handle user choice**

```matlab
switch choice
    case 'Update Mask'
        % Find latest .ugm or create new if none exists
        latestUGM = epicTreeTools.findLatestUGM(self.matFilePath);
        if isempty(latestUGM)
            filepath = epicTreeTools.generateUGMFilename(self.matFilePath);
        else
            filepath = latestUGM;  % Update latest, not create new
        end
        self.tree.saveUserMetadata(filepath);
        delete(self.figure);  % Close window

    case 'Discard Changes'
        delete(self.figure);  % Close without saving

    case 'Cancel'
        return;  % Stay in GUI, don't close
end
```

### User Experience

- **Explicit control:** User chooses whether to save changes
- **No auto-save surprises:** Changes not saved without confirmation
- **Can discard changes:** Useful if user experimented and wants to revert
- **Can cancel close:** If user clicks close accidentally
- **Updates latest .ugm:** "Update Mask" modifies existing file, not create duplicate

### Implementation in epicTreeGUI

```matlab
% In epicTreeGUI.onClose()
function onClose(self)
    % Build current mask from isSelected flags (one-time, on close)
    currentMask = self.buildCurrentMask();

    % Compare to mask loaded at startup
    if ~isequal(currentMask, self.loadedMask)
        % Prompt user with questdlg
        choice = questdlg('Update mask with session changes?', ...);

        if strcmp(choice, 'Update Mask')
            % Save to latest .ugm or create new
            latestUGM = epicTreeTools.findLatestUGM(self.matFilePath);
            if isempty(latestUGM)
                filepath = epicTreeTools.generateUGMFilename(self.matFilePath);
            else
                filepath = latestUGM;
            end
            self.tree.saveUserMetadata(filepath);
        elseif strcmp(choice, 'Cancel')
            return;  % Don't close
        end
        % 'Discard Changes' falls through to close
    end

    % Close figure
    delete(self.figure);
end
```

---

## Common Anti-Patterns

### ❌ ANTI-PATTERN 1: Direct epoch modification (BUG-001 root cause)

**WRONG:**

```matlab
% Get epochs
epochs = tree.getAllEpochs(false);

% Try to deselect by modifying returned copies
for i = 1:length(epochs)
    epochs{i}.isSelected = false;  % ❌ WRONG - modifying copy
end

% Check selection (will still show all selected!)
selected = tree.getAllEpochs(true);
assert(isempty(selected), 'Expected empty');  % FAILS - still has all epochs
```

**Why this fails:**
- `getAllEpochs()` returns COPIES of epoch structs, not references
- MATLAB structs are value types, not reference types
- Modifying `epochs{i}.isSelected` only changes the copy in `epochs` cell array
- Original epoch structs inside tree nodes are unchanged

**✅ CORRECT:**

```matlab
% Use setSelected() method to modify tree directly
tree.setSelected(false, true);  % Deselect recursively

% Verify
selected = tree.getAllEpochs(true);
assert(isempty(selected), 'All deselected');  % PASSES
```

**Why this works:**
- `setSelected()` walks tree and modifies actual epoch structs in `node.epochList`
- Changes persist because tree nodes hold the actual epoch references

### ❌ ANTI-PATTERN 2: Manually building selection masks

**WRONG:**

```matlab
% Manually create selection mask array
mask = true(1200, 1);
mask(501:end) = false;  % Deselect second half

% Try to apply to tree... how?
% No direct API for this!
```

**✅ CORRECT:**

```matlab
% Use setSelected() on tree nodes
allEps = tree.getAllEpochs(false);
for i = 1:length(allEps)
    if i <= 500
        allEps{i}.isSelected = true;
    else
        allEps{i}.isSelected = false;
    end
end

% Sync node cache after direct modification
tree.refreshNodeSelectionState();
```

**Even better (if filtering by condition):**

```matlab
% Use tree structure to select/deselect
% Example: deselect specific cell type
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    if strcmp(child.splitValue, 'Off parasol')
        child.setSelected(false, true);  % Deselect this cell type
    end
end
```

### ❌ ANTI-PATTERN 3: Assuming epoch order is stable

**WRONG:**

```matlab
% Save selection state manually
initialEpochs = tree.getAllEpochs(false);
initialOrder = cellfun(@(e) e.cellInfo.id, initialEpochs, 'UniformOutput', false);

% ... rebuild tree with different split keys ...
tree.buildTree({'parameters.contrast'});  % Different organization

% Try to restore selection based on saved order
newEpochs = tree.getAllEpochs(false);
for i = 1:length(initialOrder)
    newEpochs{i}.isSelected = ...;  % ❌ WRONG - order may have changed!
end
```

**✅ CORRECT:**

```matlab
% Use .ugm files to save/load selection state
% The .ugm system handles epoch ordering automatically
tree.saveUserMetadata('data_2026-02-16.ugm');

% ... rebuild tree ...
tree.buildTree({'parameters.contrast'});

% Load selection (maps to epochs correctly)
tree.loadUserMetadata('data_2026-02-16.ugm');
```

### ❌ ANTI-PATTERN 4: Forgetting to sync node cache

**WRONG:**

```matlab
% Directly modify epoch flags (unusual but possible in some workflows)
allEps = tree.getAllEpochs(false);
for i = 1:length(allEps)
    allEps{i}.isSelected = (rand() < 0.5);  % Random selection
end

% Use tree navigation without syncing
% node.custom.isSelected will be stale!
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    if child.custom.isSelected  % ❌ WRONG - cache not synced
        analyzeData(child);
    end
end
```

**✅ CORRECT:**

```matlab
% After direct epoch modification, sync node cache
allEps = tree.getAllEpochs(false);
for i = 1:length(allEps)
    allEps{i}.isSelected = (rand() < 0.5);
end

% Sync cache
tree.refreshNodeSelectionState();  % ✅ REQUIRED

% Now node.custom.isSelected is accurate
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    if child.custom.isSelected
        analyzeData(child);
    end
end
```

---

## Python Integration

### Reading .ugm Files in Python

The .ugm file is saved in MATLAB's v7.3 format (HDF5). **Use `h5py` to read it, not `scipy.io.loadmat`.**

The provided `python/import_ugm.py` module handles all the HDF5 parsing:

```python
from import_ugm import read_ugm

ugm_data = read_ugm('experiment_2025-12-02_2026-02-15_10-30-00.ugm')

print(ugm_data)
# {
#     'version': '1.1',
#     'created': '2026-02-16 10:00:00',
#     'epoch_count': 1915,
#     'selected_count': 1328,
#     'excluded_count': 587,
#     'excluded_uuids': ['abc-123', 'def-456', ...],  # h5_uuids of deselected epochs
#     'selected_uuids': ['ghi-789', 'jkl-012', ...],  # h5_uuids of selected epochs
# }
```

**Why h5py?** MATLAB's `-v7.3` flag saves in HDF5 format. `scipy.io.loadmat` raises `NotImplementedError` for v7.3 files. The `import_ugm.py` module handles HDF5 object references, cell arrays of strings, and other MATLAB-specific HDF5 patterns.

### Reading .ugm Files Directly with h5py

If you need lower-level access:

```python
import h5py
import numpy as np

with h5py.File('file.ugm', 'r') as f:
    ugm = f['ugm']
    mask = np.array(ugm['selection_mask']).flatten().astype(bool)
    epoch_count = int(np.array(ugm['epoch_count']).flatten()[0])

    # Read h5_uuids (cell array of strings stored as HDF5 object references)
    refs = np.array(ugm['epoch_h5_uuids']).flatten()
    uuids = []
    for ref in refs:
        chars = np.array(f[ref]).flatten()
        uuids.append(''.join(chr(int(c)) for c in chars))

    print(f"Selected {np.sum(mask)} of {epoch_count} epochs")
```

### DataJoint Round-Trip

The full round-trip workflow pushes MATLAB selections back to DataJoint as epoch tags:

```
DataJoint ──export .mat──> MATLAB ──save .ugm──> Python ──import tags──> DataJoint
```

1. **Export from DataJoint** (web UI "Export to epicTree" button)
   - Creates `.mat` with `h5_uuid` on every epoch, cell, group, block
   - Flask endpoint: `POST /results/export-mat`

2. **Analyze in MATLAB**
   ```matlab
   [data, ~] = loadEpicTreeData('epictree_export_20260216.mat');
   tree = epicTreeTools(data);
   tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
   gui = epicTreeGUI(tree);
   % User selects/deselects epochs...
   % On close: prompted to save .ugm
   ```

3. **Import mask back to DataJoint** (web UI "Import Mask" button)
   - Upload `.ugm` file via file picker
   - Flask endpoint: `POST /results/import-ugm`
   - Deselected epochs get tagged `"excluded"` in the Tags table, keyed by `h5_uuid`
   - Import is idempotent (re-importing same .ugm = same result)

4. **Result**: DataJoint Tags table reflects MATLAB selections

**Programmatic import** (without web UI):

```python
from import_ugm import read_ugm

ugm_data = read_ugm('experiment.ugm')

# ugm_data['excluded_uuids'] contains h5_uuids of deselected epochs
# Use these to insert 'excluded' tags into your DataJoint Tags table
for uuid in ugm_data['excluded_uuids']:
    # Your DataJoint insert logic here
    Tags.insert1({'h5_uuid': uuid, 'tag': 'excluded', ...})
```

### h5_uuid: The Stable Epoch Identifier

The `h5_uuid` field is the **only** identifier used for matching between .ugm masks and epoch data. It is:

- Derived from the H5 source file (stable across database repopulations)
- Present on every epoch, cell, epoch_group, epoch_block, and experiment
- Required by both `loadUserMetadata()` (MATLAB) and `read_ugm()` (Python)

**Why not database IDs?** Auto-increment IDs change when the database is repopulated. If you export, analyze in MATLAB, save a .ugm, then the database gets repopulated with new IDs, a positional or ID-based mask would apply to the wrong epochs. `h5_uuid` survives this.

### Finding the Latest .ugm File in Python

```python
import os
import glob

def find_latest_ugm(mat_file_path):
    """Find most recent .ugm file for a given .mat file"""
    directory = os.path.dirname(mat_file_path)
    basename = os.path.splitext(os.path.basename(mat_file_path))[0]

    pattern = os.path.join(directory, f"{basename}_*.ugm")
    ugm_files = glob.glob(pattern)

    if not ugm_files:
        return None

    # Sort by filename (ISO 8601 timestamps sort correctly)
    ugm_files.sort(reverse=True)
    return ugm_files[0]
```

### Three-File Workflow

```
experiment.mat                  Raw epoch data (from Python/DataJoint)
experiment_2026-02-16_*.ugm     Selection masks (from MATLAB)
DataJoint Tags table            Persistent tags (from .ugm import)
```

1. **Export** → `.mat` with h5_uuids
2. **MATLAB** → load `.mat`, build tree, select/deselect, save `.ugm`
3. **Import** → read `.ugm`, push excluded tags to DataJoint by h5_uuid
4. **Re-export** → Tags appear in next `.mat` export at all hierarchy levels

---

## Testing

### Selection State Tests

**File:** `tests/test_selection_state.m`

**Test cases:**
- Deselect all → verify `getAllEpochs(true)` returns empty
- Deselect → reselect → verify original count restored
- Recursive deselect on internal node → verify all descendants deselected
- Partial selection → verify only selected subset returned
- Integration with `getSelectedData()` → verify filtering applied
- **Anti-pattern test:** Document that direct epoch modification doesn't work
- Node cache sync → verify `refreshNodeSelectionState()` updates cache correctly

### .ugm Persistence Tests

**File:** `tests/test_ugm_persistence.m`

**Test cases:**
- Save creates .ugm file with correct format
- Save/load round-trip preserves exact selection state
- Load validates epoch count (warns on mismatch)
- Load handles missing/corrupted files gracefully
- `findLatestUGM()` returns newest file (timestamp sorting)
- Constructor `LoadUserMetadata` options work ('auto', 'latest', 'none', filepath)
- **Architecture test:** Verify no centralized `selectionMask` property exists
- Command window messages appear with correct epoch counts

**Run tests:**
```matlab
% Run both test suites
results = runtests('tests/test_selection_state.m', 'tests/test_ugm_persistence.m');
disp(results);
```

---

## Implementation Files

### Core Selection State

- **`src/tree/epicTreeTools.m`** (lines 943-1015)
  - `getAllEpochs(onlySelected)` - Recursive epoch collection with filtering
  - `setSelected(flag, recursive)` - Modify selection state with propagation
  - `selectedCount()` - Count selected epochs at node
  - `epochCount()` - Count total epochs at node
  - `refreshNodeSelectionState()` - Sync node cache with epoch states

### .ugm Persistence

- **`src/tree/epicTreeTools.m`** (lines 1450-1550)
  - `saveUserMetadata(filepath)` - Build mask from isSelected, save to .ugm
  - `loadUserMetadata(filepath)` - Load .ugm, copy mask to isSelected
  - `findLatestUGM(matFilePath)` [static] - Discover newest .ugm file
  - `generateUGMFilename(matFilePath)` [static] - Create timestamped filename

### Data Loading

- **`src/loadEpicTreeData.m`** (line 64-65)
  - Adds `source_file` field to returned data struct
  - Enables .ugm auto-discovery in constructor

### GUI Integration

- **`epicTreeGUI.m`** (lines 33-34, 93-99)
  - `matFilePath` property - Stores source .mat path
  - `loadedMask` property - Stores initial selection for close comparison
  - Constructor wires properties from `tree.sourceFile`

- **`epicTreeGUI.m`** (lines 576-632)
  - `onSaveEpochMask()` - File → Save Epoch Mask menu callback
  - Implements replace/create dialog, calls `saveUserMetadata()`

- **`epicTreeGUI.m`** (lines 410-450)
  - `onClose()` - Close handler with mask comparison
  - Prompts user if changes detected, offers Update/Discard/Cancel

- **`epicTreeGUI.m`** (lines 937-951)
  - `buildCurrentMask()` - Build selection mask from current isSelected flags

### Analysis Integration

- **`src/getSelectedData.m`** (lines 35-60)
  - Filters epochs to only `isSelected == true` before building data matrix
  - Used by ALL analysis workflows (LSTA, RF analysis, etc.)

---

## Future Considerations

### Possible Enhancements

1. **Additional metadata in .ugm:**
   - User notes explaining selection rationale
   - Analysis parameters tied to selection
   - Color coding or tagging of selected epochs

2. **Selection history:**
   - Undo/redo for selection changes
   - Version control for .ugm files (git-style diffs)

3. **Advanced filtering:**
   - Programmatic selection (e.g., "select all epochs where response > threshold")
   - Boolean operations on selection masks (union, intersection, difference)

4. **Performance optimization:**
   - For very large trees (>50k epochs), consider maintaining centralized mask with sync protocol
   - Current one-time building approach works well for typical neuroscience datasets (<10k epochs)

5. **Python library:**
   - `epicTreePy` package for reading .mat + .ugm in Python
   - Native DataJoint integration for filtering before database export

### Backward Compatibility

Future .ugm format versions should:
- Maintain `selection_mask` field for compatibility
- Add new fields with default values when missing
- Include version check in `loadUserMetadata()` to handle format evolution

---

**Document Version:** 1.0
**Last Updated:** 2026-02-16
**Related Files:**
- `src/tree/epicTreeTools.m` (selection state implementation)
- `epicTreeGUI.m` (GUI integration)
- `tests/test_selection_state.m` (test suite)
- `tests/test_ugm_persistence.m` (persistence tests)
- `CLAUDE.md` (quick reference guide)
