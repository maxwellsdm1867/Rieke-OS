# Quick Start Guide

## If You're Getting Errors When Clicking Tree Nodes

### The Error Looks Like:
```
Brace indexing is not supported for variables of this type.
Error in graphicalTree/fireNodesSelectedFcn (line 381)
```

### The Fix:
```matlab
cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')
run fix_now.m
```

**See `FIX_BRACE_INDEXING_ERROR.md` for detailed troubleshooting.**

---

## Fresh Start (Recommended First Time)

If this is your first time using the new epicTreeGUI:

```matlab
% 1. Navigate to project
cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')

% 2. Run launcher (this sets up paths correctly)
launch_epic_tree

% 3. Test the GUI
run test_epoch_display.m
```

---

## Usage Patterns

### Pattern 1: Pre-Built Tree (Recommended for Analysis)

Build the tree structure in code, then launch GUI:

```matlab
% Setup
launch_epic_tree

% Load data
[data, ~] = loadEpicTreeData('data.mat');

% Build tree with specific hierarchy
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});

% Launch GUI - tree is fixed, no dropdown
gui = epicTreeGUI(tree);
```

**What you get:**
- Tree structure defined in code
- Individual epochs shown at leaf level with pink backgrounds
- Click epoch → single trace
- Click protocol → all epochs aggregated

### Pattern 2: Simple File Loading (Quick Exploration)

```matlab
launch_epic_tree
gui = epicTreeGUI('data.mat');
```

**What you get:**
- Dropdown menu to change splits dynamically
- Good for initial exploration

---

## Test Scripts

| Script | Purpose |
|--------|---------|
| `test_epoch_display.m` | Test individual epoch flattening at leaf level |
| `test_legacy_pattern.m` | Test pre-built tree pattern |
| `test_exact_legacy_pattern.m` | Exact match of legacy code |
| `check_paths.m` | Diagnose path issues |
| `fix_now.m` | Emergency fix for path errors |
| `launch_epic_tree.m` | Safe launcher with path setup |

---

## Tree Building Examples

### Simple Two-Level Tree
```matlab
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});
```

Result:
```
RGC (1915)
├─ SingleSpot (7)
│  ├─   1: 2025-12-02 10:15:30    ← Individual epochs
│  ├─   2: 2025-12-02 10:16:45
│  └─ ...
├─ ExpandingSpots (255)
└─ VariableMeanNoise (1640)
```

### Complex Multi-Level Tree
```matlab
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnExperimentDate,
    'cellInfo.id',
    @epicTreeTools.splitOnProtocol
});
```

Result:
```
RGC (1915)
└─ 2025-12-02_F (1915)
   └─ cellInfo.id = 1 (1915)
      ├─ SingleSpot (7)
      │  ├─   1: 2025-12-02 10:15:30
      │  └─ ...
      └─ ExpandingSpots (255)
```

---

## Common Splitters

| Splitter | Splits By |
|----------|-----------|
| `@epicTreeTools.splitOnCellType` | Cell type (RGC, BC, etc.) |
| `@epicTreeTools.splitOnExperimentDate` | Experiment date |
| `@epicTreeTools.splitOnProtocol` | Protocol name |
| `'cellInfo.id'` | Cell ID number |
| `'parameters.contrast'` | Contrast parameter |
| `'parameters.temporalFrequency'` | Temporal frequency |

**See `src/splitters/` for all available splitters.**

---

## Workflow: Typical Analysis Session

```matlab
% 1. Start session
cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')
launch_epic_tree

% 2. Load data
[data, ~] = loadEpicTreeData('my_experiment.mat');
fprintf('Loaded %d epochs\n', length(data));

% 3. Build tree (customize this for your analysis)
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});

% 4. Launch GUI
gui = epicTreeGUI(tree);

% 5. Use GUI to:
%    - Navigate tree
%    - Select epochs of interest (checkboxes)
%    - View single epoch responses
%    - Export selected epochs (File > Export Selection)

% 6. Get selected data for analysis
selectedEpochs = gui.getSelectedEpochs();
fprintf('Selected %d epochs for analysis\n', length(selectedEpochs));

% 7. Run analysis (example)
[data, epochs, fs] = getSelectedData(selectedEpochs, 'Amp1');
meanResponse = mean(data, 1);
plot((1:length(meanResponse))/fs*1000, meanResponse);
xlabel('Time (ms)'); ylabel('Response');
```

---

## Tips

### Click Behavior
- **Click tree node** (white background) → Shows aggregated data
- **Click epoch** (pink background) → Shows single epoch

### Selection (Checkboxes)
- Check tree node → Selects all child epochs
- Check individual epoch → Selects just that epoch
- Use for filtering before analysis

### Keyboard Shortcuts
- `↑/↓` - Navigate tree
- `←/→` - Collapse/expand nodes
- `F` or `Space` - Toggle selection

### Hide Individual Epochs
If tree is too cluttered:
```matlab
gui = epicTreeGUI(tree, 'noEpochs');
```

---

## Documentation

| File | Purpose |
|------|---------|
| `USAGE_PATTERNS.md` | Detailed usage patterns |
| `EPOCH_FLATTENING.md` | Technical details on epoch display |
| `FIX_BRACE_INDEXING_ERROR.md` | Troubleshooting guide |
| `BUGFIX_TREE_GUI.md` | Bug fix history |
| `CLAUDE.md` | Full project documentation |

---

## Getting Help

1. **Path issues** → Read `FIX_BRACE_INDEXING_ERROR.md`
2. **How to build trees** → Read `USAGE_PATTERNS.md`
3. **Understanding epoch display** → Read `EPOCH_FLATTENING.md`
4. **General questions** → Read `CLAUDE.md`
