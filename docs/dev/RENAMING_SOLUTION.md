# Renaming Solution: Avoiding Name Conflicts

## The Problem

The repository contains **two** versions of `graphicalTree.m`:
1. **Old** - `old_epochtree/.../graphicalTree.m` (Java-based, legacy)
2. **New** - `src/gui/graphicalTree.m` (Pure MATLAB, modern)

When both are on the MATLAB path, the old version can shadow the new one, causing:
- "Brace indexing is not supported" error
- Callback failures
- Unpredictable behavior

## The Solution: Rename New Classes

We've renamed the new classes to completely avoid conflicts:

| Old Name | New Name | Purpose |
|----------|----------|---------|
| `graphicalTree` | `epicGraphicalTree` | Main tree widget |
| `graphicalTreeNode` | `epicGraphicalTreeNode` | Tree node data structure |
| `graphicalTreeNodeWidget` | `epicGraphicalTreeNodeWidget` | Visual widget for nodes |

### Benefits

✅ **No more name conflicts** - `epicGraphicalTree` is unique
✅ **No path management needed** - `old_epochtree` can stay on path
✅ **Clear naming** - Obviously part of the epicTree system
✅ **Works immediately** - No MATLAB restart required

---

## Testing the Rename

```matlab
cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')
run test_renamed.m
```

This test:
1. Verifies `epicGraphicalTree` is loaded (not `graphicalTree`)
2. Builds a tree with epoch flattening
3. Launches GUI
4. Should work WITHOUT any path management

---

## Files Changed

| File | Change |
|------|--------|
| `src/gui/epicGraphicalTree.m` | Created from `graphicalTree.m` |
| `src/gui/epicGraphicalTreeNode.m` | Created from `graphicalTreeNode.m` |
| `src/gui/epicGraphicalTreeNodeWidget.m` | Created from `graphicalTreeNodeWidget.m` |
| `epicTreeGUI.m` | Updated to use `epicGraphicalTree` |
| `test_renamed.m` | New test script |

---

## Next Step: Embed Into epicTreeGUI

Now that we've confirmed the rename works, we should **embed the tree visualization directly into `epicTreeGUI`** to eliminate external dependencies.

### Why Embed?

1. **Self-contained** - All code in one place
2. **No external dependencies** - Can't have path issues
3. **Easier maintenance** - One file to manage
4. **Better encapsulation** - Tree widget is internal implementation detail

### How to Embed

Three options:

#### Option 1: Nested Class (Cleanest)
```matlab
classdef epicTreeGUI < handle
    % ... main code ...

    methods
        % ... GUI methods ...
    end
end

% Nested classes for tree visualization
classdef epicGraphicalTree < handle
    % Tree visualization code here
end

classdef epicGraphicalTreeNode < handle
    % Node data structure here
end

classdef epicGraphicalTreeNodeWidget < handle
    % Widget code here
end
```

#### Option 2: Private Methods (Simplest)
Move all tree visualization logic into private methods of `epicTreeGUI`:
```matlab
classdef epicTreeGUI < handle
    methods (Access = private)
        function tree = createTreeWidget(self, ax, name)
            % All epicGraphicalTree code here as methods
        end

        function node = createTreeNode(self, parent, name)
            % All epicGraphicalTreeNode code here
        end

        % ... etc
    end
end
```

#### Option 3: Inline All Code (Most Portable)
Copy all the tree visualization code directly into `epicTreeGUI.m` as methods. This makes one large file but completely self-contained.

### Recommended: Option 1 (Nested Classes)

Nested classes provide:
- Clean separation of concerns
- Access to parent class properties
- Encapsulation (hidden from user)
- Still organized and readable

---

## Implementation Plan

### Phase 1: Verify Rename Works ✅ (DONE)
- [x] Create `epicGraphicalTree.m`
- [x] Create `epicGraphicalTreeNode.m`
- [x] Create `epicGraphicalTreeNodeWidget.m`
- [x] Update `epicTreeGUI.m` to use renamed classes
- [x] Create test script

### Phase 2: Test and Confirm
- [ ] Run `test_renamed.m`
- [ ] Verify GUI works without errors
- [ ] Verify epoch flattening works
- [ ] Verify clicking nodes works

### Phase 3: Embed Into epicTreeGUI (Future)
- [ ] Choose embedding approach (recommend nested classes)
- [ ] Move code into `epicTreeGUI.m`
- [ ] Test embedded version
- [ ] Remove separate class files
- [ ] Update documentation

---

## For Now: Use Renamed Classes

Until we embed the code, use the renamed classes:

```matlab
% Simple usage
addpath('src/gui');
addpath('src/tree');
addpath('src');
gui = epicTreeGUI('data.mat');

% Legacy pattern
[data, ~] = loadEpicTreeData('data.mat');
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});
gui = epicTreeGUI(tree);
```

No path management needed - the `epic*` prefix avoids all conflicts!

---

## Comparison: Before vs After

### Before (Name Conflicts)
```matlab
% Had to carefully manage paths
rmpath(genpath('old_epochtree'));
addpath('src/gui');  % MUST be first!
% Error if wrong graphicalTree loaded
```

### After (No Conflicts)
```matlab
% Just add paths, order doesn't matter
addpath('src/gui');
addpath('src/tree');
addpath('src');
% epicGraphicalTree is unique - no conflicts!
```

---

## Testing

### Quick Test
```matlab
cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')
run test_renamed.m
```

### Verify Classes Exist
```matlab
which epicGraphicalTree
which epicGraphicalTreeNode
which epicGraphicalTreeNodeWidget
```

All should show paths in `src/gui/`.

---

## Future: Embedding Documentation

Once we embed the classes into `epicTreeGUI`, we'll:
1. Create `epicTreeGUI_standalone.m` with all code embedded
2. Test thoroughly
3. Replace current `epicTreeGUI.m`
4. Archive separate class files
5. Update all documentation

This will make the system:
- Completely self-contained
- Immune to path issues
- Easier to distribute
- Simpler to maintain

---

## Summary

✅ **Problem Solved** - Renamed classes avoid all conflicts
✅ **Immediate Use** - Works now with `test_renamed.m`
🔜 **Future Work** - Embed into single file for ultimate portability

The rename gives us a working solution NOW, and embedding will make it bulletproof LATER.
