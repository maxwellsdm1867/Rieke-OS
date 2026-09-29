# Tree Utility Functions

This directory contains the core tree manipulation functions for EpicTreeGUI. These functions provide the same functionality as the legacy Java `jenkins-jauimodel-275.jar` but implemented in pure MATLAB.

## epicTreeTools Class (Recommended)

The `epicTreeTools` class packages all tree functionality into a single class:

```matlab
% Add to path
addpath('src/tree');

% Load data and create tree
data = loadEpicTreeData('experiment.mat');
tree = epicTreeTools(data);

% Build tree by cell type and contrast
tree.buildTree({'cellInfo.type', 'protocolSettings.contrast'});

% Navigate tree
onpNode = tree.childBySplitValue('OnP');
contrastNode = onpNode.childBySplitValue(0.5);

% Get epochs from leaf
epochs = contrastNode.epochList;

% Get all leaves at once
leaves = tree.leafNodes();
for i = 1:length(leaves)
    leaf = leaves{i};
    sv = leaf.splitValues();
    fprintf('Leaf %d: %d epochs\n', i, length(leaf.epochList));
end

% Static utility methods
resp = epicTreeTools.getResponseByName(epoch, 'Amp1');
[data, fs, spikes] = epicTreeTools.getResponseData(epoch, 'Amp1');
val = epicTreeTools.getNestedValue(epoch, 'protocolSettings.contrast');

% Using custom splitters (Phase 3)
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, ...
                             @epicTreeTools.splitOnF1F2Contrast});

% Mix key paths and splitter functions
tree.buildTreeWithSplitters({'cellInfo.type', ...
                             @epicTreeTools.splitOnF1F2Phase});
```

## Splitter Functions (Phase 3)

The epicTreeTools class includes static splitter methods for common analysis patterns. These can be used with `buildTreeWithSplitters()`:

### Basic Splitters

| Splitter | Description |
|----------|-------------|
| `splitOnExperimentDate(epoch)` | Split by experiment name/date |
| `splitOnCellType(epoch)` | Split by cell type (with keyword fallback) |
| `splitOnKeywords(epoch)` | Split by epoch keywords |
| `splitOnKeywordsExcluding(epoch, excludeList)` | Split by keywords, excluding specified |
| `splitOnProtocol(epoch)` | Split by protocol name |
| `splitOnEpochBlockStart(epoch)` | Split by block start time |

### Parameter Splitters

| Splitter | Description |
|----------|-------------|
| `splitOnContrast(epoch)` | Split by contrast parameter |
| `splitOnTemporalFrequency(epoch)` | Split by temporal frequency |
| `splitOnSpatialFrequency(epoch)` | Split by spatial frequency |
| `splitOnBarWidth(epoch)` | Split by bar width |
| `splitOnFlashDelay(epoch)` | Split by flash delay time |
| `splitOnStimulusCenter(epoch)` | Split by stimulus center offset |

### F1/F2 Analysis Splitters

| Splitter | Description |
|----------|-------------|
| `splitOnF1F2Contrast(epoch)` | Split by F1/F2 contrast (handles multiple protocols) |
| `splitOnF1F2CenterSize(epoch)` | Split by F1/F2 center size |
| `splitOnF1F2Phase(epoch)` | Split by F1/F2 phase (returns 'F1' or 'F2') |

### Recording/Equipment Splitters

| Splitter | Description |
|----------|-------------|
| `splitOnHoldingSignal(epoch)` | Split by holding/offset signal |
| `splitOnOLEDLevel(epoch)` | Split by OLED brightness level |
| `splitOnRecKeyword(epoch)` | Split by recording type (exc/inh/gClamp/etc.) |
| `splitOnLogIRtag(epoch)` | Split by log IR tag |
| `splitOnRadiusOrDiameter(epoch, param)` | Split by radius/diameter (handles Symphony 1→2) |

### Natural Image Analysis Splitters

| Splitter | Description |
|----------|-------------|
| `splitOnPatchContrast_NatImage(epoch)` | Split by natural image patch contrast |
| `splitOnPatchSampling_NatImage(epoch)` | Split by natural image patch sampling |

### Example: F1/F2 Analysis with Splitters

```matlab
% Load data
data = loadEpicTreeData('experiment.mat');
tree = epicTreeTools(data);

% Build tree for F1/F2 analysis
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, ...
                             @epicTreeTools.splitOnF1F2Contrast, ...
                             @epicTreeTools.splitOnF1F2Phase});

% Process leaves
leaves = tree.leafNodes();
for i = 1:length(leaves)
    leaf = leaves{i};
    sv = leaf.splitValues();
    fprintf('%s, contrast=%g, phase=%s: %d epochs\n', ...
        sv.splitOnCellType, sv.splitOnF1F2Contrast, ...
        sv.splitOnF1F2Phase, length(leaf.epochList));
end
```

## Standalone Functions (Alternative)

Individual functions are also available if you prefer:

## Function Reference

### Data Extraction

| Function | Description |
|----------|-------------|
| `getAllEpochs(treeData)` | Flatten hierarchical data into cell array of epochs |
| `getNestedValue(obj, keyPath)` | Access nested struct fields via dot notation |
| `getStreamNames(epochs, type)` | Get unique response/stimulus stream names |
| `getResponseByName(epoch, name)` | Get response struct by device name |
| `getStimulusByName(epoch, name)` | Get stimulus struct by device name |
| `getResponseData(epoch, name)` | Get response data, sample rate, spike times |

### Tree Building

| Function | Description |
|----------|-------------|
| `buildTreeByKeyPaths(epochs, keyPaths)` | Build hierarchical tree by grouping on key paths |
| `sortEpochsByKey(epochs, keyPath)` | Sort epochs by value at key path |

### Tree Navigation

| Function | Description |
|----------|-------------|
| `getChildBySplitValue(node, value)` | Find child node by split value |
| `getSplitValues(node)` | Get all split key-values from root to node |
| `getLeafNodes(node)` | Get all leaf nodes under a node |

## Common Key Paths

| Key Path | Description |
|----------|-------------|
| `cellInfo.type` | Cell type (OnP, OffP, OnM, etc.) |
| `cellInfo.id` | Cell ID |
| `cellInfo.label` | Cell label |
| `parameters.contrast` | Stimulus contrast |
| `parameters.temporal_frequency` | Temporal frequency |
| `parameters.spatial_frequency` | Spatial frequency |
| `groupInfo.protocol_name` | Protocol name |
| `blockInfo.protocol_name` | Block protocol |
| `expInfo.exp_name` | Experiment name |
| `id` | Epoch ID |

## TreeNode Structure

Nodes returned by `buildTreeByKeyPaths` have this structure:

```matlab
treeNode = struct(
    'splitKey',    '',      % Key path used for split (empty for root)
    'splitValue',  [],      % Value at this split
    'children',    {},      % Cell array of child nodes (empty for leaf)
    'epochList',   {},      % Cell array of epochs (only for leaf nodes)
    'isLeaf',      false,   % True if this is a leaf node
    'parent',      []       % Reference to parent node
);
```

## Example: Analysis Workflow

```matlab
% Load and prepare data
data = loadEpicTreeData('experiment.mat');
epochs = getAllEpochs(data);

% Build tree by cell type, then by contrast
tree = buildTreeByKeyPaths(epochs, {'cellInfo.type', 'parameters.contrast'});

% Process each leaf (each unique cell type + contrast combination)
leaves = getLeafNodes(tree);
results = cell(length(leaves), 1);

for i = 1:length(leaves)
    leaf = leaves{i};
    sv = getSplitValues(leaf);

    % Get epochs for this condition
    conditionEpochs = leaf.epochList;

    % Extract response data
    allResponses = [];
    for j = 1:length(conditionEpochs)
        [data, fs, spikes] = getResponseData(conditionEpochs{j}, 'Amp1');
        allResponses(j, :) = data;
    end

    % Compute mean response
    meanResp = mean(allResponses, 1);

    results{i} = struct(...
        'cellType', sv.cellInfo_type, ...
        'contrast', sv.parameters_contrast, ...
        'nEpochs', length(conditionEpochs), ...
        'meanResponse', meanResp);
end
```

## See Also

- [JAUIMODEL_FUNCTION_INVENTORY.md](../../JAUIMODEL_FUNCTION_INVENTORY.md) - Reference for Java equivalents
- [DATA_FORMAT_SPECIFICATION.md](../../DATA_FORMAT_SPECIFICATION.md) - Data format specification
