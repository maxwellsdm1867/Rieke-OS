# Epoch Flattening Implementation

This document explains how individual epochs are displayed at the leaf level of the tree, matching the legacy `epochTreeGUI` behavior.

## Overview

In the legacy system, when you navigate down the tree hierarchy to a leaf node (e.g., a specific protocol), the tree **flattens out individual epochs** as separate child nodes. Each epoch becomes a clickable node with:
- Pink background color
- Sequential number and timestamp
- Its own checkbox for selection
- Direct access to single-epoch data

## Implementation

### 1. Tree Building (epicTreeGUI.m:408-433)

The `marryEpochNodesToWidgets()` method now has three cases:

```matlab
if ~epochNode.isLeaf
    % Internal node - recurse on children
    for ii = 1:length(epochNode.children)
        childEpoch = epochNode.children{ii};
        childBrowser = gTree.newNode(browserNode, '');
        self.marryEpochNodesToWidgets(childEpoch, childBrowser);
    end
elseif self.showEpochs && ~isempty(epochNode.epochList)
    % Leaf node - create individual epoch widgets
    epochs = epochNode.epochList;
    for ii = 1:length(epochs)
        ep = epochs{ii};
        epochWidget = gTree.newNode(browserNode, '');
        epochWidget.userData = ep;  % Store epoch struct directly
        epochWidget.isChecked = ep.isSelected;
        epochWidget.name = self.formatEpochName(ii, ep);
        epochWidget.textBackgroundColor = [1 .85 .85];  % Pink
    end
end
```

**Key Points:**
- When `epochNode.isLeaf == true` and `showEpochs == true`, create individual widgets
- Each epoch widget stores the epoch **struct** in `userData` (not an `epicTreeTools` node)
- Pink background `[1 .85 .85]` visually distinguishes epochs from tree nodes

### 2. Epoch Name Formatting (epicTreeGUI.m:771-790)

```matlab
function name = formatEpochName(~, index, epoch)
    % Legacy format: "#N: YYYY-MM-DD HH:MM:SS"
    if isfield(epoch, 'expInfo') && isfield(epoch.expInfo, 'date')
        dateStr = epoch.expInfo.date;
    elseif isfield(epoch, 'startTime')
        dateStr = epoch.startTime;
    else
        dateStr = '';
    end

    if ~isempty(dateStr)
        name = sprintf('%3d: %s', index, dateStr);
    else
        name = sprintf('%3d', index);
    end
end
```

**Example Output:**
```
  1: 2025-12-02 10:15:30
  2: 2025-12-02 10:16:45
  3: 2025-12-02 10:18:12
```

### 3. Click Behavior (epicTreeGUI.m:453-476)

The selection handler now differentiates between tree nodes and epoch nodes:

```matlab
function onTreeSelectionChanged(self, ~)
    graphNodes = self.treeBrowser.graphTree.getSelectedNodes();
    userData = graphNodes{1}.userData;

    if isa(userData, 'epicTreeTools')
        % Tree node - display aggregated data
        self.updateInfoTable(userData);
        self.plotNodeData(userData);
    elseif isstruct(userData)
        % Individual epoch - display single epoch
        self.updateInfoTableForEpoch(userData);
        self.plotSingleEpoch(userData);
    end
end
```

**Behavior:**
- **Click tree node** (e.g., "SingleSpot (7)") → Shows all 7 epochs aggregated
- **Click epoch node** (e.g., "  1: 2025-12-02 10:15:30") → Shows just that single epoch

### 4. Info Table Display

**For Tree Nodes:**
```
Property    Value
Node        protocolID
Value       SingleSpot
Epochs      7
Selected    7
```

**For Individual Epochs:**
```
Property    Value
Type        Single Epoch
Date        2025-12-02 10:15:30
Protocol    SingleSpot
Selected    true
```

### 5. Data Plotting

**Tree Node (epicTreeGUI.m:656-677):**
- Plots all epochs as gray traces
- Overlays mean trace in black
- Shows epoch count in title

**Individual Epoch (epicTreeGUI.m:679-719):**
- Plots single trace in blue
- Shows device name (e.g., "Amp1")
- Title: "Single Epoch"

### 6. Selection Syncing (epicTreeGUI.m:514-533)

Checkbox changes update the appropriate data structure:

```matlab
function onTreeCheckChanged(self, ~)
    for ii = 1:length(gTree.nodeList)
        gNode = gTree.nodeList{ii};
        if isa(gNode.userData, 'epicTreeTools')
            % Tree node - update custom flag
            gNode.userData.custom.isSelected = gNode.isChecked;
        elseif isstruct(gNode.userData)
            % Individual epoch - update isSelected field
            gNode.userData.isSelected = gNode.isChecked;
        end
    end
end
```

## Visual Hierarchy

```
RGC (1915)                          ← Tree node, white background
├─ SingleSpot (7)                   ← Tree node, white background
│  ├─   1: 2025-12-02 10:15:30     ← Epoch, PINK background
│  ├─   2: 2025-12-02 10:16:45     ← Epoch, PINK background
│  ├─   3: 2025-12-02 10:18:12     ← Epoch, PINK background
│  ├─   4: 2025-12-02 10:19:05     ← Epoch, PINK background
│  ├─   5: 2025-12-02 10:20:33     ← Epoch, PINK background
│  ├─   6: 2025-12-02 10:21:47     ← Epoch, PINK background
│  └─   7: 2025-12-02 10:23:19     ← Epoch, PINK background
├─ ExpandingSpots (255)
└─ VariableMeanNoise (1640)
```

## Usage Example

```matlab
% Build tree that ends at protocol level
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
    % No more splits - epochs will be shown as children
});

% Launch GUI - individual epochs will appear at leaf level
gui = epicTreeGUI(tree);
```

**User interaction:**
1. Expand "RGC" node
2. Expand "SingleSpot" node
3. See 7 pink epoch nodes
4. Click "  1: 2025-12-02 10:15:30" → Single epoch trace displayed
5. Click "SingleSpot (7)" → All 7 epochs overlaid + mean trace

## Disabling Epoch Display

If you want to hide individual epochs (show only tree nodes):

```matlab
gui = epicTreeGUI(data, 'noEpochs');
```

This sets `gui.showEpochs = false`, preventing epoch flattening.

## Comparison with Legacy

| Feature | Legacy (Java) | New (MATLAB) |
|---------|---------------|--------------|
| Epoch display | Pink nodes at leaf level | Pink nodes at leaf level ✓ |
| Name format | `"#N: date/time"` | `"#N: date/time"` ✓ |
| Click epoch | Single epoch viewer | Single epoch trace ✓ |
| Click parent | Aggregated viewer | Aggregated traces ✓ |
| Checkbox sync | Updates `epoch.isSelected` | Updates `epoch.isSelected` ✓ |
| Background color | `[1 .85 .85]` | `[1 .85 .85]` ✓ |

## Testing

Run the demonstration script:

```matlab
run test_epoch_display.m
```

This builds a two-level tree (Cell Type → Protocol) and shows individual epochs at the protocol level.

**Expected GUI appearance:**
- Tree nodes: white background, bold epoch counts
- Individual epochs: pink background, sequential numbering
- Clicking epochs vs nodes shows different data

## Technical Notes

### Why This Pattern?

The epoch flattening pattern serves several purposes:

1. **Visual clarity** - Easy to see how many epochs are in each condition
2. **Individual selection** - Can check/uncheck specific epochs
3. **Quick inspection** - Click any epoch to see its data
4. **Aggregate analysis** - Click parent to analyze all epochs together

### UserData Types

The `graphicalTreeNode.userData` field contains different types:

- **epicTreeTools object** → Tree node (internal or leaf)
- **Struct** → Individual epoch

This dual type system allows the same tree widget to display both hierarchy levels and individual data points.

### Memory Considerations

For large datasets (>1000 epochs), displaying all epochs as individual nodes can:
- Slow down tree rendering
- Increase memory usage
- Make scrolling sluggish

**Solutions:**
1. Use deeper tree hierarchies (more split levels)
2. Use `'noEpochs'` option to hide individual epochs
3. Add pagination or lazy loading (future enhancement)

## Files Modified

| File | Changes |
|------|---------|
| `epicTreeGUI.m` | Added epoch flattening logic in `marryEpochNodesToWidgets` |
| `epicTreeGUI.m` | Added `formatEpochName()` helper method |
| `epicTreeGUI.m` | Added `updateInfoTableForEpoch()` method |
| `epicTreeGUI.m` | Added `plotSingleEpoch()` method |
| `epicTreeGUI.m` | Modified `onTreeSelectionChanged()` to detect epoch vs node |
| `epicTreeGUI.m` | Modified `onTreeCheckChanged()` to handle both types |
| `test_epoch_display.m` | New test script demonstrating epoch flattening |

## Future Enhancements

Potential improvements to match legacy behavior even more closely:

1. **Multi-device subplot display** - Show Amp1, Amp2, etc. in separate subplots for single epochs
2. **Epoch slider** - Navigate between epochs using a slider widget
3. **Stimulus overlay** - Plot stimulus waveform below response
4. **Epoch capsule system** - Wrap single epochs in temporary trees for isolated analysis
5. **Keyboard shortcuts** - Arrow keys to step through epochs
