# Rieke Lab Infrastructure Specification
## Functional Equivalents for EpicTreeGUI

**Document Purpose:** Detailed specification of legacy Rieke lab infrastructure (`jenkins-jauimodel-275.jar`) to enable creation of functional equivalents in pure MATLAB for the new epicTreeGUI system.

**Date:** January 2026  
**Source:** Analysis of `old_epochtree/lin_equiv_paperfigure.m`, `old_epochtree/SpatioTemporalModel.m`, and JAR decompilation

---

## 1. HIGH-LEVEL ARCHITECTURE

### Legacy System (Rieke Lab)
```
DATABASE + .mat export files
         ↓
    [EntityLoader]
         ↓
    EpochList (raw epoch data)
         ↓
  [Split Functions] 
  (date, keywords, cell type, etc.)
         ↓
   [EpochTreeFactory]
         ↓
    EpochTree (hierarchical structure)
         ↓
  [epochTreeGUI] ← Interactive tree browser
         ↓
  Node Selection & Analysis
         ↓
  Data extraction, plotting, statistics
```

### New System (EpicTreeGUI)
```
.mat files (new retinanalysis format)
         ↓
  [loadEpicTreeData] (pure MATLAB)
         ↓
  EpicTreeData struct (raw epoch data)
         ↓
  [Split Functions] (pure MATLAB)
  (cellType, parameter-based, etc.)
         ↓
  [buildTreeFromEpicData]
         ↓
  uitree (MATLAB UI tree widget)
         ↓
  [epicTreeGUI] ← Interactive tree browser
         ↓
  Node Selection & Analysis
         ↓
  Data extraction, plotting, statistics
```

---

## 2. CORE COMPONENTS

### 2.1 EntityLoader / loadEpicTreeData()

**Legacy Function:** `edu.washington.rieke.Analysis.getEntityLoader()`

**Purpose:** Load epoch data from exported .mat files into memory

**Input:**
- Export file path: `exportFolder + 'lin_equiv_spikes.mat'`
- Data folder path: `/path/to/raw/data/files`

**Output:** 
- `EpochList` object containing all epochs with metadata and responses

**Key Responsibility:**
- Reads .mat file containing epoch metadata
- Links to raw data files if stored separately
- Provides access to individual epochs with their:
  - Stimulus parameters (protocolSettings)
  - Response data (voltage/current traces, spikes)
  - Timing information (startDate, preTime, stimTime, tailTime)
  - Experimental metadata (cell.label, rig info, etc.)

**New MATLAB Equivalent:**
```matlab
function epicTreeData = loadEpicTreeData(matFilePath)
  % Loads .mat file and structures data for tree building
  % Input: Path to .mat file
  % Output: Structure with fields:
  %   - experiments (hierarchical cell array)
  %   - metadata (experiment info)
  %   - isLoaded (boolean flag)
end
```

**Expected Data Structure:**
```matlab
epicTreeData.experiments{1}  % Experiment 1
  .experimentID
  .cells{1}                  % Cell within experiment
    .cellLabel
    .cellType
    .cellID
    .cellData{1}             % Group/recording within cell
      .groups{1}             % Stimulus group
        .blocks{1}           % Data block
          .epochs{1}         % Individual epoch
            .epochID
            .startDate
            .preTime
            .stimTime
            .tailTime
            .response        % [1 x nSamples]
            .responseAmplifier
            .samplingInterval
            .protocolSettings % struct with stimulus params
```

---

### 2.2 EpochTreeFactory / buildTreeFromEpicData()

**Legacy Function:** `edu.washington.rieke.Analysis.getEpochTreeFactory()`

**Purpose:** Convert flat EpochList into hierarchical tree structure

**Input:**
- `EpochList` (flat collection of all epochs)
- Split criteria (strings, arrays, function handles)

**Output:**
- `EpochTree` with hierarchical node structure

**Key Responsibility:**
- Organizes flat epoch data hierarchically
- Each node contains:
  - `splitValue` - The organizing criterion value (e.g., "2025-01-01", "ON parasol", "contrast=0.3")
  - `children` - Sub-nodes (ArrayList/array)
  - `epochList` - Raw epochs at this level
- Supports multiple organizational methods via split criteria

**New MATLAB Equivalent:**
```matlab
function treeData = buildTreeFromEpicData(epicTreeData, varargin)
  % Builds hierarchical tree structure from flat epoch data
  % Input:
  %   - epicTreeData: Output from loadEpicTreeData
  %   - Optional: splitMethod ('none', 'cellType', 'parameterName')
  % Output:
  %   - treeData: Hierarchical structure with nodes
  %     - treeData.root
  %       .splitValue = 'All Experiments'
  %       .children = cell array of child nodes
  %       .epochList = epochs at this level
end
```

---

### 2.3 Split Functions

**Purpose:** Organize epochs by different criteria

**Three Categories:**

#### A. Fixed Splitters (Built-in)

**1. splitOnExperimentDate()**
- **Input:** EpochList
- **Output:** Tree split by date of experiment
- **Example hierarchy:**
  ```
  Root
  ├─ 2025-01-15
  ├─ 2025-01-16
  └─ 2025-01-17
  ```
- **New MATLAB:** [src/splitters/splitOnExperimentDate.m](src/splitters/splitOnExperimentDate.m)

**2. splitOnCellType()**
- **Input:** EpochList
- **Output:** Tree split by retinal cell type
- **Example hierarchy:**
  ```
  Root
  ├─ ON parasol
  ├─ OFF parasol
  ├─ ON midget
  ├─ OFF midget
  └─ Starburst
  ```
- **New MATLAB:** [src/splitters/splitOnCellType.m](src/splitters/splitOnCellType.m) ✅ DONE

**3. splitOnKeywords()**
- **Input:** EpochList
- **Output:** Tree split by epoch keywords/tags
- **Example:** "natural image", "noise", "bar", "spot"
- **New MATLAB:** Needs implementation

#### B. Generic Splitter

**splitOnParameter(paramName)**
- **Input:** 
  - EpochList
  - Parameter name (string): e.g., 'contrast', 'size', 'equivalentIntensity', 'stimulusTag'
- **Output:** Tree split by unique values of that parameter
- **Example for contrast:**
  ```
  Root
  ├─ 0.1
  ├─ 0.3
  ├─ 0.5
  └─ 1.0
  ```
- **Data Source:** `protocolSettings` map within each epoch
- **New MATLAB:** [src/splitters/splitOnParameter.m](src/splitters/splitOnParameter.m) ✅ DONE

#### C. Custom Split Functions (User-Defined)

**Pattern in old code:**
```matlab
% Define custom split function
dateSplit = @(list) splitOnExperimentDate(list);

% Convert to Java adapter
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);

% Use in tree building
tree = riekesuite.analysis.buildTree(list, {
    'protocolSettings(source:type)',  % Direct field access
    dateSplit_java,                    % Custom function
    'cell.label',                      % Direct field access
    'protocolSettings(equivalentIntensity)'  % Nested field
});
```

**New MATLAB Pattern:**
```matlab
% Define hierarchical organization
splitCriteria = {
    'source_type',           % Group by source type
    'date',                  % Then by date
    'cell_label',            % Then by cell
    'stimulus_type'          % Then by stimulus type
};

treeData = buildHierarchicalTree(epicTreeData, splitCriteria);
```

---

### 2.4 Tree Node Structure

**Legacy EpochTree Node:**
```java
class EpochTreeNode {
    String splitValue;              % Organizing criterion value
    ArrayList<EpochTreeNode> children;  % Sub-nodes
    EpochList epochList;            % Raw epochs at this level
    int startIndex, endIndex;       % Index range in parent
}
```

**New MATLAB Equivalent:**
```matlab
struct TreeNode {
    splitValue       % String: organizing value
    children         % Cell array of child TreeNode structs
    epochList        % Array of epoch indices or structs
    level            % Depth in hierarchy
    label            % Display name in UI
    isLeaf           % Boolean: no more children
    data             % Any additional data for this node
}
```

---

## 3. ANALYSIS WORKFLOW

### 3.1 Data Selection Pattern

**Step 1: Build Tree**
```matlab
% Load data
list = loader.loadEpochList([exportFolder 'lin_equiv_spikes.mat'], dataFolder);

% Define organization
dateSplit = @(list) splitOnExperimentDate(list);
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);

% Build hierarchical tree
tree = riekesuite.analysis.buildTree(list, {
    'protocolSettings(source:type)',
    dateSplit_java,
    'cell.label',
    'protocolSettings(imageName)',
    'protocolSettings(equivalentIntensity)'
});
```

**Step 2: Launch GUI & Select Nodes**
```matlab
gui = epochTreeGUI(tree);
node = gui.getSelectedEpochTreeNodes();
```

**Step 3: Extract Data from Selected Node**
```matlab
% Access epochs at this tree node
rootNode = node{1};

% Loop through children (organized by split criterion)
for ctype_idx = 1 : rootNode.children.length
    childNode = rootNode.children.elements(ctype_idx);
    
    % Access individual epochs
    for epoch_idx = 1 : childNode.epochList.length
        epoch = childNode.epochList.elements(epoch_idx);
        
        % Extract epoch data
        stimTime = epoch.protocolSettings.get('stimTime') * 1e-3;
        preTime = epoch.protocolSettings.get('preTime') * 1e-3;
        response = epoch.get(params.Amp);  % Voltage or current
    end
end
```

---

### 3.2 Data Access Patterns

**Legacy Code Pattern A: Direct Field Access**
```matlab
% Accessing nested protocolSettings (dot notation in java)
rig_info = epoch.protocolSettings.get('experiment:rig');
annulusOuter = epoch.protocolSettings.get('annulusOuterDiameter');
equivalentIntensity = epoch.protocolSettings('equivalentIntensity');
```

**Legacy Code Pattern B: Time/Amplitude Data**
```matlab
% Calculate sampling points
PrePts = epoch.protocolSettings.get('preTime') * 1e-3 / params.SamplingInterval;
TailPts = epoch.protocolSettings.get('tailTime') * 1e-3 / params.SamplingInterval;
StmPts = epoch.protocolSettings.get('stimTime') * 1e-3 / params.SamplingInterval;

% Extract response data
response = getSelectedData(epochList, params.Amp);  % "Amp1", "Amp2", etc.
% Returns: [nEpochs x nSamples] matrix
```

**Legacy Code Pattern C: Spike Detection (Cell-Attached)**
```matlab
if (CellAttachedFlag)
    for epoch = 1:size(response, 1)
        [SpikeTimes, SpikeAmplitudes, RefractoryViolations] = ...
            SpikeDetection.Detector(response(epoch, :));
        
        % Convert to spike train (impulse format)
        spikeTrainResponse(epoch, :) = 0;
        spikeTrainResponse(epoch, SpikeTimes) = 1 / params.SamplingInterval;
    end
end
```

**New MATLAB Pattern:**
```matlab
% Access node and extract data
selectedNode = treeData.selectedNode;

% Loop through epochs
for idx = 1:length(selectedNode.epochList)
    epoch = selectedNode.epochList(idx);
    
    % Get timing
    preTime = epoch.preTime;           % ms
    stimTime = epoch.stimTime;         % ms
    tailTime = epoch.tailTime;         % ms
    samplingInterval = epoch.samplingInterval;  % seconds
    
    % Get response
    response = epoch.response;         % [1 x nSamples]
    
    % Get stimulus parameters
    stimParams = epoch.protocolSettings;
    contrast = stimParams.contrast;
    equivalentIntensity = stimParams.equivalentIntensity;
    
    % Process if needed
    if strcmp(epoch.recordingType, 'cellAttached')
        [spikeTimes, spikeAmplitudes] = detectSpikes(response);
    end
end
```

---

## 4. PROTOCOL SETTINGS STRUCTURE

**What it is:** Key-value map containing stimulus parameters for each epoch

**Common Fields Accessed:**
```matlab
% Temporal
protocolSettings.get('preTime')        % Pre-stimulus time (ms)
protocolSettings.get('stimTime')       % Stimulus duration (ms)
protocolSettings.get('tailTime')       % Post-stimulus time (ms)

% Spatial (Visual)
protocolSettings.get('annulusOuterDiameter')
protocolSettings.get('annulusInnerDiameter')
protocolSettings.get('imageName')      % e.g., "image_001", "noise_pattern"
protocolSettings.get('equivalentIntensity')
protocolSettings.get('backgroundIntensity')
protocolSettings.get('contrast')
protocolSettings.get('size')
protocolSettings.get('stimulusTag')    % e.g., "linear_equiv", "doves", "noise"

% Equipment/Recording
protocolSettings.get('experiment:rig') % Rig letter: 'B', 'G', etc.
protocolSettings.get('sourceType')     % e.g., 'natural image'
protocolSettings.get('protocolID')
protocolSettings.get('stimulusIndex')  % Stimulus position
```

**New MATLAB Equivalent:**
```matlab
% Structure stored in each epoch
epoch.protocolSettings = struct();
epoch.protocolSettings.preTime = 500;        % ms
epoch.protocolSettings.stimTime = 1000;      % ms
epoch.protocolSettings.tailTime = 500;       % ms
epoch.protocolSettings.contrast = 0.5;
epoch.protocolSettings.equivalentIntensity = 50000;
epoch.protocolSettings.annulusOuterDiameter = 500;
% ... more fields as needed
```

---

## 5. ANALYSIS EXAMPLES FROM LEGACY CODE

### Example 1: Linear Equivalence Analysis (lin_equiv_paperfigure.m)

**Workflow:**
1. Load epochs from `lin_equiv_spikes.mat`
2. Build tree organized by: date → cell type → stimulus type
3. Select all epochs for a cell at a given date
4. For each patch location:
   - Extract response to "image" stimulus
   - Extract response to "disc" stimulus (linear equivalent)
   - Compare responses to assess linearity
5. Calculate nonlinearity index (NLI) and statistics

**Key Data Accessed:**
```matlab
% Node selection loop structure
for ctype_idx = 1 : rootNode.children.length        % Cell types
    cellTypeNode = rootNode.children.elements(ctype_idx);
    
    for date_node = 1 : cellTypeNode.children.length  % Dates
        dateNode = cellTypeNode.children.elements(date_node);
        
        for cell_node = 1 : dateNode.children.length  % Cells
            cellNode = dateNode.children.elements(cell_node);
            
            % Extract protocols (image vs disc)
            for graph_node = 1 : cellNode.children.length
                % Access data at this level
            end
        end
    end
end
```

**New MATLAB Pattern:**
```matlab
% Navigate tree hierarchically
for each_cellType in tree.cellType_nodes
    for each_date in cellType.date_nodes
        for each_cell in date.cell_nodes
            % Access protocols
            imageEpochs = cell.protocols('image');
            discEpochs = cell.protocols('disc');
            
            % Compare responses
            imageResponse = extractResponse(imageEpochs);
            discResponse = extractResponse(discEpochs);
            nli = calculateNLI(imageResponse, discResponse);
        end
    end
end
```

### Example 2: Spatiotemporal RF Mapping (SpatioTemporalModel.m)

**Workflow:**
1. Load natural image movie stimulus (`Doves` dataset)
2. Build tree organized by: source type → date → cell → stimulus type
3. Get stimulus frames for each epoch
4. Get neural response for each epoch
5. Optionally convert to spike train for cell-attached recordings
6. Optional: Compute cone model predictions (ISETBio toolbox)

**Key Steps:**
```matlab
% Extract stimulus frames
frames = getDovesMovieMM(node, 'E', '/Path/to/Doves/');  % [spatial x spatial x time]

% Optional: Apply spatial aperture
frames = applyApertureToMovie(frames, centerSigma, ...);

% Downsample
frames = frames(1:resampleFactor:end, 1:resampleFactor:end, :);

% Extract neural response
response = getSelectedData(node.epochList, params.Amp);  % [nEpochs x nSamples]

% Convert to spike train if needed
if CellAttachedFlag
    [SpikeTimes, ...] = SpikeDetection.Detector(response);
    response(:) = 0;
    response(SpikeTimes) = 1 / samplingInterval;
end

% Optional: Cone model
LinearModel = osCreate('linear');     % Linear optics + photoreceptors
FullModel = osCompute(FullModel, sensor);
coneResponse = osGet(FullModel, 'coneCurrentSignal');
```

---

## 6. IMPLEMENTATION CHECKLIST FOR EPICGUI

### Phase 1: Core Data Loading ✅
- [x] `loadEpicTreeData()` - Load .mat files
- [x] Parse hierarchical structure
- [x] Access to protocolSettings

### Phase 2: Tree Building ✅
- [x] `buildTreeFromEpicData()` - Build UI tree
- [x] Node structure with splitValue, children, epochList
- [x] Support multiple split criteria

### Phase 3: Split Functions ✅
- [x] `splitOnCellType.m` - Group by cell type
- [x] `splitOnParameter.m` - Generic parameter splitting
- [ ] `splitOnExperimentDate.m` - Group by date
- [ ] `splitOnKeywords.m` - Group by keywords/tags

### Phase 4: Analysis Functions
- [ ] `getSelectedData()` - Extract response from epochs
- [ ] `extractSpikeTrains()` - Convert to spikes
- [ ] `plotRawTrace()` - Plot voltage/current
- [ ] `plotSpikeRaster()` - Plot spike timing
- [ ] `calculateSTA()` - Spike-triggered average
- [ ] `calculateRF()` - Receptive field
- [ ] `calculateLinearEquivalence()` - Linear nonlinear test

### Phase 5: GUI Integration
- [ ] Tree navigation callbacks
- [ ] Node selection
- [ ] Real-time data updates
- [ ] Plot refresh on node change

---

## 7. KEY DIFFERENCES: Legacy vs New

| Aspect | Legacy (Rieke Lab) | New (EpicTreeGUI) |
|--------|-------------------|------------------|
| **Language** | Java + MATLAB | Pure MATLAB |
| **Data Source** | Ovation database | .mat files (retinanalysis) |
| **Data Structure** | Complex Java objects | MATLAB structs/cell arrays |
| **Tree Building** | `riekesuite.analysis.buildTree()` | `buildTreeFromEpicData()` |
| **Node Access** | `.children.elements(idx)` | `.children{idx}` |
| **Split Criteria** | Function adapters | Direct function calls |
| **GUI Type** | Custom Swing GUI | MATLAB App Designer |
| **Data Fields** | Heterogeneous (varies by protocol) | Standardized retinanalysis format |

---

## 8. DATA FLOW EXAMPLE

### Legacy System:
```
Database ─→ Ovation API ─→ getEntityLoader() ─→ EpochList
                                                    ↓
                                          Splitter functions
                                                    ↓
                                          getEpochTreeFactory()
                                                    ↓
                                             EpochTree
                                                    ↓
                                          epochTreeGUI
                                                    ↓
                                      gui.getSelectedEpochTreeNodes()
                                                    ↓
                                      getSelectedData() → Analysis
```

### New System:
```
.mat file (retinanalysis) ─→ loadEpicTreeData() ─→ epicTreeData
                                                        ↓
                                              Splitter functions
                                                        ↓
                                        buildTreeFromEpicData()
                                                        ↓
                                                 uitree
                                                        ↓
                                              epicTreeGUI
                                                        ↓
                                        ui_tree_node_selected()
                                                        ↓
                                        displayNodeData() → Analysis
```

---

## 9. STIMULUS/PROTOCOL TYPES (From Code Analysis)

Common stimulus types encountered:
- **Natural images**: Doves movies, texture images
- **Noise stimuli**: Full-field noise, spatiotemporal white noise
- **Geometric**: Spots, bars, annuli (with variable size/contrast)
- **Flash stimuli**: Full-field flashes at different intensities
- **Linear equivalents**: Designed to test linearity of responses

---

## 10. RECORDING TYPES

From code analysis:
- **Whole-cell voltage clamp** - Continuous current recording
- **Whole-cell current clamp** - Continuous voltage recording
- **Cell-attached** - Spike recording (binary events)
- **Extracellular** - Spike recording from electrode arrays

---

## SUMMARY FOR EPICGUI IMPLEMENTATION

**You need to create:**

1. **Data Layer** (loadEpicTreeData)
   - Read .mat files structured by retinanalysis
   - Parse to MATLAB structures
   - Provide consistent API for tree building

2. **Tree Building** (buildTreeFromEpicData)
   - Hierarchical organization of flat epoch list
   - Support for multiple split criteria
   - Node structure matching legacy tree node interface

3. **Split Functions** (splitOn*)
   - Each returns unique values for organizing axis
   - Maps epochs to organization structure
   - Can be combined hierarchically

4. **Display/Analysis** (displayNodeData)
   - Extract data from selected node
   - Plot traces, spike rasters, statistics
   - Mimic legacy analysis workflows

**The architecture is preserved**, just reimplemented in pure MATLAB to work with the new retinanalysis data format!
