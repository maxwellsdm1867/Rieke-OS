# EpicTreeGUI: Hierarchical Electrophysiology Data Browser

Interactive tool for querying, exporting, and analyzing electrophysiology experiments with **backend isolation** - your visualization and analysis code stays the same regardless of how your data is stored.

## Overview

EpicTreeGUI provides a complete workflow from database queries to interactive visualization:

```
┌─────────────────────────────────────┐
│  Data Sources (Flexible)            │
│  • DataJoint Database + H5 files    │
│  • RetinAnalysis Pipeline           │
│  • Direct H5 reading                │
│  • Future: Cloud, other systems...  │
└──────────────┬──────────────────────┘
               │ Export to
               ▼
┌─────────────────────────────────────┐
│  Standard Format (.mat file)        │
│  • Defined structure                │
│  • Version controlled               │
│  • Self-contained                   │
└──────────────┬──────────────────────┘
               │ Loads into
               ▼
┌─────────────────────────────────────┐
│  EpicTreeGUI (Stable)               │
│  • Tree visualization               │
│  • Data browsing                    │
│  • Analysis functions               │
│  • Independent of data source       │
└─────────────────────────────────────┘
```

## Key Features

### Backend Isolation
- Analysis code independent of data source
- Swap databases/file formats without changing MATLAB code
- Share `.mat` files without database access

### Hierarchical Navigation
- Experiment → Cell → EpochGroup → EpochBlock → Epoch
- Browse full experimental hierarchy
- View metadata at each level

### Flexible Querying
- Filter by experiment name, cell type, protocol
- Tag-based queries
- Complex AND/OR conditions

### Interactive GUI
- Tree browser with expandable nodes
- Click to view detailed information
- Plot response traces and spike times

### Extensible
- Easy to add new data sources
- Add custom analysis functions
- Version-controlled data format

## Quick Start

### 1. Export Data (Python)

```bash
cd python_export
python export_to_epictree.py
```

Follow prompts to select experiments, cell types, and protocols.

### 2. Visualize (MATLAB)

```matlab
epicTreeGUI()
% File > Load Data... > select exported .mat file
```

Browse the tree and click nodes to view data!

## Documentation

**Start Here:**
- **[WORKFLOW_GUIDE.md](WORKFLOW_GUIDE.md)** - Complete workflow from database to visualization ⭐

**Export & Integration:**
- **[python_export/EXPORT_GUIDE.md](python_export/EXPORT_GUIDE.md)** - How to export data
- **[INTEGRATION_INSTRUCTIONS.md](INTEGRATION_INSTRUCTIONS.md)** - Data extraction details

**Architecture:**
- **[DATA_FORMAT_SPECIFICATION.md](DATA_FORMAT_SPECIFICATION.md)** - Standard format spec

## Installation

### Python Requirements

```bash
pip install datajoint h5py scipy numpy
```

### MATLAB Requirements

- MATLAB R2019b or later
- No additional toolboxes required

### Setup

```bash
git clone <repository-url>
cd epicTreeGUI

# In MATLAB:
# addpath('src'); savepath
```

## Usage Examples

### Export OnP Cells

```python
from export_to_epictree import EpicTreeExporter
import datajoint as dj

db = dj.VirtualModule('schema.py', 'schema')
exporter = EpicTreeExporter('username', db)

query = {
    'cell': {'COND': {'type': 'COND', 'value': 'type="OnP"'}}
}

exporter.export_query_to_mat(query, 'onp_cells.mat')
```

### Load and Plot in MATLAB

```matlab
% Load data
[data, metadata] = loadEpicTreeData('onp_cells.mat');

% Navigate to first epoch
exp = data.experiments(1);
cell = exp.cells(1);
epoch = cell.epoch_groups(1).epoch_blocks(1).epochs(1);

% Plot response
if ~isempty(epoch.responses)
    response = epoch.responses(1);
    time = (0:length(response.data)-1) / response.sample_rate * 1000;

    figure;
    plot(time, response.data);
    xlabel('Time (ms)');
    ylabel(['Voltage (' response.units ')']);
    title(['Epoch ' num2str(epoch.id)]);
end
```

### Interactive GUI

```matlab
epicTreeGUI()  % Launch GUI
% File > Load Data > select .mat file
% Click tree nodes to view data
```

## File Structure

```
epicTreeGUI/
├── README.md                           # This file
├── WORKFLOW_GUIDE.md                   # Complete guide ⭐
├── DATA_FORMAT_SPECIFICATION.md        # Format spec
├── INTEGRATION_INSTRUCTIONS.md         # Integration details
│
├── epicTreeGUI.m                       # Main GUI
│
├── src/                                # MATLAB source
│   ├── loadEpicTreeData.m             # Load standard format
│   ├── buildTreeFromEpicData.m        # Build tree UI
│   └── formatEpicNodeData.m           # Format display
│
├── python_export/                      # Export tools
│   ├── README.md                       # Export overview
│   ├── EXPORT_GUIDE.md                # Usage guide
│   └── export_to_epictree.py          # Main exporter
│
├── new_retinanalysis/                  # RetinAnalysis integration
└── old_epochtree/                      # Legacy code (reference)
```

## Why This Architecture?

### 1. Backend Isolation
Your MATLAB analysis code never changes when you:
- Switch from DataJoint to SQL to NoSQL
- Change file formats (H5 → custom → cloud)
- Add new data sources

### 2. Portability
- Export once, analyze anywhere
- Share files without database
- Reproducible analysis

### 3. Versioning
- `format_version` field for backward compatibility
- Evolve format while supporting old files
- Clear migration paths

### 4. Testability
- Create synthetic data for testing
- Validate exports independently
- Mock data for unit tests

## Advanced Usage

### Complex Queries

```python
query = {
    'experiment': {'COND': {'type': 'COND', 'value': 'exp_name="20250115A"'}},
    'cell': {
        'AND': [
            {'COND': {'type': 'COND', 'value': 'type="OnP"'}},
            {'COND': {'type': 'TAG', 'value': 'tag="good_quality"'}}
        ]
    },
    'epoch_block': {'COND': {'type': 'COND', 'value': 'protocol_name="Contrast"'}}
}

exporter.export_query_to_mat(query, 'filtered.mat')
```

### Batch Processing

```python
experiments = ['20250115A', '20250116A', '20250117A']

for exp in experiments:
    query = {'experiment': {'COND': {'type': 'COND', 'value': f'exp_name="{exp}"'}}}
    exporter.export_query_to_mat(query, f'{exp}.mat')
```

### Custom Analysis

```matlab
function psth = computeEpochPSTH(epoch, bin_size_ms)
    if isempty(epoch.responses) || isempty(epoch.responses(1).spike_times)
        psth = [];
        return;
    end

    spike_times = epoch.responses(1).spike_times;
    edges = epoch.epoch_start_ms:bin_size_ms:epoch.epoch_end_ms;
    counts = histcounts(spike_times, edges);

    psth.time = edges(1:end-1);
    psth.rate = counts / (bin_size_ms / 1000);  % Hz
end
```

## Extending the System

### New Data Source

Just create an exporter that outputs the standard format:

```python
class MyExporter:
    def export(self, source, output_file):
        export_data = {
            'format_version': '1.0',
            'metadata': {...},
            'experiments': [...]
        }
        scipy.io.savemat(output_file, export_data)
```

MATLAB backend works automatically - no changes needed!

### New Analysis Function

```matlab
function result = myAnalysis(cell)
    % Works with any data in standard format
    for i = 1:length(cell.epoch_groups)
        eg = cell.epoch_groups(i);
        % Analyze...
    end
end
```

## Troubleshooting

### Export Issues

**"Could not connect to database"**
- Check database is running
- Verify credentials

**"H5 file not found"**
- Check file paths in database
- Verify read permissions

### MATLAB Issues

**"Undefined function"**
```matlab
addpath('src');
savepath;
```

**"Invalid data format"**
```matlab
data = load('export.mat');
if ~isfield(data, 'format_version')
    error('Not a valid EpicTree format');
end
```

## Contributing

1. Fork the repository
2. Create feature branch
3. Follow existing code style
4. Update documentation
5. Submit pull request

## License

[Add your license]

## Citation

If you use this in research, please cite:

```
[Add citation]
```

## Contact

- **Issues**: GitHub Issues
- **Questions**: GitHub Discussions

---

**Version**: 1.0
**Last Updated**: 2025-01-23

**See Also**: [Original README](README_OLD.md) for legacy system documentation
