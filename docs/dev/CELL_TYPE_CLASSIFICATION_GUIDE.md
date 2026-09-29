# Cell Type Classification Guide

## Current Status

Your data currently has:
- All epochs labeled as generic `"RGC"` in `cellInfo.type`
- No keywords field
- No cell subtype classification (ON-parasol, OFF-parasol, etc.)

## Available Splitter: `splitOnCellType`

**Location:** `src/tree/epicTreeTools.m` lines 1559-1590

### Detection Methods (in priority order):

#### 1. Direct cellInfo.type (PREFERRED)
```matlab
epoch.cellInfo.type = 'RGC\ON-parasol'
% Splitter returns: 'RGC\ON-parasol'
```

#### 2. Keywords (fallback)
```matlab
epoch.keywords = {'onparasol', 'cell-attached'}
% Splitter returns: 'RGC\ON-parasol'
```

#### 3. Recognized Keywords
```
Keyword          → Cell Type Returned
──────────────────────────────────────
'onparasol'      → 'RGC\ON-parasol'
'offparasol'     → 'RGC\OFF-parasol'
'onmidget'       → 'RGC\ON-midget'
'offmidget'      → 'RGC\OFF-midget'
'horizontal'     → 'horizontal'
'onp'            → 'OnP'
'offp'           → 'OffP'
'onm'            → 'OnM'
'offm'           → 'OffM'
(no match)       → 'noCellTypeTag'
```

## How to Add Cell Type Information

### Option 1: Update Python Export Pipeline

In your data export script (e.g., `export_to_matlab.py`), add cell type classification:

```python
# During cell data processing
cell_data = {
    'cellInfo': {
        'id': cell_id,
        'label': cell_label,
        'type': classify_cell_type(cell_properties)  # ← Add this
    }
}

def classify_cell_type(props):
    """Classify cell based on properties"""

    # Option A: From database/metadata
    if 'cell_type' in props:
        return props['cell_type']  # e.g., 'RGC\ON-parasol'

    # Option B: From RF analysis
    if 'rf_center_diameter' in props:
        if props['rf_center_diameter'] > 200:  # microns
            cell_class = 'parasol'
        else:
            cell_class = 'midget'

        polarity = 'ON' if props.get('polarity') == 'on' else 'OFF'
        return f'RGC\\{polarity}-{cell_class}'

    # Option C: Generic
    return 'RGC'
```

### Option 2: Add Keywords

```python
# During epoch processing
epoch_data['keywords'] = []

if cell_type == 'on_parasol':
    epoch_data['keywords'].append('onparasol')
elif cell_type == 'off_parasol':
    epoch_data['keywords'].append('offparasol')

# Add other metadata
if recording_mode == 'cell_attached':
    epoch_data['keywords'].append('cell-attached')
```

### Option 3: Post-Process Existing MAT File

If you already have a .mat file, enhance it in MATLAB:

```matlab
% Load existing data
load('data.mat', 'export_data');

% Function to classify cells based on your criteria
function cellType = classifyCellFromData(cell_data)
    % Your classification logic here
    % Could use:
    % - RF center size
    % - Response kinetics
    % - Spike waveform
    % - Dendritic field size
    % - Manual labels from experimenter notes

    % Example: Simple classification
    if cell_data.rf_center_diameter > 200
        if cell_data.on_response > cell_data.off_response
            cellType = 'RGC\ON-parasol';
        else
            cellType = 'RGC\OFF-parasol';
        end
    else
        if cell_data.on_response > cell_data.off_response
            cellType = 'RGC\ON-midget';
        else
            cellType = 'RGC\OFF-midget';
        end
    end
end

% Process each cell
for exp_idx = 1:length(export_data.experiments)
    exp = export_data.experiments(exp_idx);
    for cell_idx = 1:length(exp.cells)
        cell = exp.cells(cell_idx);

        % Classify cell
        cellType = classifyCellFromData(cell);

        % Update all epochs from this cell
        for grp_idx = 1:length(cell.epoch_groups)
            for blk_idx = 1:length(cell.epoch_groups(grp_idx).epoch_blocks)
                for ep_idx = 1:length(cell.epoch_groups(grp_idx).epoch_blocks(blk_idx).epochs)
                    % Update cell type
                    export_data.experiments(exp_idx).cells(cell_idx) ...
                        .epoch_groups(grp_idx).epoch_blocks(blk_idx) ...
                        .epochs(ep_idx).cellInfo.type = cellType;
                end
            end
        end
    end
end

% Save enhanced file
save('data_with_cell_types.mat', 'export_data', '-v7.3');
```

## Custom Splitter: `splitOnRGCSubtype`

A custom splitter has been created at `src/splitters/splitOnRGCSubtype.m` that can:
1. Use cellInfo.type if specific
2. Parse keywords
3. Infer type from RF analysis results
4. Infer type from response properties

**Usage:**
```matlab
tree.buildTreeWithSplitters({
    @splitOnRGCSubtype,  % Custom RGC subtype classifier
    'cellInfo.id'
});
```

## Classification Strategies

### Based on RF Properties
```
Center Diameter > 200 μm → Parasol
Center Diameter < 200 μm → Midget

ON response > OFF response → ON-type
OFF response > ON response → OFF-type
```

### Based on Response Kinetics
```
Transient peak, fast decay → Parasol
Sustained response → Midget
```

### Based on Dendritic Field
```
Large dendritic field (>300 μm) → Parasol
Small dendritic field (<150 μm) → Midget
```

### Manual Classification
If you have experimenter notes or manual labels:
```python
# In export script
manual_labels = load_experimenter_notes('experiment.txt')
cell_data['type'] = manual_labels.get(cell_id, 'RGC')
```

## Testing Your Classification

After adding cell types:

```matlab
% Load enhanced data
[data, ~] = loadEpicTreeData('data_with_cell_types.mat');

% Build tree by cell type
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});

% See what types were found
fprintf('Cell types found:\n');
for i = 1:tree.childrenLength()
    node = tree.childAt(i);
    fprintf('  %s: %d epochs\n', char(node.splitValue), node.epochCount());
end

% Launch GUI
gui = epicTreeGUI(tree);
```

Expected output:
```
Cell types found:
  RGC\ON-parasol: 512 epochs
  RGC\OFF-parasol: 438 epochs
  RGC\ON-midget: 287 epochs
  RGC\OFF-midget: 315 epochs
  horizontal: 42 epochs
```

## Next Steps

1. **Decide classification method** - RF properties? Manual labels? Response kinetics?
2. **Update export pipeline** - Add cell type info during export
3. **Re-export data** - Generate new .mat file with cell types
4. **Test** - Build tree and verify cell types appear correctly
5. **Analyze** - Use `getSelectedData()` on cell type nodes for subtype-specific analysis

## See Also

- `src/tree/epicTreeTools.m` - Main splitter implementation
- `src/splitters/splitOnRGCSubtype.m` - Custom RGC classifier
- `DATA_FORMAT_SPECIFICATION.md` - Expected data format
- `CLAUDE.md` - Usage examples
