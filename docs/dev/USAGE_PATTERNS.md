# EpicTreeGUI Usage Pattern

The epicTreeGUI uses a **pre-built tree pattern** matching the legacy `epochTreeGUI` behavior.

## Pre-Built Tree Pattern

Build your tree structure in code before launching the GUI. This gives you full control over the hierarchy and supports custom splitter functions.

```matlab
% 1. Load data
[data, ~] = loadEpicTreeData('data.mat');

% 2. Build tree structure in code
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,        % Level 1
    @epicTreeTools.splitOnExperimentDate,  % Level 2
    'cellInfo.id',                        % Level 3
    @myCustomSplitter                      % Level 4
});

% 3. Launch GUI with pre-built tree
gui = epicTreeGUI(tree);
```

**Features:**
- Tree structure is **fixed** - no dropdown menu
- Full control over split hierarchy in code
- Supports custom splitter functions
- Supports mixing key paths ('cellInfo.type') and function handles (@epicTreeTools.splitOnCellType)
- Reproducible analysis workflows
- Matches legacy epochTreeGUI pattern exactly

---

## Why This Pattern?

This approach:
1. **Makes hierarchies explicit** - you see exactly how data is organized in your code
2. **Supports custom logic** - write any splitter function you need
3. **Matches legacy workflows** - drop-in replacement for old epochTreeGUI scripts
4. **Ensures reproducibility** - same code = same tree structure every time

---

## Comparison with Legacy Code

### Legacy Java Pattern:
```matlab
% Legacy epochTreeGUI (Java-based)
loader = edu.washington.rieke.Analysis.getEntityLoader();
list = loader.loadEpochList('data.mat', dataFolder);

dateSplit = @(list)splitOnExperimentDate(list);
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);

tree = riekesuite.analysis.buildTree(list, {
    'protocolSettings(source:type)',
    dateSplit_java,
    'cell.label',
    'protocolSettings(epochGroup:label)'
});

gui = epochTreeGUI(tree);  % GUI shows fixed structure
```

### New MATLAB Pattern:
```matlab
% New epicTreeGUI (pure MATLAB)
[data, ~] = loadEpicTreeData('data.mat');

tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    'cellInfo.type',                      % Was: protocolSettings(source:type)
    @epicTreeTools.splitOnExperimentDate, % Was: dateSplit_java
    'cellInfo.id',                        % Was: cell.label
    'parameters.epochGroup'               % Was: protocolSettings(epochGroup:label)
});

gui = epicTreeGUI(tree);  % GUI shows fixed structure
```

**Key differences:**
- No Java imports needed
- `loadEpicTreeData()` replaces `loader.loadEpochList()`
- `epicTreeTools` replaces `riekesuite.analysis.buildTree()`
- Static splitters like `@epicTreeTools.splitOnExperimentDate` replace Java adapters
- Field name mapping: `cellInfo.type` ≈ `protocolSettings(source:type)`

---

## Creating Custom Splitters

Both patterns support custom splitter functions:

```matlab
function value = myCustomSplitter(epoch)
    % Extract any value from the epoch struct
    % Use epicTreeTools.getNestedValue() for deep field access

    value = epicTreeTools.getNestedValue(epoch, 'parameters.myParam');

    % OR custom logic:
    if epoch.parameters.stimulus == 'flash'
        value = 'flash';
    else
        value = 'other';
    end

    % Return value can be: numeric, char, string, logical
end
```

Then use it in your tree:
```matlab
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @myCustomSplitter,              % Your custom splitter
    'cellInfo.id'
});
```

---

## Examples

See these test scripts for working examples:
- `tests/test_legacy_pattern.m` - Pre-built tree with 4-level hierarchy
- `tests/test_exact_legacy_pattern.m` - Matches legacy code exactly with 7-level hierarchy
