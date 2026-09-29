# Changes: Pre-Built Tree Pattern Only

## Summary

The epicTreeGUI has been updated to **ONLY** accept pre-built epicTreeTools objects. The dropdown-based dynamic reorganization pattern has been removed.

## What Changed

### 1. GUI Constructor
**Before:**
```matlab
gui = epicTreeGUI('data.mat');  % File path accepted
gui = epicTreeGUI(tree);        % Pre-built tree accepted
```

**After:**
```matlab
gui = epicTreeGUI(tree);  % ONLY pre-built trees accepted
```

### 2. UI Removed
- **Removed:** Split dropdown menu from GUI
- **Removed:** "Split By" control panel
- Tree panel now uses full available space (87% vs 78%)

### 3. Methods Removed
- `loadData(dataPath)` - No longer loads files directly
- `rebuildTree(splitKeys)` - No longer rebuilds tree dynamically
- `onSplitChanged(src)` - No longer handles dropdown changes
- `onLoadData()` - No longer shows file picker

### 4. Menu Updated
- **Removed:** File > Load Data... menu item
- **Kept:** File > Export Selection... (still works)
- **Kept:** File > Close

### 5. Properties Removed
- `treeData` - No longer stores original data
- `currentSplitKeys` - No longer tracks split configuration

### 6. Documentation Updated
- `CLAUDE.md` - Removed Pattern 1, shows only pre-built tree pattern
- `USAGE_PATTERNS.md` - Removed Pattern 1 comparison
- `epicTreeGUI.m` - Updated class documentation

## Why This Change?

1. **Matches legacy pattern** - The old Java-based epochTreeGUI always used pre-built trees
2. **Explicit hierarchy** - You see exactly how data is organized in your code
3. **Reproducibility** - Same code = same tree structure every time
4. **Supports custom splitters** - Write any splitter function you need
5. **Simpler codebase** - Removed ~100 lines of dynamic reorganization code

## Migration Guide

### If you were using file paths:

**Before:**
```matlab
gui = epicTreeGUI('data.mat');
% Then use dropdown to change splits
```

**After:**
```matlab
% Build tree first
[data, ~] = loadEpicTreeData('data.mat');
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnExperimentDate,
    'cellInfo.id'
});

% Launch GUI
gui = epicTreeGUI(tree);
```

### To change hierarchy:
Simply modify the `buildTreeWithSplitters()` call and re-run your script.

## Available Splitters (22+)

The system has 22+ built-in splitters as static methods in `epicTreeTools`:

**Basic:**
- `splitOnCellType` - Cell type (OnP, OffP, etc.)
- `splitOnExperimentDate` - Experiment date/name
- `splitOnKeywords` - Epoch keywords
- `splitOnProtocol` - Protocol name

**Stimulus Parameters:**
- `splitOnContrast`, `splitOnF1F2Contrast`
- `splitOnTemporalFrequency`, `splitOnSpatialFrequency`
- `splitOnRadiusOrDiameter`
- `splitOnBarWidth`, `splitOnFlashDelay`
- `splitOnStimulusCenter`

**Recording Parameters:**
- `splitOnHoldingSignal`
- `splitOnOLEDLevel`
- `splitOnRecKeyword`

**F1/F2 Analysis:**
- `splitOnF1F2CenterSize`
- `splitOnF1F2Phase`

**Natural Images:**
- `splitOnPatchContrast_NatImage`
- `splitOnPatchSampling_NatImage`

**Other:**
- `splitOnLogIRtag`
- `splitOnEpochBlockStart`

**Plus:** Use key paths like `'cellInfo.id'`, `'parameters.contrast'`, etc.

## Example Usage

```matlab
% Load data
[data, ~] = loadEpicTreeData('data.mat');

% Build tree with any combination of splitters
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,        % Level 1
    @epicTreeTools.splitOnExperimentDate,  % Level 2
    'cellInfo.id',                         % Level 3: key path
    @epicTreeTools.splitOnContrast,        % Level 4
    @epicTreeTools.splitOnProtocol         % Level 5
});

% Launch GUI - tree structure is now fixed
gui = epicTreeGUI(tree);
```

## Testing

Run the test to verify the changes:
```matlab
run test_updated_gui.m
```

Expected output:
```
✓ GUI only accepts pre-built trees
✓ No split dropdown in GUI
✓ File paths correctly rejected
✓ Tree structure is fixed at launch
✓ ALL TESTS PASSED
```

## Files Modified

1. `epicTreeGUI.m` - Removed dropdown, file loading, and dynamic rebuild code
2. `CLAUDE.md` - Updated to show only pre-built tree pattern
3. `USAGE_PATTERNS.md` - Removed Pattern 1, kept only Pattern 2
4. `test_updated_gui.m` - New test file for verification

## Files Unchanged

All splitter functions, tree building logic, and analysis functions remain unchanged. The only changes are to the GUI initialization and UI.

---

**Date:** 2026-02-02
**Status:** ✅ COMPLETE
**Verified:** All tests passing
