# EpicTreeGUI User Guide

A pure MATLAB GUI for browsing and analyzing epoch data.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Loading Data](#loading-data)
3. [Building Trees](#building-trees)
4. [Tree Navigation](#tree-navigation)
5. [Selection & Controlled Access](#selection--controlled-access)
6. [Data Retrieval](#data-retrieval)
7. [Analysis Functions](#analysis-functions)
8. [GUI Usage](#gui-usage)
9. [Common Workflows](#common-workflows)
10. [Stimulus Reconstruction](#stimulus-reconstruction)
11. [DataJoint Web App Integration](#datajoint-web-app-integration)

---

## Getting Started

### Installation

1. Clone or download the epicTreeGUI repository
2. Add the src folder to your MATLAB path:

```matlab
addpath(genpath('/path/to/epicTreeGUI/src'));
```

### Requirements

- MATLAB R2020a or later
- No external toolboxes required (pure MATLAB)

### Quick Start

```matlab
% Configure H5 directory (if using H5 lazy loading)
epicTreeConfig('h5_dir', '/path/to/h5/files');

% Launch GUI
gui = epicTreeGUI('/path/to/data.mat');
```

---

## Loading Data

### Data Format

EpicTreeGUI works with `.mat` files conforming to the standard data format. See [DATA_FORMAT_SPECIFICATION.md](../DATA_FORMAT_SPECIFICATION.md) for details.

Basic structure:
```matlab
data.format_version = '1.0';
data.experiments{1}.cells{1}.epoch_groups{1}.epoch_blocks{1}.epochs{1}
```

### Loading with epicTreeTools

```matlab
% Load data file
data = load('experiment.mat');

% Create tree
tree = epicTreeTools(data);

% Check total epochs
allEpochs = tree.getAllEpochs(false);
fprintf('Loaded %d epochs\n', length(allEpochs));
```

### H5 Lazy Loading

For large datasets, response data can be lazy-loaded from H5 files:

```matlab
% Set H5 directory once per session
epicTreeConfig('h5_dir', '/Users/data/h5');

% Get H5 file path for an experiment
h5_file = getH5FilePath('2025-12-02_F');

% Data is loaded from H5 when needed
[data, epochs, fs] = getSelectedData(node, 'Amp1', h5_file);
```

---

## Building Trees

Trees organize epochs hierarchically by splitting on different parameters.

### Basic Tree Building

```matlab
% Create tree from data
tree = epicTreeTools(data);

% Build by cell type
tree.buildTree({'cellInfo.type'});

% Build by cell type, then protocol
tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});

% Build by cell type, protocol, then contrast
tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name', 'parameters.contrast'});
```

### Available Split Keys

**String key paths** (dot notation):
- `cellInfo.type` - Cell type (OnP, OffP, etc.)
- `cellInfo.label` - Cell label/ID
- `blockInfo.protocol_name` - Protocol name
- `parameters.contrast` - Stimulus contrast
- `parameters.preTime` - Pre-stimulus time
- `parameters.stimTime` - Stimulus time
- Any parameter: `parameters.<paramName>`

**Function handles** (for complex splitting):
```matlab
tree.buildTreeWithSplitters({
    'cellInfo.type',
    @epicTreeTools.splitOnExperimentDate,
    @epicTreeTools.splitOnProtocol,
    'parameters.contrast'
});
```

### Built-in Splitter Functions

| Function | Description |
|----------|-------------|
| `splitOnCellType` | Groups by cell type |
| `splitOnCellLabel` | Groups by cell label |
| `splitOnProtocol` | Groups by protocol name |
| `splitOnExperimentDate` | Groups by experiment date |
| `splitOnContrast` | Groups by contrast value |
| `splitOnKeywords` | Groups by epoch keywords |

---

## Tree Navigation

### Navigate Down (to children)

```matlab
% Get number of children
n = node.childrenLength();

% Get child by index (1-based)
child = node.childAt(1);

% Loop over all children
for i = 1:node.childrenLength()
    child = node.childAt(i);
    fprintf('Child %d: %s\n', i, string(child.splitValue));
end

% Find child by split value
onpNode = tree.childBySplitValue('OnP');
contrastNode = parentNode.childBySplitValue(0.5);

% Get all leaf nodes
leaves = tree.leafNodes();
```

### Navigate Up (to parents)

```matlab
% Get direct parent
parent = node.parent;

% Get ancestor N levels up
grandparent = node.parentAt(2);

% Get root node
root = node.getRoot();

% Get depth (root = 0)
d = node.depth();

% Get path from root
path = node.pathFromRoot();  % Cell array of nodes

% Get human-readable path string
pathStr = node.pathString();  % "Root > OnP > 0.5"
pathStr = node.pathString('/');  % "Root/OnP/0.5"
```

### Check Node Properties

```matlab
% Is this a leaf node?
if node.isLeaf
    epochs = node.epochList;  % Direct access to epochs
end

% Count epochs under this node
n = node.epochCount();

% Get split value
value = node.splitValue;  % e.g., 'OnP' or 0.5
```

---

## Selection & Controlled Access

### Selection State

Each epoch has an `isSelected` flag for filtering:

```matlab
% Get all epochs (selected + unselected)
allEpochs = node.getAllEpochs(false);

% Get only selected epochs
selectedEpochs = node.getAllEpochs(true);

% Count selected
nSelected = node.selectedCount();

% Set selection on a node (and optionally children)
node.setSelected(true, true);   % Select all recursively
node.setSelected(false, false); % Deselect this node only

% Mark individual epochs
node.epochList{1}.isSelected = false;
```

### Controlled Access (putCustom/getCustom)

Store and retrieve custom data on nodes without directly modifying properties:

```matlab
% Store analysis results
results = struct();
results.mean = 42.5;
results.std = 3.2;
results.n = 10;
node.putCustom('results', results);

% Check if key exists
if node.hasCustom('results')
    % Retrieve results
    r = node.getCustom('results');
    fprintf('Mean: %.2f (n=%d)\n', r.mean, r.n);
end

% Remove custom data
node.removeCustom('results');

% List all custom keys
keys = node.customKeys();
```

---

## Data Retrieval

### getSelectedData (Primary Function)

The most important function for analysis - gets response data filtered by selection:

```matlab
% Basic usage
[dataMatrix, epochs, sampleRate] = getSelectedData(node, 'Amp1');

% With H5 lazy loading
[dataMatrix, epochs, sampleRate] = getSelectedData(node, 'Amp1', h5_file);

% Returns:
%   dataMatrix - [nEpochs x nSamples] response data
%   epochs     - Cell array of epoch structs
%   sampleRate - Sample rate in Hz
```

### getResponseMatrix

Lower-level function - gets all epochs without selection filtering:

```matlab
% Get response matrix from epoch list
[respMatrix, fs] = getResponseMatrix(epochs, 'Amp1');
[respMatrix, fs] = getResponseMatrix(epochs, 'Amp1', h5_file);  % With H5
```

### getTreeEpochs

Convenience wrapper for getAllEpochs:

```matlab
epochs = getTreeEpochs(node);           % All epochs
epochs = getTreeEpochs(node, true);     % Selected only
```

---

## Analysis Functions

### getMeanResponseTrace

Compute mean response with SEM:

```matlab
% Get data first
[data, ~, fs] = getSelectedData(node, 'Amp1', h5_file);

% Compute mean trace
result = getMeanResponseTrace(data, fs);

% Result contains:
%   result.mean       - Mean trace
%   result.stdev      - Standard deviation
%   result.SEM        - Standard error of mean
%   result.n          - Number of epochs
%   result.timeVector - Time in seconds
```

### getResponseAmplitudeStats

Compute peak and integrated response:

```matlab
result = getResponseAmplitudeStats(data, fs, 'PreTime', 500, 'StimTime', 1000);

% Result contains:
%   result.peakAmplitude
%   result.integratedResponse
%   result.timeToMeak
```

### getCycleAverageResponse

For periodic stimuli:

```matlab
result = getCycleAverageResponse(data, fs, cyclePeriodMs);

% Result contains:
%   result.cycleAverage
%   result.F1amplitude
%   result.F2amplitude
```

### MeanSelectedNodes

Compare multiple conditions:

```matlab
% Get nodes for different conditions
nodes = {};
for i = 1:parentNode.childrenLength()
    nodes{end+1} = parentNode.childAt(i);
end

% Plot comparison
results = MeanSelectedNodes(nodes, 'Amp1', 'h5_file', h5_file);

% Result contains:
%   results.meanResponse - [nNodes x nSamples]
%   results.respAmp      - Integrated response per node
%   results.splitValue   - Split value for each node
```

---

## GUI Usage

### Launching the GUI

```matlab
% Basic launch
gui = epicTreeGUI('data.mat');

% Without individual epochs in tree
gui = epicTreeGUI('data.mat', 'noEpochs');
```

### GUI Layout

```
+------------------+------------------------+
|   Tree Browser   |     Data Viewer        |
|     (40%)        |        (60%)           |
|                  |                        |
| [Split Dropdown] |  [Info Table]          |
|                  |                        |
| + Root           |  [Response Plot]       |
|   + OnP          |                        |
|     + Protocol1  |                        |
|       - 0.3      |                        |
|       - 0.5      |                        |
|                  |                        |
| [Buttons]        |                        |
+------------------+------------------------+
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| ↑ / ↓ | Navigate up/down in tree |
| ← | Collapse selected node |
| → | Expand selected node |
| F or Space | Toggle selection checkbox |

### Menu Options

**File Menu:**
- Load Data... - Open a new data file
- Export Selection... - Save selected epochs to .mat
- Close - Close the GUI

**Analysis Menu:**
- Mean Response Trace - Plot mean ± SEM
- Response Amplitude - (Coming soon)

---

## Common Workflows

### Workflow 1: Analyze Contrast Response

```matlab
% Load and build tree
data = load('experiment.mat');
tree = epicTreeTools(data);
tree.buildTree({'cellInfo.type', 'parameters.contrast'});

% Configure H5
epicTreeConfig('h5_dir', '/path/to/h5');
h5_file = getH5FilePath('experiment_name');

% Navigate to OnP cell type
onpNode = tree.childBySplitValue('OnP');

% Analyze each contrast
for i = 1:onpNode.childrenLength()
    contrastNode = onpNode.childAt(i);
    contrast = contrastNode.splitValue;

    % Get data
    [data, ~, fs] = getSelectedData(contrastNode, 'Amp1', h5_file);

    % Compute mean
    result = getMeanResponseTrace(data, fs);

    % Store results
    contrastNode.putCustom('results', result);

    fprintf('Contrast %.2f: mean=%.2f, n=%d\n', ...
        contrast, mean(result.mean), result.n);
end
```

### Workflow 2: Compare Cell Types

```matlab
% Build tree by cell type
tree = epicTreeTools(data);
tree.buildTree({'cellInfo.type'});

% Collect all cell type nodes
cellNodes = {};
for i = 1:tree.childrenLength()
    cellNodes{end+1} = tree.childAt(i);
end

% Compare using MeanSelectedNodes
results = MeanSelectedNodes(cellNodes, 'Amp1', ...
    'h5_file', h5_file, ...
    'ShowAnalysis', true);
```

### Workflow 3: Batch Analysis with Results Storage

```matlab
% Build deep tree
tree = epicTreeTools(data);
tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name', 'parameters.contrast'});

% Analyze all leaf nodes
leaves = tree.leafNodes();
for i = 1:length(leaves)
    leaf = leaves{i};

    % Get data
    [data, ~, fs] = getSelectedData(leaf, 'Amp1', h5_file);

    if isempty(data)
        continue;
    end

    % Compute statistics
    result = struct();
    result.mean = mean(data, 1);
    result.peak = max(mean(data, 1));
    result.n = size(data, 1);
    result.path = leaf.pathString();

    % Store at leaf
    leaf.putCustom('results', result);
end

% Query results later
for i = 1:length(leaves)
    r = leaves{i}.getCustom('results');
    if ~isempty(r)
        fprintf('%s: peak=%.2f (n=%d)\n', r.path, r.peak, r.n);
    end
end
```

---

## Stimulus Reconstruction

Symphony stores stimuli parametrically — only the generator class name (`stimulus_id`) and parameters are saved, not the actual waveform data. EpicTreeGUI includes pure MATLAB ports of all 11 Symphony stimulus generators to reconstruct waveforms on demand.

### How It Works

When you access a stimulus via `getStimulusByName()`, it checks:
1. If `.data` is already populated, return it directly
2. If `.data` is empty but `.stimulus_id` and `.stimulus_parameters` exist, auto-reconstruct
3. If neither, return empty

This is transparent — callers always get a populated `data` field back.

### Supported Generators

| Generator | stimulusID | Key Parameters |
|-----------|-----------|----------------|
| Pulse | `symphonyui.builtin.stimuli.PulseGenerator` | preTime, stimTime, tailTime, amplitude, mean |
| Sine | `symphonyui.builtin.stimuli.SineGenerator` | + period, phase |
| Square | `symphonyui.builtin.stimuli.SquareGenerator` | + period, phase |
| Ramp | `symphonyui.builtin.stimuli.RampGenerator` | preTime, stimTime, tailTime, amplitude, mean |
| Direct Current | `symphonyui.builtin.stimuli.DirectCurrentGenerator` | time, offset |
| Pulse Train | `symphonyui.builtin.stimuli.PulseTrainGenerator` | + numPulses, increments |
| Repeating Pulse | `symphonyui.builtin.stimuli.RepeatingPulseGenerator` | Same as Pulse |
| Sum | `symphonyui.builtin.stimuli.SumGenerator` | Composite of sub-generators |
| Gaussian Noise | `edu.washington.riekelab.stimuli.GaussianNoiseGenerator` | stDev, freqCutoff, numFilters, seed |
| Gaussian Noise V2 | `edu.washington.riekelab.stimuli.GaussianNoiseGeneratorV2` | Same params, corrected filter |
| Binary Noise | `edu.washington.riekelab.stimuli.BinaryNoiseGenerator` | segmentTime, amplitude, seed |

### Usage

```matlab
% Single stimulus waveform
stim = epicTreeTools.getStimulusByName(epoch, 'UV LED');
plot(stim.data);

% Single epoch: [data, sampleRate]
[stimData, sr] = epicTreeTools.getStimulusFromEpoch(epoch, 'UV LED');

% Matrix for multiple epochs: [nEpochs x nSamples]
[stimMatrix, sr] = epicTreeTools.getStimulusMatrix(epochs, 'UV LED');

% Direct generator call (for testing/exploration)
params = struct('preTime', 100, 'stimTime', 200, 'tailTime', 100, ...
    'amplitude', 5, 'mean', 0, 'sampleRate', 10000);
[data, sr] = epicStimulusGenerators.generateStimulus( ...
    'symphonyui.builtin.stimuli.PulseGenerator', params);
```

### Noise Reproducibility

Stochastic generators (gaussianNoise, gaussianNoiseV2, binaryNoise) use seeded RNG via `RandStream('mt19937ar', 'Seed', seed)`. The same seed always produces identical output, matching Symphony's behavior for STA/linear filter analysis.

### Two Classes of Stimuli

**Waveform stimuli** — the generator IS the stimulus:
- Used by noise protocols (VariableMeanNoise, etc.)
- `stimulus_id` = `GaussianNoiseGeneratorV2`, device = `UV LED`
- Must reconstruct for STA/LN analysis

**Parametric stimuli** — the generator is just holding current:
- Used by spot/grating protocols (SingleSpot, ExpandingSpots, etc.)
- `stimulus_id` = `DirectCurrentGenerator`, device = `Amp1` (0 pA DC)
- The actual light stimulus is described by protocol parameters (preTime, spotIntensity, etc.)
- Stage-based stimuli have no `stimulus_id` at all — `stimulus_id` is empty/NULL

---

## DataJoint Web App Integration

EpicTreeGUI integrates with a DataJoint-based web application for centralized data management. The web app provides a query interface for browsing experiments, exporting to epicTreeGUI `.mat` format, and importing selection masks back.

### Architecture

```
┌──────────────────────────────────────────────┐
│  DataJoint Web App                            │
│                                               │
│  Frontend: Next.js (React) on port 3000       │
│  Backend:  Flask (Python) on port 5000        │
│  Database: MySQL 5.7 in Docker on port 3306   │
│                                               │
│  Key endpoints:                               │
│  POST /pop/add-data     Ingest experiments    │
│  GET  /results/export-mat  Export to .mat     │
│  POST /results/import-ugm  Import .ugm mask   │
│  GET  /pop/clear          Clear database       │
└──────────────┬───────────────────────────────┘
               │ .mat / .ugm files
               ▼
┌──────────────────────────────────────────────┐
│  epicTreeGUI (MATLAB)                         │
│  Load .mat → Build tree → Analyze → Save .ugm │
└──────────────────────────────────────────────┘
```

### Prerequisites

- **Docker Desktop** running (for MySQL 5.7 container)
- **Node.js** installed (for the Next.js frontend)
- **Python 3.9+** with Poetry (for the Flask backend)
- **H5 files** accessible on disk (export stores paths, not raw waveforms)

### Setup

1. **Start the MySQL database:**

```bash
cd /path/to/datajoint/databases/single_cell_test
docker compose up -d
```

2. **Start the Flask backend:**

```bash
cd /path/to/datajoint/next-app/api
poetry install
poetry run flask run --port 5000
# Use port 5001 if 5000 is taken by AirPlay on macOS
```

3. **Start the Next.js frontend** (in a separate terminal):

```bash
cd /path/to/datajoint/next-app
npm install
npm run dev
```

4. **Configure the proxy** if using a non-default Flask port. In `next.config.js`:

```javascript
destination: 'http://127.0.0.1:5001/:path*'
```

5. **Open the app** at `http://localhost:3000`.

### Adding Data

The web app ingests data from three directories:

| Directory | Contents | Purpose |
|-----------|----------|---------|
| **H5 directory** | `.h5` experiment files | Raw Symphony data |
| **Meta directory** | `.json` metadata files | Parsed from H5 by RetinAnalysis |
| **Tags directory** | `.json` tag files | User annotations (can be empty `{}`) |

Data is ingested via the `/pop/add-data` endpoint. The Flask backend parses JSON metadata and populates 14+ DataJoint tables (Experiment, Animal, Preparation, Cell, EpochGroup, EpochBlock, Epoch, Response, Stimulus, Protocol, Tags, etc.).

### Stimulus Metadata Pipeline

The DataJoint `Stimulus` table stores generator metadata alongside device and path info:

| Column | Source | Example |
|--------|--------|---------|
| `h5_uuid` | H5 file UUID | `db89fd05-2b19-...` |
| `device_name` | Recording device | `Amp1` |
| `h5path` | Path in H5 file | `/experiment-.../stimuli/Amp1-...` |
| `stimulus_id` | Generator class name | `symphonyui.builtin.stimuli.DirectCurrentGenerator` |
| `sample_rate` | Sample rate | `10000.0` |
| `sample_rate_units` | Units | `Hz` |
| `duration_seconds` | Duration | `0.75` |
| `units` | Physical units | `A` |

These fields flow from H5 → JSON metadata → DataJoint DB → Python export → MATLAB reconstruction.

### Exporting to epicTreeGUI

1. **Run a query** in the web app to select experiments/cells of interest.
2. **Click "Export to epicTree"** (green button in the results toolbar).
3. A `.mat` file downloads to your browser's download folder.

### Using the Export in MATLAB

```matlab
% 1. Load the export
exportFile = '/path/to/epictree_export_YYYYMMDD_HHMMSS.mat';
[data, meta] = loadEpicTreeData(exportFile);

% 2. Configure H5 directory (derived from the export itself)
tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
tree.buildTree({'cellInfo.type'});
allEps = tree.getAllEpochs(false);
h5Dir = fileparts(allEps{1}.responses{1}.h5_file);
epicTreeConfig('h5_dir', h5Dir);

% 3. Build tree with your preferred splitters
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});

% 4. Navigate and analyze — stimulus reconstruction is automatic
firstCell = tree.childAt(1);
ssNode = firstCell.childBySplitValue('SingleSpot');
[data, epochs, fs] = epicTreeTools.getSelectedData(ssNode, 'Amp1');
plot((1:size(data,2))/fs*1000, mean(data,1));
xlabel('Time (ms)'); ylabel('Response (pA)');

% 5. Get stimulus waveforms (auto-reconstructed from stimulus_id)
[stimMatrix, sr] = epicTreeTools.getStimulusMatrix(epochs, 'UV LED');

% 6. Launch GUI
gui = epicTreeGUI(tree);
```

### Importing Selection Masks

After analyzing in MATLAB and saving a `.ugm` file, you can push selections back to DataJoint:

1. **Save `.ugm` in MATLAB:** `tree.saveUserMetadata(filepath)`
2. **Click "Import Mask"** (orange button in the DataJoint results toolbar)
3. **Select the `.ugm` file** — deselected epochs get tagged as `"excluded"` in DataJoint

The import is idempotent (re-importing produces identical tags) and uses `h5_uuid` for matching (survives database repopulation).

### Notes

- **Protocol names**: DataJoint exports use full Java package paths (e.g., `edu.washington.riekelab.protocols.SingleSpot`). The `childBySplitValue` method supports substring matching, so `childBySplitValue('SingleSpot')` works.
- **Epoch ordering**: Epochs are sorted by `start_time` at leaf nodes, so the same data produces identical ordering regardless of data source.
- **H5 lazy loading**: The export stores `h5_path` references, not raw waveform data. H5 files must be accessible at the paths recorded in the export.
- **No MEA support**: The DataJoint export currently supports single-cell patch clamp data only (`is_mea = false`).
- **Database credentials**: Hardcoded as `root`/`simple` on `127.0.0.1:3306` (local development only).

---

## Troubleshooting

### "No epochs found"

- Check data format matches DATA_FORMAT_SPECIFICATION.md
- Verify epochs are nested correctly: `experiments → cells → epoch_groups → epoch_blocks → epochs`

### "H5 file not found"

- Ensure `epicTreeConfig('h5_dir', path)` is set correctly
- Check H5 file naming matches experiment name

### "Response stream not found"

- Check available streams: `getStreamNames(epochs, 'responses')`
- Common streams: 'Amp1', 'Amp2'

### Selection not working

- Epochs need `isSelected` field (defaults to true)
- Check: `epochs{1}.isSelected`

---

## API Reference

See inline documentation for each function:

```matlab
help epicTreeTools
help getSelectedData
help MeanSelectedNodes
```

---

*Last updated: February 2026*
