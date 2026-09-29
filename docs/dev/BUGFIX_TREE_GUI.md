# Bug Fixes: Tree GUI Issues

## Issues Fixed

### 1. Callback Error (Brace Indexing)
**Error:**
```
Brace indexing is not supported for variables of this type.
Error in graphicalTree/fireNodesSelectedFcn (line 381)
    feval(fcn{1}, nodes);
```

**Cause:**
- Two versions of `graphicalTree.m` existed in the codebase
- Old version (in `old_epochtree/`) was being loaded instead of new version (in `src/gui/`)
- Old version expects callbacks as cell arrays: `fcn{1}`
- New version accepts function handles or cell arrays

**Fix:**
Updated all test scripts to:
1. Remove `old_epochtree` from path
2. Add `src/gui` to path **first** (before other paths)

**Files Updated:**
- `test_launch.m`
- `test_legacy_pattern.m`
- `test_exact_legacy_pattern.m`

**Path Setup (now in all test scripts):**
```matlab
% CRITICAL: Remove old_epochtree from path if it's there
warning('off', 'MATLAB:rmpath:DirNotFound');
rmpath(genpath('old_epochtree'));
warning('on', 'MATLAB:rmpath:DirNotFound');

% Add NEW code paths (in correct order - most specific first)
addpath('src/gui');           % CRITICAL: graphicalTree
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');
```

---

### 2. Long Protocol Names
**Issue:**
Protocol names like `edu.washington.riekelab.protocols.SingleSpot` were too long and displayed with boxes around them in the tree.

**Fix:**
Added `abbreviateProtocolName()` method to `epicTreeGUI.m`:
- Extracts just the protocol name (e.g., `SingleSpot`)
- Truncates to 40 characters max with '...'

**Example:**
- Before: `edu.washington.riekelab.protocols.SingleSpot (7)`
- After: `SingleSpot (7)`

**Files Updated:**
- `epicTreeGUI.m` (lines 373-676)

---

### 3. Legacy Pattern Support
**New Feature:**
GUI now accepts pre-built trees (matching legacy `epochTreeGUI` behavior):

```matlab
% Build tree in code
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnExperimentDate,
    'cellInfo.id'
});

% Launch GUI - no dropdown menu
gui = epicTreeGUI(tree);
```

**Files Updated:**
- `epicTreeGUI.m` - Modified constructor to accept `epicTreeTools` object
- `test_legacy_pattern.m` - Demo script
- `test_exact_legacy_pattern.m` - Exact legacy match demo
- `USAGE_PATTERNS.md` - Documentation

---

## Testing

### 1. Test Basic GUI (Dynamic Splits)
```matlab
run test_launch.m
```
- GUI should launch without errors
- Should be able to click on nodes
- Protocol names should be short (e.g., "SingleSpot", not full Java package)

### 2. Test Legacy Pattern (Fixed Structure)
```matlab
run test_legacy_pattern.m
```
- GUI should launch without split dropdown
- Tree structure should match code definition
- Should be able to navigate to leaf nodes
- Clicking nodes should not error

### 3. Test Exact Legacy Match
```matlab
run test_exact_legacy_pattern.m
```
- Should match legacy code exactly
- 7-level hierarchy as defined in code

---

## Root Cause Analysis

### Why did this happen?

1. **Path Pollution:** The `old_epochtree/` directory contains legacy Java-based code with different callback conventions. When this directory was on the MATLAB path (possibly from a previous session or startup script), it shadowed the new implementation.

2. **Class Name Collision:** Both old and new codebases have a `graphicalTree.m` class:
   - Old: `old_epochtree/.../graphicalTree.m` (expects cell array callbacks)
   - New: `src/gui/graphicalTree.m` (handles both function handles and cell arrays)

3. **Missing Path Management:** Test scripts didn't explicitly manage the MATLAB path, assuming the user had a clean workspace.

### Prevention

All test scripts now:
1. Explicitly remove `old_epochtree` from path
2. Add paths in specific order (most specific first)
3. Document the importance of path order

---

## Verification Checklist

After running the fixed code, verify:

- [ ] No "brace indexing" error when clicking nodes
- [ ] Protocol names are abbreviated (not full Java package paths)
- [ ] Can navigate to leaf nodes (individual protocols)
- [ ] Clicking leaf nodes displays data in right panel
- [ ] Info table updates with node information
- [ ] Pre-built tree mode has NO dropdown menu
- [ ] File loading mode HAS dropdown menu

---

## Files Changed Summary

| File | Change |
|------|--------|
| `epicTreeGUI.m` | Added pre-built tree support, protocol name abbreviation |
| `test_launch.m` | Added path management |
| `test_legacy_pattern.m` | Added path management |
| `test_exact_legacy_pattern.m` | Added path management |
| `USAGE_PATTERNS.md` | New documentation |
| `BUGFIX_TREE_GUI.md` | This file |

---

## Additional Notes

### If errors persist:

1. **Clear MATLAB workspace completely:**
   ```matlab
   clear all
   close all
   clc
   restoredefaultpath  % Reset to default MATLAB path
   ```

2. **Check for startup scripts:**
   - Look for `startup.m` in your MATLAB path
   - Ensure it's not adding `old_epochtree` to path

3. **Verify which graphicalTree is loaded:**
   ```matlab
   which graphicalTree
   ```
   Should show: `.../epicTreeGUI/src/gui/graphicalTree.m`
   NOT: `.../old_epochtree/.../graphicalTree.m`

4. **Manual path fix:**
   ```matlab
   restoredefaultpath
   cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')
   run test_legacy_pattern.m
   ```
