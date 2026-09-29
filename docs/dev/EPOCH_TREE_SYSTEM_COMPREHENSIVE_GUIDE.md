# Epoch Tree System - Comprehensive Technical Guide

## Overview

This document provides a complete technical understanding of the Rieke Lab Epoch Tree system, derived from analyzing the actual working code in `old_epochtree/`. This guide explains how the system works end-to-end, from data loading to visualization and analysis.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Data Flow Pipeline](#2-data-flow-pipeline)
3. [Core Components Detailed](#3-core-components-detailed)
4. [Tree Building Process](#4-tree-building-process)
5. [Splitter Functions](#5-splitter-functions)
6. [GUI System](#6-gui-system)
7. [Data Access Patterns](#7-data-access-patterns)
8. [Analysis Workflow Examples](#8-analysis-workflow-examples)
9. [Critical Functions Reference](#9-critical-functions-reference)
10. [Implementation Roadmap](#10-implementation-roadmap)

---

## 1. System Architecture

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MATLAB USER SCRIPT                                 │
│  (e.g., initital_ex, lin_equiv_paperfigure.m, CenterSurround.m)            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        JAVA ANALYSIS LAYER                                   │
│  edu.washington.rieke.Analysis (Entry Point)                                │
│  ├── getEntityLoader()      → EntityLoader                                  │
│  ├── getEpochTreeFactory()  → EpochTreeFactory                              │
│  └── getEpochListFactory()  → EpochListFactory                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────┐   ┌─────────────┐   ┌───────────────┐
            │ EpochList │   │ EpochTree   │   │ Epoch         │
            │ (flat)    │   │ (hierarchy) │   │ (single trial)│
            └───────────┘   └─────────────┘   └───────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           epochTreeGUI                                       │
│  ├── graphicalTree (UI component)                                           │
│  ├── graphicalTreeNode (node widget)                                        │
│  └── singleEpoch (plotting panel)                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ANALYSIS FUNCTIONS                                    │
│  getMeanResponseTrace(), getResponseAmplitudeStats(), getSelectedData()     │
│  runTreeCalculation(), MeanSelectedNodes()                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Core Java Classes (from jenkins-jauimodel-275.jar)

| Class | Purpose |
|-------|---------|
| `edu.washington.rieke.Analysis` | Main entry point, provides factory singletons |
| `edu.washington.rieke.jauimodel.AuiEpochTree` | EpochTree implementation |
| `edu.washington.rieke.jauimodel.AuiEpoch` | Epoch implementation |
| `edu.washington.rieke.symphony.generic.GenericEpochList` | EpochList implementation |
| `edu.washington.rieke.symphony.generic.GenericEpochTreeFactory` | Builds trees from lists |
| `riekesuite.analysis` | MATLAB-facing analysis API |
| `riekesuite.util.SplitValueFunctionAdapter` | Converts MATLAB functions to Java splitters |

---

## 2. Data Flow Pipeline

### 2.1 Complete Data Flow

```
Step 1: INITIALIZATION
════════════════════════════════════════════════════════════════
loader = edu.washington.rieke.Analysis.getEntityLoader();
treeFactory = edu.washington.rieke.Analysis.getEpochTreeFactory();

Step 2: DATA LOADING
════════════════════════════════════════════════════════════════
list = loader.loadEpochList([path 'epochs.mat'], dataFolder);
    │
    ▼
Returns: EpochList containing all Epoch objects
    - Each Epoch has: protocolSettings, responses, stimuli, cell, startDate, keywords

Step 3: SPLITTER PREPARATION
════════════════════════════════════════════════════════════════
% Create MATLAB function handles for custom splitting
dateSplit = @(list) splitOnExperimentDate(list);

% Convert to Java-compatible format
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);
    │
    ▼
Returns: Java HashMap<Epoch, SplitValue> for each epoch

Step 4: TREE BUILDING
════════════════════════════════════════════════════════════════
tree = riekesuite.analysis.buildTree(list, {
    'protocolSettings(source:type)',    % String key path → direct property access
    dateSplit_java,                      % Java HashMap → custom function result
    'cell.label',                        % String key path → nested property
    'protocolSettings(imageName)',       % String key path
    keywordSplitter_java,                % Java HashMap
    'protocolSettings(equivalentIntensity)',
    'protocolSettings(stimulusTag)'
});
    │
    ▼
Returns: Hierarchical EpochTree
    Root
    ├── Node (splitKey='protocolSettings(source:type)', splitValue='Amp1')
    │   ├── Node (splitKey=dateSplit, splitValue='2024-01-15')
    │   │   ├── Node (splitKey='cell.label', splitValue='c1')
    │   │   │   └── ... (more levels)
    │   │   │       └── LeafNode (isLeaf=true, epochList=[epochs...])
    │   │   └── Node (splitKey='cell.label', splitValue='c2')
    │   └── Node (splitKey=dateSplit, splitValue='2024-01-16')
    └── Node (splitKey='protocolSettings(source:type)', splitValue='Amp2')

Step 5: GUI LAUNCH
════════════════════════════════════════════════════════════════
gui = epochTreeGUI(tree);
    │
    ▼
Creates interactive GUI with:
    - Tree browser (left panel) - graphicalTree component
    - Plotting canvas (right panel) - singleEpoch viewer
    - Selection/checkbox controls

Step 6: ANALYSIS
════════════════════════════════════════════════════════════════
nodes = gui.getSelectedEpochTreeNodes();
epochList = nodes{1}.epochList;  % Get epochs at selected node
data = getSelectedData(epochList, 'Amp1');  % Get response matrix
```

### 2.2 Key Transformation: EpochList → EpochTree

The `buildTree` algorithm (from `GenericEpochTreeFactory`):

```
buildTree(epochList, keyPaths):
    if keyPaths is empty:
        return LeafNode(epochList)  # Base case

    currentKey = keyPaths[0]
    remainingKeys = keyPaths[1:]

    # Group epochs by value at currentKey
    groups = {}
    for epoch in epochList:
        value = getSplitValue(epoch, currentKey)
        groups[value].append(epoch)

    # Create child nodes for each unique value
    node = TreeNode(splitKey=currentKey)
    for value in sorted(groups.keys()):
        child = buildTree(groups[value], remainingKeys)
        child.splitValue = value
        node.addChild(child)

    return node
```

---

## 3. Core Components Detailed

### 3.1 EpochTree Node Structure

```javascript
EpochTree {
    // Identity
    splitKey: Object        // The key used to split (e.g., 'cell.label' or HashMap)
    splitValue: Comparable  // The value at this split (e.g., 'c1', 500, '2024-01-15')

    // Hierarchy
    parent: EpochTree       // Parent node (null for root)
    children: List<EpochTree>  // Child nodes (empty for leaves)

    // Data
    isLeaf: boolean         // True if this is a leaf node
    epochList: EpochList    // Only populated for leaf nodes

    // Custom storage
    custom: Map<String, Object>  // User-defined properties
        - 'isSelected': boolean  // Selection state for UI
        - 'isExample': boolean   // Example flag for highlighting
        - 'display': Map         // UI appearance settings
        - 'results': Map         // Analysis results storage

    // Key Methods
    leafNodes(): List<EpochTree>           // All leaf descendants
    descendentsDepthFirst(): EpochTree[]   // All descendants in DFS order
    splitValues(): Map<String, Object>     // All key-value pairs from root to this node
    childBySplitValue(value): EpochTree    // Find child by its split value
}
```

### 3.2 EpochList Structure

```javascript
EpochList {
    // Elements
    elements(): Epoch[]              // All epochs in list
    firstValue(): Epoch              // First epoch
    length(): int                    // Number of epochs
    valueByIndex(i): Epoch           // Get epoch by index

    // Streams
    stimuliStreamNames(): String[]   // e.g., ['Amp1', 'LED']
    responseStreamNames(): String[]  // e.g., ['Amp1']

    // Data Access (CRITICAL!)
    // Use: riekesuite.getResponseMatrix(epochList, streamName)
    // Returns: double[numEpochs][numSamples]

    // Sorting
    sortedBy(keyPath): EpochList     // Return sorted copy

    // Keywords
    keywords(): Set<String>          // All keyword tags
}
```

### 3.3 Epoch Structure

```javascript
Epoch {
    // Metadata
    protocolID(): String             // e.g., 'edu.washington.rieke.PulseFamily'
    comment(): String
    duration(): Double               // seconds
    startDate(): double[]            // [year, month, day, hour, min, sec]

    // Parent references
    cell(): Cell                     // Parent cell
        cell.label(): String         // e.g., 'c1'
        cell.experiment(): Experiment
            experiment.startDate()
            experiment.purpose()

    // Protocol Parameters (VERY IMPORTANT!)
    protocolSettings(): Map<String, Object>
    protocolSettings(key): Object    // Direct access
        - 'preTime', 'stimTime', 'tailTime'  // Timing (ms)
        - 'sampleRate'                        // Hz
        - 'amp'                               // Amplifier name
        - 'equivalentIntensity'
        - 'imageName'
        - 'annulusOuterDiameter', 'annulusInnerDiameter'
        - Custom parameters...

    // Data Streams
    responses(): Map<String, Response>
    responses(name): Response        // e.g., responses('Amp1')
        response.data(): double[]    // Raw response data

    stimuli(): Map<String, Stimulus>
    stimuli(name): Stimulus
        stimulus.data(): double[]
        stimulus.parameters()

    // State
    isSelected: boolean              // UI selection state
    includeInAnalysis: boolean       // Analysis inclusion flag

    // Keywords
    keywords(): Set<String>          // e.g., {'cell-attached', 'ON-parasol'}
    addKeywordTag(tag): void
    removeKeywordTag(tag): void
}
```

---

## 4. Tree Building Process

### 4.1 Split Key Types

The `buildTree` function accepts two types of split keys:

#### Type 1: String Key Paths

Direct property access using dot notation:

```matlab
'protocolSettings(source:type)'   % Access protocolSettings.get('source:type')
'cell.label'                      % Access epoch.cell.label
'protocolSettings(imageName)'     % Access protocolSettings.get('imageName')
```

**Key Path Resolution:**
- `protocolSettings(X)` → `epoch.protocolSettings.get('X')`
- `cell.label` → `epoch.cell.label`
- `cell.experiment.startDate` → `epoch.cell.experiment.startDate`

#### Type 2: Java HashMaps (from SplitValueFunctionAdapter)

For custom splitting logic:

```matlab
% 1. Define MATLAB function that takes epoch, returns split value
dateSplit = @(epoch) splitOnExperimentDate(epoch);

% 2. Pre-compute split values for all epochs → Java HashMap
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);

% 3. HashMap maps: Epoch → SplitValue
% Example: {epoch1: '2024-01-15', epoch2: '2024-01-15', epoch3: '2024-01-16'}
```

### 4.2 SplitValueFunctionAdapter.buildMap

**Purpose:** Convert a MATLAB function into a Java HashMap for efficient lookup during tree building.

**Process:**
```
Input: epochList, matlabFunction
Output: java.util.HashMap<Epoch, Object>

for each epoch in epochList:
    value = matlabFunction(epoch)  # Call MATLAB function
    hashMap.put(epoch, value)

return hashMap
```

**Why?** Tree building needs to look up split values many times. Pre-computing to a HashMap avoids repeated MATLAB→Java calls.

---

## 5. Splitter Functions

### 5.1 Built-in Splitters (TreeSplitters/)

#### splitOnExperimentDate.m
```matlab
function V = splitOnExperimentDate(epoch)
    V = datestr(datetime(epoch.cell.experiment.startDate'));
end
% Returns: Date string like '24-Jan-2024'
```

#### splitOnKeywords.m
```matlab
function V = splitOnKeywords(epoch)
    V = strvcat(epoch.keywords);
end
% Returns: Concatenated keyword string
```

#### splitOnCellType.m
```matlab
function V = splitOnCellType(epoch)
    keywords = epoch.keywords.toArray;
    V = '';
    for i = 1:length(keywords)
        if contains(keywords(i), 'ON') || contains(keywords(i), 'OFF')
            V = keywords(i);
            return
        end
    end
end
```

### 5.2 Custom Splitter Pattern

```matlab
% Pattern for custom splitters:
function V = splitOnCustomProperty(epoch)
    % Access protocol settings
    value = epoch.protocolSettings.get('customProperty');

    % Transform if needed
    V = processValue(value);
end

% Usage:
customSplit = @(epoch) splitOnCustomProperty(epoch);
customSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, customSplit);
```

### 5.3 Complex Splitter Example

From `splitOnStimulusCenter.m`:
```matlab
function V = splitOnStimulusCenter(epoch)
    % Handle multiple possible key names (different rigs)
    if (~isempty(epoch.protocolSettings.get('background:Microdisplay Stage@localhost:centerOffset')))
        temp = epoch.protocolSettings.get('background:Microdisplay Stage@localhost:centerOffset');
    end
    if (~isempty(epoch.protocolSettings.get('background:LightCrafter Stage@localhost:centerOffset')))
        temp = epoch.protocolSettings.get('background:LightCrafter Stage@localhost:centerOffset');
    end
    % ... more variants ...
    V = get(temp, 0);  % Get first element of array
end
```

---

## 6. GUI System

### 6.1 epochTreeGUI Class

**File:** `MHT-analysis-package-master/JauiModel&TreeTools/epoch-tree-gui/epochTreeGUI.m`

```matlab
classdef epochTreeGUI < handle
    properties
        epochTree        % The root EpochTree
        showEpochs       % Whether to show individual epochs as nodes
        figure           % MATLAB figure handle
        isBusy           % Loading state
    end

    properties(Hidden)
        treeBrowser      % Left panel with tree visualization
        plottingCanvas   % Right panel for data plotting
    end
end
```

#### Key Methods

| Method | Purpose |
|--------|---------|
| `buildUIComponents()` | Create figure and panels |
| `initTreeBrowser()` | Initialize graphicalTree |
| `marryEpochNodesToWidgets(epochNode, browserNode)` | Link EpochTree nodes to UI widgets |
| `getSelectedEpochTreeNodes()` | Get currently selected nodes |
| `plotEpochData()` | Update plotting panel |
| `setExample()` | Toggle example highlighting |

### 6.2 graphicalTree Class

**File:** `epoch-tree-gui/graphicalTree/graphicalTree.m`

Manages the visual tree representation with:
- Node expansion/collapse
- Checkbox selection
- Keyboard navigation (arrows, 'f' for flag)
- Mouse interaction

#### Key Properties

```matlab
trunk           % Root node (graphicalTreeNode)
nodeList        % All nodes (graphicalTreeList)
widgetList      % Visual widgets
selectedWidgetKeys  % Currently selected indices
```

#### Callbacks

```matlab
nodesSelectedFcn     % Called when selection changes
nodesCheckedFcn      % Called when checkboxes toggle
nodeBecameCheckedFcn % Called per-node on check change
```

### 6.3 graphicalTreeNode Class

```matlab
classdef graphicalTreeNode < handle
    properties
        tree              % Parent graphicalTree
        selfKey           % Index in nodeList
        parentKey         % Parent's index
        childrenKeys      % Children indices

        depth             % Level in tree
        name              % Display text
        textColor         % [R G B]
        textBackgroundColor

        isExpanded        % Show children?
        isChecked         % Checkbox state
        recursiveCheck    % Propagate checks to children?

        userData          % Attached EpochTree or Epoch object
    end
end
```

### 6.4 Data-UI Binding

The `marryEpochNodesToWidgets` function creates the binding:

```matlab
function marryEpochNodesToWidgets(self, epochNode, browserNode)
    browserNode.userData = epochNode;  % CRITICAL: Link UI node to data

    % Set display name from splitValue
    if isobject(epochNode.splitValue)
        display.name = epochNode.splitValue.toString();
    else
        display.name = num2str(epochNode.splitValue);
    end

    % Store display settings in epochNode.custom
    epochNode.custom.put('display', riekesuite.util.toJavaMap(display));

    % Handle leaf nodes with epochs
    if epochNode.isLeaf && self.showEpochs
        epochs = epochNode.epochList.elements;
        for ii = 1:length(epochs)
            ep = epochs(ii);
            epochWidget = browserNode.tree.newNode(browserNode);
            epochWidget.userData = ep;
            epochWidget.isChecked = ep.isSelected;
            epochWidget.name = sprintf('%3d: %d-%02d-%02d %d:%d:%d', ii, ep.startDate);
        end
    else
        % Recurse for children
        for each child...
    end
end
```

---

## 7. Data Access Patterns

### 7.1 Getting Response Data (CRITICAL!)

**Primary Method:**
```matlab
% Get response matrix from EpochList
dataMatrix = riekesuite.getResponseMatrix(epochList, 'Amp1');
% Returns: double[numEpochs][numSamples]
```

**With Selection Filter (getSelectedData.m):**
```matlab
function epochData = getSelectedData(epochList, streamName)
    tempData = riekesuite.getResponseMatrix(epochList, streamName);

    % Filter by isSelected flag
    for epoch = 1:epochList.length
        isSelected(epoch) = epochList.valueByIndex(epoch).isSelected;
    end
    selectedEpochs = find(isSelected == 1);
    epochData = tempData(selectedEpochs, :);
end
```

### 7.2 Getting Protocol Parameters

```matlab
% Single epoch
epoch = epochList.firstValue;
preTime = epoch.protocolSettings.get('preTime');      % milliseconds
stimTime = epoch.protocolSettings.get('stimTime');
sampleRate = epoch.protocolSettings.get('sampleRate'); % Hz
amp = epoch.protocolSettings.get('amp');               % 'Amp1'

% Convert to samples
prePts = (preTime / 1e3) * sampleRate;
stimPts = (stimTime / 1e3) * sampleRate;
```

### 7.3 Tree Traversal

```matlab
% Get all epochs under a node
epochList = getTreeEpochs(epochTree);  % Returns EpochList
epochList = getTreeEpochs(epochTree, true);  % Only isSelected epochs

% Get all leaf nodes
leaves = getTreeLeaves(epochTree);  % Returns cell array
leaves = getTreeLeaves(epochTree, true);  % Only selected leaves

% Iterate children
for i = 1:node.children.length
    child = node.children.elements(i);
    % Process child...
end

% Navigate by split value
specificChild = node.childBySplitValue(500);  % Find child with splitValue=500

% Get all split values from root to this node
allSplits = node.splitValues();  % Returns Map
cellLabel = allSplits.get('cell.label');
```

### 7.4 Storing Results on Nodes

```matlab
function runTreeCalculation(nodes, C)
    for i = 1:length(nodes)
        curNode = nodes(i);

        % Run analysis
        resultStruct = C.func(curNode, params);

        % Store results on node
        resultMap = riekesuite.util.toJavaMap(resultStruct);

        if isempty(curNode.custom.get('results'))
            curNode.custom.put('results', resultMap);
        else
            % Merge with existing results
            results = curNode.custom.get('results');
            % ... merge logic ...
        end
    end
end
```

---

## 8. Analysis Workflow Examples

### 8.1 Basic Analysis Pattern

```matlab
% 1. Setup
loader = edu.washington.rieke.Analysis.getEntityLoader();
list = loader.loadEpochList('data.mat', dataFolder);

% 2. Build tree
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, @splitOnExperimentDate);
tree = riekesuite.analysis.buildTree(list, {
    dateSplit_java,
    'cell.label',
    'protocolSettings(stimTime)'
});

% 3. Launch GUI and select nodes
gui = epochTreeGUI(tree);
% User selects nodes in GUI...

% 4. Get selected data
nodes = gui.getSelectedEpochTreeNodes();
for i = 1:length(nodes)
    node = nodes{i};
    epochList = getTreeEpochs(node, true);  % Only selected epochs

    % Get response data
    data = getSelectedData(epochList, 'Amp1');

    % Get parameters
    sampleRate = epochList.firstValue.protocolSettings.get('sampleRate');
    preTime = epochList.firstValue.protocolSettings.get('preTime');

    % Analyze...
    meanTrace = mean(data, 1);
end
```

### 8.2 Nested Loop Analysis (from lin_equiv_paperfigure.m)

```matlab
rootNode = gui.getSelectedEpochTreeNodes(){1};

% Loop over hierarchy levels
for ctype_idx = 1:rootNode.children.length
    cellTypeNode = rootNode.children.elements(ctype_idx);

    for date_idx = 1:cellTypeNode.children.length
        dateNode = cellTypeNode.children.elements(date_idx);

        for cell_idx = 1:dateNode.children.length
            cellNode = dateNode.children.elements(cell_idx);

            % Get protocol parameters
            rig_info = cellNode.epochList.elements(1).protocolSettings.get('experiment:rig');

            for patch_idx = 1:cellNode.children.length
                patchNode = cellNode.children.elements(patch_idx);

                % Get data at leaf
                for leaf_idx = 1:patchNode.children.length
                    leafNode = patchNode.children(leaf_idx);
                    epochData = getSelectedData(leafNode.epochList, 'Amp1');

                    % Process...
                end
            end
        end
    end
end
```

### 8.3 Using Analysis Functions

```matlab
% getMeanResponseTrace usage
epochList = node.epochList;
response = getMeanResponseTrace(epochList, 'extracellular');
% Returns:
%   response.mean      - mean trace
%   response.stdev     - standard deviation
%   response.SEM       - standard error
%   response.n         - number of trials
%   response.timeVector
%   response.units

% getResponseAmplitudeStats usage
stats = getResponseAmplitudeStats(epochList, 'exc');
% Returns:
%   stats.peak.mean, stats.peak.SEM
%   stats.integrated.mean, stats.integrated.SEM
```

---

## 9. Critical Functions Reference

### 9.1 Java Entry Points

| Function | Returns | Usage |
|----------|---------|-------|
| `edu.washington.rieke.Analysis.getEntityLoader()` | EntityLoader | Load epoch lists |
| `edu.washington.rieke.Analysis.getEpochTreeFactory()` | EpochTreeFactory | Build trees |
| `edu.washington.rieke.Analysis.getEpochListFactory()` | EpochListFactory | Create empty lists |

### 9.2 Data Loading

| Function | Input | Output |
|----------|-------|--------|
| `loader.loadEpochList(path, dataFolder)` | MAT file path | EpochList |
| `riekesuite.analysis.buildTree(list, keyPaths)` | EpochList, cell array | EpochTree |

### 9.3 Data Access

| Function | Input | Output |
|----------|-------|--------|
| `riekesuite.getResponseMatrix(epochList, stream)` | EpochList, string | double[][] |
| `riekesuite.getResponseVector(epoch, stream)` | Epoch, string | double[] |
| `getSelectedData(epochList, stream)` | EpochList, string | double[][] (filtered) |
| `getTreeEpochs(tree, onlySelected?)` | EpochTree | EpochList |
| `getTreeLeaves(tree, onlySelected?)` | EpochTree | cell array |

### 9.4 Splitter Helpers

| Function | Input | Output |
|----------|-------|--------|
| `riekesuite.util.SplitValueFunctionAdapter.buildMap(list, func)` | EpochList, function | Java HashMap |
| `riekesuite.util.toJavaMap(struct)` | MATLAB struct | Java HashMap |
| `convertJavaArrayList(javaArray)` | Java ArrayList | MATLAB array |

### 9.5 Tree Navigation

| Method | Returns |
|--------|---------|
| `tree.children.elements()` | Array of child nodes |
| `tree.children.length` | Number of children |
| `tree.leafNodes.elements()` | All leaf descendants |
| `tree.splitValues()` | Map of all splits to this node |
| `tree.childBySplitValue(value)` | Child with matching value |
| `tree.epochList` | EpochList (leaf nodes only) |

---

## 10. Implementation Roadmap

### 10.1 Required Components for New Epic Tree

#### Phase 1: Core Data Structures
1. **Epoch Class** - MATLAB struct or class with:
   - protocolSettings (Map/struct)
   - responses (Map of stream → data)
   - stimuli (Map of stream → data)
   - cell reference
   - startDate, duration, keywords
   - isSelected, includeInAnalysis flags

2. **EpochList Class** - Array wrapper with:
   - elements access
   - responseStreamNames, stimuliStreamNames
   - getResponseMatrix(streamName)
   - sortedBy(keyPath)

3. **EpochTree Class** - Node with:
   - splitKey, splitValue
   - parent, children
   - isLeaf, epochList
   - custom properties map

#### Phase 2: Tree Building
1. **buildTree Function**
   - Accept list of key paths (strings and HashMaps)
   - Recursive grouping algorithm
   - Support both string key paths and custom functions

2. **Key Path Resolver**
   - Parse 'protocolSettings(X)' syntax
   - Parse 'cell.label' dot notation
   - Handle nested property access

3. **Splitter Function Pattern**
   - Accept epoch, return split value
   - Pre-computation to HashMap equivalent

#### Phase 3: GUI System
1. **Tree Browser Component**
   - Hierarchical node display
   - Expand/collapse
   - Checkbox selection with recursion
   - Keyboard navigation

2. **Data Viewer Component**
   - Plot response traces
   - Show epoch metadata
   - Navigate through epochs

3. **Selection System**
   - Track selected nodes
   - Filter by isSelected flag
   - Example highlighting

#### Phase 4: Analysis Integration
1. **getSelectedData** equivalent
2. **Analysis function wrappers**
3. **Results storage on nodes**

### 10.2 Key Differences from Original

| Original (Java) | New (Python/MATLAB) |
|-----------------|---------------------|
| CoreData/JNI persistence | MAT file or HDF5 |
| Java HashMap | Python dict or MATLAB containers.Map |
| AuiEpoch objects | Struct or class |
| JUNG visualization | Web-based or native GUI |
| riekesuite.util.* | Native equivalents |

### 10.3 Critical Path Items

1. **Data Loading** - Must read existing MAT exports
2. **buildTree Algorithm** - Core functionality
3. **Key Path Resolution** - Access nested properties
4. **Response Matrix Access** - Primary data output
5. **Selection/Filtering** - isSelected flag handling

---

## Appendix A: Example initital_ex Annotated

```matlab
% === INITIALIZATION ===
close all; clear all; clc;

% Get Java singletons
loader = edu.washington.rieke.Analysis.getEntityLoader();
treeFactory = edu.washington.rieke.Analysis.getEpochTreeFactory();

% === DATA LOADING ===
% Load epochs from MAT file export
list = loader.loadEpochList([exportFolder 'lin_equiv_spikes.mat'], dataFolder);
% Returns: EpochList with N epochs

% === SPLITTER SETUP ===
% Create MATLAB function handle
dateSplit = @(list) splitOnExperimentDate(list);
% Convert to Java HashMap for efficient tree building
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);
% Result: HashMap {epoch1: '24-Jan-2024', epoch2: '24-Jan-2024', ...}

keywordSplitter = @(list) splitOnKeywords(list);
keywordSplitter_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, keywordSplitter);

% === TREE BUILDING ===
tree = riekesuite.analysis.buildTree(list, {
    'protocolSettings(source:type)', ...  % Level 1: Split by amplifier
    dateSplit_java, ...                   % Level 2: Split by date
    'cell.label', ...                     % Level 3: Split by cell
    'protocolSettings(imageName)', ...    % Level 4: Split by image
    keywordSplitter_java, ...             % Level 5: Split by keywords
    'protocolSettings(equivalentIntensity)', ... % Level 6
    'protocolSettings(stimulusTag)'       % Level 7: Leaf level
});
% Result: Hierarchical tree with 7 levels, epochs at leaves

% === GUI ===
gui = epochTreeGUI(tree);
% Opens interactive browser
% User can: expand/collapse, select nodes, check/uncheck, view data
```

---

## Appendix B: Protocol Settings Key Reference

Common protocol settings keys found in the codebase:

| Key | Type | Description |
|-----|------|-------------|
| `preTime` | double | Pre-stimulus time (ms) |
| `stimTime` | double | Stimulus duration (ms) |
| `tailTime` | double | Post-stimulus time (ms) |
| `sampleRate` | double | Sampling rate (Hz) |
| `amp` | string | Amplifier name ('Amp1') |
| `equivalentIntensity` | double | Equivalent disc intensity |
| `imageName` | string | Natural image identifier |
| `backgroundIntensity` | double | Background light level |
| `annulusOuterDiameter` | double | Annulus outer size |
| `annulusInnerDiameter` | double | Annulus inner size |
| `currentPatchLocation` | array | [x, y] patch position |
| `stimulusTag` | string | Stimulus condition tag |
| `experiment:rig` | string | Rig identifier ('B', 'G') |
| `source:type` | string | Recording source |

---

*Document generated: 2026-01-24*
*Based on analysis of old_epochtree/ codebase*
