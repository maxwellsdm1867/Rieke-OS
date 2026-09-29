# EpicTreeGUI - Basic Display & Splitter System

## What Was Just Built

Based on the TRD specifications, we've implemented the core tree browser functionality:

### 1. Display System (`src/displayNodeData.m`)
Visual data viewer that shows:
- **Spike rasters** - Individual spike times plotted by trial
- **PSTH plots** - Peri-stimulus time histograms with Gaussian smoothing
- **Parameter displays** - Stimulus parameters for each epoch
- **Summary views** - Text summaries for cells, blocks, groups, experiments

Handles different node types automatically and adapts display accordingly.

### 2. Tree Splitter System (`src/splitters/`)
Dynamic tree reorganization that groups data by:
- **Cell Type** (`splitOnCellType.m`) - Groups all cells by retinal type (OnP, OffP, etc.)
- **Any Parameter** (`splitOnParameter.m`) - Groups epochs by any stimulus parameter (contrast, size, temporal frequency, etc.)

Each splitter:
- Traverses entire dataset
- Extracts grouping values
- Creates child nodes for unique values
- Preserves full data hierarchy

### 3. GUI Integration (`epicTreeGUI.m` updates)
- **Split dropdown menu** - Select organization method
- **Visual plot panel** - Replaced text area with axes for plots
- **Rebuild system** (`rebuildTreeWithSplit.m`) - Dynamically reorganizes tree
- **Path management** - Automatically adds required directories

## How to Use

### Launch GUI
```matlab
cd /Users/maxwellsdm/Documents/GitHub/epicTreeGUI
test_launch
```

### Load Data
1. Click **File → Load Data**
2. Select your .mat file
3. Tree displays with default hierarchical organization

### Reorganize Tree
Use the **"Split by"** dropdown to choose:
- **None** - Default hierarchy (Exp → Cell → Group → Block → Epoch)
- **Cell Type** - Group by retinal cell type
- **Contrast** - Group epochs by contrast value
- **Size** - Group by stimulus size
- **Temporal Frequency** - Group by temporal frequency

Tree automatically rebuilds with new organization!

### View Data
Click any tree node to see:
- Spike raster plot (top)
- PSTH with smoothing (bottom)
- Stimulus parameters

## Architecture

```
epicTreeGUI/
├── epicTreeGUI.m              # Main GUI (updated)
├── test_launch.m              # Quick launcher
├── src/
│   ├── loadEpicTreeData.m     # Data loader (existing)
│   ├── buildTreeFromEpicData.m # Default tree builder (existing)
│   ├── formatEpicNodeData.m   # Text formatter (existing)
│   ├── displayNodeData.m      # NEW: Visual display system
│   ├── rebuildTreeWithSplit.m # NEW: Dynamic tree rebuilder
│   └── splitters/             # NEW: Splitter functions
│       ├── splitOnCellType.m
│       └── splitOnParameter.m
```

## What This Enables

### From TRD Requirements (Section 3):
✅ **Tree Browser** - Interactive navigation with expand/collapse  
✅ **Dynamic Organization** - Split by cell type or parameters  
✅ **Data Viewer** - Visual plots (spike rasters, PSTH)  
✅ **Hierarchical Display** - Shows full experiment structure  

### Still To Build (Future):
- Checkbox system for epoch selection
- Analysis functions (RFAnalysis, LSTA, etc.)
- MeanSelectedNodes for comparisons
- Additional splitters (date, holding potential, etc.)
- Export/save functionality
- Advanced plot options

## Technical Details

### Splitter System Design
Splitters are **pure functions** that take:
- `parent` - Tree node to split
- `data` - Full dataset
- `paramName` - (optional) Parameter to split on

And return:
- Array of child nodes organized by grouping criteria

This makes splitters:
- **Composable** - Can chain multiple splits
- **Extensible** - Easy to add new splitters
- **Testable** - Pure functions with clear inputs/outputs

### Display System Design
Uses MATLAB's subplot system to create:
- Top panel: Spike raster
- Bottom panel: PSTH with Gaussian smoothing

Automatically handles:
- Single vs. multiple trials
- Empty spike trains
- Missing data fields

## Next Steps

To continue building per TRD:
1. Add more splitters (date, keywords, etc.)
2. Implement analysis functions
3. Add checkbox selection system
4. Build MeanSelectedNodes overlay tool
5. Add RF mosaic visualization
6. Implement data export utilities

See [trd](../trd) for full specifications.
