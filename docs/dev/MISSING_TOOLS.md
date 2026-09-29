# Missing Tools & Implementation Priority

## Executive Summary

Analysis of the legacy Rieke lab infrastructure (Java system) versus the new EpicTreeGUI reveals the following **missing MATLAB tools** needed for functional equivalence.

**Status**: ✅ Core layer created, 🟡 Splitters partially done, 🔴 Additional tools needed

---

## Priority 1: CRITICAL (Core System) ✅ MOSTLY DONE

### P1.1: loadEpicTreeData() 
**Status**: ✅ DONE (in epicTreeGUI.m)  
**Purpose**: Load .mat file and structure data for tree building  
**Implementation**: Lines 1-50 of epicTreeGUI.m  
**What it does**: Reads MAT file, parses hierarchical experiments/cells/blocks/epochs structure

### P1.2: TreeNode struct/class
**Status**: ✅ DONE (in rebuildTreeWithSplit.m)  
**Purpose**: Hierarchical node structure with splitValue, children, epochList  
**Implementation**: Struct with properties: splitValue, children (cell array), epochList, level, label, isLeaf

### P1.3: buildTreeFromEpicData()
**Status**: ✅ DONE (in epicTreeGUI.m)  
**Purpose**: Build hierarchical tree from flat epoch data  
**Implementation**: Lines 51-100 of epicTreeGUI.m

### P1.4: rebuildTreeWithSplit()
**Status**: ✅ DONE  
**Location**: [src/rebuildTreeWithSplit.m](src/rebuildTreeWithSplit.m)  
**Purpose**: Dynamic tree reorganization with different split methods  
**What it does**: Routes between 'none', 'cellType', and parameter-based splits

### P1.5: GUI Integration with Split Dropdown
**Status**: ✅ DONE (in epicTreeGUI.m)  
**Purpose**: Dropdown menu to change split organization  
**Implementation**: Lines 101-125 of epicTreeGUI.m

### P1.6: displayNodeData()
**Status**: ✅ DONE  
**Location**: [src/displayNodeData.m](src/displayNodeData.m)  
**Purpose**: Display selected node data (raw trace, spike raster, PSTH)  
**What it does**: Plots response data when user clicks tree node

---

## Priority 2: HIGH (Basic Splitters) 🟡 PARTIALLY DONE

### P2.1: splitOnCellType()
**Status**: ✅ DONE  
**Location**: [src/splitters/splitOnCellType.m](src/splitters/splitOnCellType.m)  
**Purpose**: Group epochs by retinal cell type (OnP, OffP, OnM, etc.)  
**Algorithm**: Extract cellType field from each epoch, group by unique values

### P2.2: splitOnParameter()
**Status**: ✅ DONE (Generic)  
**Location**: [src/splitters/splitOnParameter.m](src/splitters/splitOnParameter.m)  
**Purpose**: Group epochs by any parameter (contrast, size, equivalentIntensity, etc.)  
**Algorithm**: Inspect protocolSettings for paramName, collect unique values, sort appropriately

### P2.3: splitOnExperimentDate()
**Status**: 🔴 NOT DONE  
**Purpose**: Group epochs by experiment date (e.g., "2025-01-15", "2025-01-16")  
**Algorithm**:
```matlab
function nodes = splitOnExperimentDate(epochData)
    % Extract unique dates from epoch.startDate
    % Group epochs by date
    % Return nodes organized by date
end
```

### P2.4: splitOnKeywords()
**Status**: 🔴 NOT DONE  
**Purpose**: Group epochs by keywords/tags  
**Algorithm**: Extract keywords field, group by unique values

---

## Priority 3: MEDIUM (Extended Splitters) 🔴 NOT DONE

These are specific parameter-based splitters found in old code. Each follows same pattern: extract parameter, group by unique values.

### P3.1: splitOnF1F2Contrast.m
**Purpose**: Group by contrast parameter  
**Source**: F1F2 analysis protocol  
**Alias**: May be same as `splitOnParameter(data, 'contrast')`

### P3.2: splitOnF1F2CenterSize.m
**Purpose**: Group by RF center size  
**Parameter**: RF parameter from analysis_chunk

### P3.3: splitOnF1F2Phase.m
**Purpose**: Group by response phase at F1

### P3.4: splitOnRadiusOrDiameter.m
**Purpose**: Group by stimulus size/radius parameter

### P3.5: splitOnHoldingSignal.m
**Purpose**: Group by voltage clamp holding potential

### P3.6: splitOnOLEDLevel.m
**Purpose**: Group by LED/light intensity level

### P3.7: splitOnRecKeyword.m
**Purpose**: Group by recording type keyword

### P3.8: splitOnLogIRtag.m
**Purpose**: Group by IR tag log value

### P3.9: splitOnJavaArrayList.m
**Purpose**: Generic handler for Java ArrayList parameters (compatibility)

### P3.10: splitOnPatchContrast_NatImage.m
**Purpose**: Group by patch contrast for natural image protocols

### P3.11: splitOnPatchSampling_NatImage.m
**Purpose**: Group by patch sampling method for natural images

### P3.12+: Additional splitters
Check old_epochtree/ for complete list of all splitter files

**Implementation Strategy**: Create template for splitter functions
```matlab
function nodes = splitOn<ParameterName>(epochData)
    % Extract parameter from all epochs
    % Collect unique values
    % Create nodes, one per value
    % Return nodes array
end
```

---

## Priority 4: MEDIUM (Data Extraction Utilities) ✅ CRITICAL ONE DONE

### P4.0: getSelectedData() **⭐ MOST CRITICAL**
**Status**: ✅ DONE  
**Location**: [src/getSelectedData.m](src/getSelectedData.m)  
**Purpose**: Extract response data from selected epochs - **REQUIRED BY ALL ANALYSIS FUNCTIONS**  
**Usage Pattern**: Used 20+ times in old code (RFAnalysis, LSTA, SpatioTemporalModel, etc.)  
**Signature**:
```matlab
epochData = getSelectedData(treeData, epochIndices, streamName)
% Inputs:
%   treeData: EpicTreeGUI data structure
%   epochIndices: [1 x N] array of epoch indices
%   streamName: 'Amp1', 'Amp2', 'Cell', 'Frame Monitor'
% Output:
%   epochData: [nEpochs x nSamples] matrix or cell array (for spikes)
```
**What it does**:
- Flattens tree hierarchy to access epochs by index
- Extracts response data based on stream name
- Returns matrix format compatible with old analysis code
- Handles multiple amplifier channels and spike data

**Legacy equivalent**:
```matlab
% OLD: tempData = riekesuite.getResponseMatrix(epochList, streamName);
% NEW: epochData = getSelectedData(treeData, epochIndices, streamName);
```

### P4.1: getMeanResponseTrace()
**Status**: Not yet integrated with real data  
**Purpose**: Compute PSTH from spike times with optional smoothing  
**Signature**:
```matlab
[time, trace, sem] = getMeanResponseTrace(epochData, cellIds, epochIndices, varargin)
% Inputs:
%   epochData: EpochData object
%   cellIds: Which cells to include
%   epochIndices: Which epochs to include
%   varargin: Options (smoothing, baseline correction)
% Outputs:
%   time: Time vector (ms)
%   trace: Mean response (spikes/sec or current)
%   sem: Standard error of mean
```

### P4.2: getResponseAmplitudeStats()
**Purpose**: Extract peak amplitude, integrated response, etc.

### P4.3: getCycleAverageResponse()
**Purpose**: Average responses aligned to stimulus cycles (for drifting gratings)

### P4.4: getF1F2statistics()
**Purpose**: Extract F1 (fundamental) and F2 (2nd harmonic) components via FFT

### P4.5: getLinearFilterAndPrediction()
**Purpose**: Compute linear filter via reverse correlation  
**Requires**: Stimulus reconstruction

### P4.6: getNoiseStimulusAndResponse()
**Purpose**: Load and align noise stimulus with neural response

### P4.7: getTreeEpochs()
**Purpose**: Recursive tree traversal to extract all epochs under a node

### P4.8: filterEpochListByEpochGroups()
**Purpose**: Filter epochs by group labels (include/exclude)

### P4.9: makeUniformEpochList()
**Purpose**: Filter to uniform parameter values (majority rules)

---

## Priority 5: HIGH (Analysis Functions Integration) 🔴 NOT DONE

These exist in old_epochtree/ but need adaptation to new data format.

### P5.1: RFAnalysis.m
**Status**: PORTED to `epicAnalysis.RFAnalysis()` in `src/analysis/epicAnalysis.m`
**Purpose**: RF center/surround characterization, DOG fitting, per-epoch statistics (std, SEM)
**Includes**: Merged RFAnalysis + RFAnalysis2 (per-epoch stats, error bars)
**Also ported**: `detectSpikes`, `baselineCorrect`, `differenceOfGaussians`, `singleGaussian`, `halfMaxSize`, `defaultParams`
**Tests**: `tests/test_epicAnalysis.m` (10 tests, all passing with real ExpandingSpots data)

### P5.3: LSTA.m
**Status**: Exists in old_epochtree/  
**Purpose**: Linear spatio-temporal analysis (spike-triggered average)  
**Location to reference**: [old_epochtree/LSTA.m](old_epochtree/LSTA.m)

### P5.4: SpatioTemporalModel.m
**Status**: Exists in old_epochtree/  
**Purpose**: Linear-nonlinear (LN) cascade modeling  
**Needs**: Stimulus reconstruction support  
**Location to reference**: [old_epochtree/SpatioTemporalModel.m](old_epochtree/SpatioTemporalModel.m)

### P5.5: CenterSurround.m
**Status**: Exists in old_epochtree/  
**Purpose**: Expanding spot analysis, DOG fitting, surround suppression  
**Location to reference**: [old_epochtree/CenterSurround.m](old_epochtree/CenterSurround.m)

### P5.6: Interneurons.m
**Status**: Exists in old_epochtree/  
**Purpose**: Interneuron-specific analysis  
**Location to reference**: [old_epochtree/Interneurons.m](old_epochtree/Interneurons.m)

### P5.7: Occlusion.m
**Status**: Exists in old_epochtree/  
**Purpose**: Occlusion tuning analysis  
**Location to reference**: [old_epochtree/Occlusion.m](old_epochtree/Occlusion.m)

### P5.8: MeanSelectedNodes.m
**Status**: Partially done, needs integration  
**Purpose**: Overlay responses from multiple tree branches for comparison  
**Basic functionality**: Already sketched in epicTreeGUI Phase 7

---

## Implementation Roadmap

### Immediate (This Week): 🔴 DO NOW
1. ✅ Create loadEpicTreeData() - DONE
2. ✅ Create TreeNode structure - DONE
3. ✅ Create buildTreeFromEpicData() - DONE
4. ✅ Add rebuildTreeWithSplit() - DONE
5. ✅ Add splitOnCellType() - DONE
6. ✅ Add splitOnParameter() - DONE
7. ✅ Add displayNodeData() with basic plots - DONE
8. **Create splitOnExperimentDate()** - NEXT
9. **Create splitOnKeywords()** - NEXT

### Short Term (Next 1-2 weeks): 🟡 SOON
1. Create remaining 9+ specific splitters
2. Implement getMeanResponseTrace() and core data extraction utilities
3. Integrate RFAnalysis with new data format

### Medium Term (2-3 weeks): 🔴 PLANNED
1. Implement LSTA, SpatioTemporalModel, CenterSurround
2. Complete all data extraction utilities
3. Add advanced display options (multiple cells, rasters)

### Long Term (3+ weeks): 🔴 FUTURE
1. Full analysis function integration
2. Stimulus reconstruction
3. Performance optimization

---

## Data Format Reference

### Input: .mat file structure (from Python export)
```
experiments{i}
  .experimentID
  .cells{j}
    .cellLabel
    .cellType
    .cellData{k}
      .groups{l}
        .blocks{m}
          .epochs{n}
            .epochID
            .startDate
            .preTime (ms)
            .stimTime (ms)
            .tailTime (ms)
            .response [1 x nSamples]
            .responseAmplifier
            .samplingInterval (s)
            .protocolSettings (struct)
              .contrast
              .equivalentIntensity
              .annulusOuterDiameter
              .cellType
              .sourceType
              ... (20+ fields)
```

### Legacy API Patterns (to match)
```matlab
% OLD: epoch.protocolSettings.get('preTime')
% NEW: epoch.protocolSettings.preTime

% OLD: epoch.get(params.Amp)
% NEW: epoch.response (for whole voltage/current)
%      detectSpikes(epoch.response) for spikes

% OLD: epoch.cell.label
% NEW: epoch.cellLabel (flattened for simplicity)

% OLD: tree.children.elements(idx)
% NEW: tree.children{idx} (MATLAB cell array)

% OLD: epochList.length
% NEW: length(epochList)
```

---

## Testing Each Component

### Test loadEpicTreeData()
```matlab
data = loadEpicTreeData('test_export.mat');
assert(~isempty(data.experiments));
assert(length(data.experiments) > 0);
assert(~isempty(fieldnames(data.experiments{1})));
```

### Test TreeNode creation
```matlab
node = TreeNode('OnP', []);
node.addChild(TreeNode('Cell 42', []));
assert(length(node.children) == 1);
```

### Test buildTreeFromEpicData()
```matlab
treeData = buildTreeFromEpicData(epicData);
assert(~isempty(treeData.root));
assert(~isempty(treeData.root.children));
```

### Test splitOnCellType()
```matlab
nodes = splitOnCellType(epicData);
assert(length(nodes) > 0);  % Should have multiple cell types
```

### Test splitOnParameter()
```matlab
nodes = splitOnParameter(epicData, 'contrast');
assert(length(nodes) > 0);  % Should have multiple contrasts
```

---

## Key Files Location

### Already Implemented ✅
- [epicTreeGUI.m](epicTreeGUI.m) - Main GUI with loadEpicTreeData, buildTreeFromEpicData
- [src/rebuildTreeWithSplit.m](src/rebuildTreeWithSplit.m) - Dynamic tree reorganization
- [src/displayNodeData.m](src/displayNodeData.m) - Data visualization
- [src/splitters/splitOnCellType.m](src/splitters/splitOnCellType.m) - Cell type splitting
- [src/splitters/splitOnParameter.m](src/splitters/splitOnParameter.m) - Generic parameter splitting

### Still Needed 🔴
- src/splitters/splitOnExperimentDate.m
- src/splitters/splitOnKeywords.m
- src/splitters/splitOnF1F2Contrast.m
- ... (9+ more)
- src/analysis/getMeanResponseTrace.m
- ... (8+ more utilities)
- RFAnalysis.m, LSTA.m, SpatioTemporalModel.m, etc. (adapt from old_epochtree/)

### Reference Files (in old_epochtree/)
- [old_epochtree/lin_equiv_paperfigure.m](old_epochtree/lin_equiv_paperfigure.m) - Analysis workflow example
- [old_epochtree/SpatioTemporalModel.m](old_epochtree/SpatioTemporalModel.m) - LN model example
- [old_epochtree/jenkins-jauimodel-275.jar](old_epochtree/jenkins-jauimodel-275.jar) - Legacy Java classes (analyzed)

---

## Documentation References

- [RIEKE_LAB_INFRASTRUCTURE_SPECIFICATION.md](RIEKE_LAB_INFRASTRUCTURE_SPECIFICATION.md) - Complete analysis of legacy system
- [trd](trd) - Technical requirements (Section 0 has infrastructure mapping)
- [src/README_DISPLAY_SPLITTER.md](src/README_DISPLAY_SPLITTER.md) - Architecture for display/splitter system

---

**Last Updated**: January 23, 2026  
**Status**: Core system complete, 50+ functions still needed for full parity with legacy system
