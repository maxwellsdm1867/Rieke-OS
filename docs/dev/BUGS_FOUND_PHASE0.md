# Bugs Found During Phase 0 Testing

**Date:** 2026-02-08
**Testing Phase:** Phase 0 - Testing & Validation
**Test Results:** 88/169 passing (52.1%)

## Critical Bugs

### BUG-001: Selection State Not Persisting/Propagating 🔴 CRITICAL

**Priority:** P0 - Blocks core functionality
**Component:** Tree selection system (`epicTreeTools.m`, selection state management)
**Discovered In:** `tests/integration/WorkflowTest.m::testSelectionFilteredWorkflow`

#### Symptom
When user deselects epochs in the tree, the selection state is not respected by data extraction functions. All epochs are still returned even when only selected epochs are requested.

#### Evidence
```matlab
% Test workflow:
tree = epicTreeTools(data);
tree.buildTree('cellInfo.type');
leafNode = tree.leafNodes(){1};

% Deselect half the epochs (should leave 958 selected)
totalEpochs = leafNode.epochCount();  % Returns 1915
halfCount = floor(totalEpochs / 2);
epochs = leafNode.getAllEpochs(false);
for i = 1:halfCount
    epochs{i}.isSelected = false;  % Manually deselect
end

% CHECK 1: selectedCount() reports correctly
selectedCount = leafNode.selectedCount();  % Returns 958 ✓ CORRECT

% CHECK 2: But getAllEpochs(true) ignores it!
selectedEpochs = leafNode.getAllEpochs(true);
length(selectedEpochs)  % Returns 1915 ✗ WRONG - should be 958

% CHECK 3: getSelectedData also returns all epochs
[data, epochs, fs] = getSelectedData(leafNode, 'Amp1');
size(data, 1)  % Returns 1915 rows ✗ WRONG - should be 958
```

#### Root Cause Analysis Needed

**Hypothesis 1: isSelected field not being checked**
- `getAllEpochs(onlySelected=true)` might not filter by `isSelected` field
- Need to verify the filtering logic in epicTreeTools.m

**Hypothesis 2: Selection state stored elsewhere**
- `isSelected` might be stored in a separate structure (parallel array, map)
- Direct modification of `epochs{i}.isSelected` doesn't update the "real" state
- `selectedCount()` reads from one location, `getAllEpochs()` from another

**Hypothesis 3: Tree structure vs epoch structure disconnect**
- Selection might be tracked at the tree node level, not epoch level
- Setting `isSelected` on epoch structs doesn't update node-level tracking
- Tree nodes might maintain separate selection indices/masks

#### Architectural Questions

1. **Where should selection state live?**
   - Option A: On individual epoch structs (`epoch.isSelected`)
   - Option B: On tree nodes (node maintains list/mask of selected indices)
   - Option C: Separate selection manager (side file/structure)

2. **How should it propagate?**
   - When parent node is deselected, should all children auto-deselect?
   - When all children deselected, should parent auto-deselect?
   - How to handle partial selection (some children selected)?

3. **How should it persist?**
   - Should selection state save to disk between sessions?
   - Should it be part of tree serialization?
   - Should it be a separate `.selection` file alongside tree?

#### Suggested Architecture (for discussion)

```
epicTreeTools (tree structure)
    ├── allEpochs (master list of all epochs)
    ├── selectionMask (boolean array, 1:1 with allEpochs)
    │   - Updated by setSelected()
    │   - Queried by getAllEpochs(onlySelected=true)
    │   - Persisted in .mat file or separate .selection file
    │
    ├── Tree hierarchy (nodes)
    │   ├── Each node has indices into allEpochs
    │   ├── Node.epochIndices = [1, 5, 7, ...]
    │   └── Node.getSelectedIndices() uses selectionMask(epochIndices)
    │
    └── Methods:
        ├── setSelected(indices, state) - updates selectionMask
        ├── getSelected() - returns indices where selectionMask==true
        ├── getAllEpochs(onlySelected) - filters by selectionMask
        └── saveSelection(filename) - persist to side file
```

**Benefits of centralized selection mask:**
- Single source of truth
- Fast bulk operations (vectorized)
- Easy to save/load selection state
- No synchronization issues between nodes

**Side file approach:**
```
mydata.mat          # Original data
mydata.tree         # Built tree structure (optional cache)
mydata.selection    # Selection state (indices or mask)
```

#### Impact
- **User workflow broken:** Cannot filter data by selection
- **Analysis invalid:** All analyses include unwanted epochs
- **Test suite:** 4+ integration tests failing
- **Trust issue:** Users think they're analyzing subset, actually analyzing everything

#### Reproduction Steps
1. Load data and build tree
2. Navigate to any leaf node
3. Deselect some epochs using `setSelected(false)` or GUI checkboxes
4. Call `getAllEpochs(true)` or `getSelectedData()`
5. Observe: All epochs returned, not just selected ones

#### Files Involved
- `src/tree/epicTreeTools.m` - Tree class with selection methods
- `src/getSelectedData.m` - Data extraction respecting selection
- `src/getResponseMatrix.m` - Low-level data extraction
- `epicTreeGUI.m` - GUI checkbox interaction

---

## Major Bugs

### BUG-002: Test Data Missing Expected Response Streams 🟡 MAJOR

**Priority:** P1 - Blocks test validation
**Component:** Test data or test design
**Discovered In:** Multiple test classes

#### Symptom
```
Warning: Response stream "Amp1" not found in first epoch
```

All tests hardcoded to extract "Amp1" stream, but test data file (`2025-12-02_F.mat`) doesn't contain this stream name.

#### Evidence
- 40+ tests fail with empty data matrices
- Analysis function baselines generated with NaN values
- Cannot validate that analysis functions produce correct results

#### Impact
- Cannot verify analysis functions work correctly
- Test coverage appears to exist but isn't actually testing anything
- Baselines are invalid (all NaN)

#### Possible Fixes

**Option 1: Fix test data**
- Add "Amp1" stream to test data file
- Ensure it matches expected format

**Option 2: Auto-detect streams**
```matlab
% Instead of hardcoded:
[data, epochs, fs] = getSelectedData(node, 'Amp1');

% Do this:
availableStreams = unique({epochs{1}.responses.device_name});
streamToUse = availableStreams{1};  % Use first available
[data, epochs, fs] = getSelectedData(node, streamToUse);
```

**Option 3: Make tests data-aware**
```matlab
function testCase = setupOnce(testCase)
    testCase.AvailableStreams = getAvailableStreams(testCase.TestData);
    testCase.StreamName = testCase.AvailableStreams{1};
end
```

#### Files Involved
- Test data: `/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat`
- All test classes that call `getSelectedData(node, 'Amp1')`

---

### BUG-003: GUI API Changed, Tests Outdated 🟡 MAJOR

**Priority:** P2 - GUI tests broken (if needed)
**Component:** GUI test suite vs actual GUI implementation
**Discovered In:** `tests/gui/GUIInteractionTest.m` (all 22 tests)

#### Symptom
```
Unrecognized method, property, or field 'graphicalTree' for class 'epicTreeGUI'
```

Tests expect `gui.graphicalTree` property that doesn't exist in current `epicTreeGUI` class.

#### Impact
- All 22 GUI interaction tests error immediately
- Cannot validate GUI functionality programmatically
- Unknown what the correct API actually is

#### Investigation Needed
1. Read current `epicTreeGUI.m` to understand actual API
2. Determine how to access tree display from outside
3. Update all GUI tests to match current API

#### Files Involved
- `epicTreeGUI.m` - Actual GUI implementation
- `tests/gui/GUIInteractionTest.m` - Outdated test suite
- `tests/helpers/TreeNavigationUtility.m` - GUI interaction helper

---

## Test Summary

### Passing Tests (88 tests, 52.1%)
✓ Tree navigation (30 tests) - Core navigation works
✓ Basic workflows (4 tests) - Load → build → analyze pipeline works
✓ Splitter functions (7 tests) - Returns values, no crashes
✓ Data structure validation (20+ tests) - Types, dimensions correct

### Failing Tests (44 tests, 26.0%)
✗ Selection filtering (4 tests) - BUG-001
✗ Analysis with data (8 tests) - BUG-002 (missing streams)
✗ Data extraction edge cases (5 tests) - BUG-002
✗ GUI interaction (22 tests) - BUG-003
✗ Baseline comparisons (2 tests) - Invalid baselines from BUG-002
✗ Some splitter edge cases (3 tests) - Missing data fields

### Skipped Tests (37 tests, 21.9%)
○ H5 data tests (20+ tests) - Expected, H5 file exists but no h5_dir configured
○ Some analysis tests (10+ tests) - Filtered by assumption when data unavailable

---

## Next Steps

### Immediate (Phase 0 completion)
1. ✅ Document bugs (this file)
2. 🔲 Decide on selection state architecture
3. 🔲 Commit bug report to repo

### Before Phase 1
**Decision needed:** Fix bugs now vs document and defer?

**Option A: Fix BUG-001 now** (recommended)
- Selection filtering is CRITICAL functionality
- Will take 1-2 hours to diagnose and fix
- Tests will validate the fix works

**Option B: Document and defer**
- Add to TESTING_REPORT.md
- Create GitHub issues
- Fix during Phase 1 or maintenance phase

**Option C: Partial fix**
- Fix BUG-001 (critical)
- Defer BUG-002 and BUG-003 (test infrastructure)

---

## Discussion Points

### Selection State Management Strategy

**Current Questions:**
1. Where is `isSelected` currently stored? (epoch struct vs tree metadata)
2. How does `setSelected()` currently work?
3. Why does `selectedCount()` work but `getAllEpochs(true)` doesn't?

**Proposed Solution:**
- Centralized selection mask in epicTreeTools root
- Side file for persistence (`.selection` file alongside `.mat`)
- Clear API: `saveSelection()`, `loadSelection()`, `getSelectionMask()`

**Benefits:**
- Single source of truth
- Fast filtering (vectorized logical indexing)
- Easy persistence between sessions
- Compatible with GUI checkbox system

**Implementation Plan:**
1. Add `selectionMask` property to epicTreeTools
2. Initialize to `true(numEpochs, 1)` on tree build
3. Update `setSelected()` to modify mask
4. Update `getAllEpochs()` to filter by mask
5. Add persistence methods
6. Update GUI to use centralized mask

---

## Questions for User

1. **Selection architecture:** Do you want centralized mask approach or keep per-epoch flags?
2. **Side files:** Should selection state persist to `.selection` file or embedded in tree?
3. **Fix timing:** Fix BUG-001 now before Phase 1, or defer to later?
4. **GUI tests:** Important to fix, or acceptable to skip for v1.0?

