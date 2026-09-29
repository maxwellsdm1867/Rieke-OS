# Complete Workflow Guide: From Database to Visualization

This guide walks through the complete process of querying, extracting, and visualizing electrophysiology data using the EpicTreeGUI system.

## System Overview

```
┌──────────────────────────────────────────────────────────┐
│  STEP 1: Query & Extract (Python)                       │
│  - Query DataJoint database                              │
│  - Extract epoch data from H5 files                      │
│  - Export to standard .mat format                        │
└────────────────┬─────────────────────────────────────────┘
                 │
                 │ .mat file (standard format)
                 ▼
┌──────────────────────────────────────────────────────────┐
│  STEP 2: Visualize & Analyze (MATLAB)                   │
│  - Load standard format                                  │
│  - Browse hierarchical tree                              │
│  - Run analysis functions                                │
│  - Generate plots                                        │
└──────────────────────────────────────────────────────────┘
```

## Prerequisites

### Python Environment
```bash
pip install datajoint h5py scipy numpy
```

### MATLAB
- MATLAB R2019b or later (for App Designer components)
- No additional toolboxes required

### Data
- Access to DataJoint database
- H5 files accessible at paths in database

## Step-by-Step Workflow

### Step 1: Query and Export (Python)

#### 1.1 Interactive Export

Easiest method for quick exports:

```bash
cd /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/python_export
python export_to_epictree.py
```

Follow the prompts:
```
Enter username: your_username
Experiment name (or press Enter for all): 20250115A
Cell type (or press Enter for all): OnP
Protocol name (or press Enter for all): Contrast
Output file [epictree_export_20250123_143000.mat]: my_data.mat
```

The script will:
1. Connect to database
2. Execute query
3. Extract data from H5 files
4. Save to .mat file
5. Print summary

#### 1.2 Programmatic Export

For scripted workflows:

```python
#!/usr/bin/env python3
import sys
sys.path.append('/Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api')

import datajoint as dj
from export_to_epictree import EpicTreeExporter

# Connect
db = dj.VirtualModule('schema.py', 'schema')
exporter = EpicTreeExporter('username', db)

# Define query
query = {
    'experiment': {'COND': {'type': 'COND', 'value': 'exp_name="20250115A"'}},
    'cell': {'COND': {'type': 'COND', 'value': 'type="OnP"'}}
}

# Export
exporter.export_query_to_mat(query, 'onp_cells.mat', verbose=True)
```

#### 1.3 Export Output

The export creates a `.mat` file with this structure:
```
format_version: '1.0'
metadata: {created_date, data_source, export_user, ...}
experiments: [
    {id, exp_name, is_mea, cells: [
        {id, type, epoch_groups: [
            {id, protocol_name, epoch_blocks: [
                {id, epochs: [
                    {id, parameters, responses, stimuli}
                ]}
            ]}
        ]}
    ]}
]
```

### Step 2: Visualize in MATLAB

#### 2.1 Launch EpicTreeGUI

```matlab
% In MATLAB
cd /Users/maxwellsdm/Documents/GitHub/epicTreeGUI
epicTreeGUI()
```

#### 2.2 Load Data

Option A: Use menu
```
File > Load Data... > select my_data.mat
```

Option B: Programmatically
```matlab
% Load data
[treeData, metadata] = loadEpicTreeData('my_data.mat');

% Display summary
disp(['Experiments: ' num2str(length(treeData.experiments))]);
disp(['Created: ' metadata.created_date]);
```

#### 2.3 Browse the Tree

The GUI shows a hierarchical tree:
```
├── Experiment: 20250115A [Patch]
    ├── Cell 42 (OnP)
        ├── Group 1 (Contrast)
            ├── Block 1 (10 epochs)
                ├── Epoch 1 [1R/1S]
                ├── Epoch 2 [1R/1S]
                └── ...
```

Click on any node to view details:
- Experiment: metadata, experimenter, rig, etc.
- Cell: type, RF parameters, properties
- Epoch: parameters, timing, response/stimulus data

### Step 3: Analyze Data

#### 3.1 Access Epoch Data

```matlab
% Load data
[treeData, ~] = loadEpicTreeData('my_data.mat');

% Navigate to first epoch
exp = treeData.experiments(1);
cell = exp.cells(1);
eg = cell.epoch_groups(1);
eb = eg.epoch_blocks(1);
epoch = eb.epochs(1);

% Get response data
if ~isempty(epoch.responses)
    response = epoch.responses(1);
    trace = response.data;
    sample_rate = response.sample_rate;
    spike_times = response.spike_times;

    % Plot
    figure;
    time = (0:length(trace)-1) / sample_rate * 1000;  % Convert to ms
    plot(time, trace);
    xlabel('Time (ms)');
    ylabel(['Voltage (' response.units ')']);
    title(['Epoch ' num2str(epoch.id) ' - ' response.device_name]);
end
```

#### 3.2 Compute PSTH

```matlab
% Collect spike times from multiple epochs
all_spike_times = {};
for i = 1:length(eb.epochs)
    epoch = eb.epochs(i);
    if ~isempty(epoch.responses)
        spike_times = epoch.responses(1).spike_times;
        all_spike_times{i} = spike_times;
    end
end

% Compute PSTH
bin_size = 10;  % ms
time_window = [0 5000];  % ms
psth = computePSTH(all_spike_times, bin_size, time_window);

% Plot
figure;
bar(psth.time, psth.rate);
xlabel('Time (ms)');
ylabel('Firing Rate (Hz)');
title('PSTH');
```

#### 3.3 Compare Across Parameters

```matlab
% Group epochs by parameter (e.g., contrast)
contrasts = [];
mean_rates = [];

for i = 1:length(eb.epochs)
    epoch = eb.epochs(i);

    % Get contrast parameter
    if isfield(epoch.parameters, 'contrast')
        contrast = epoch.parameters.contrast;

        % Compute mean spike rate
        if ~isempty(epoch.responses) && ~isempty(epoch.responses(1).spike_times)
            duration = (epoch.epoch_end_ms - epoch.epoch_start_ms) / 1000;  % sec
            spike_count = length(epoch.responses(1).spike_times);
            rate = spike_count / duration;

            contrasts(end+1) = contrast;
            mean_rates(end+1) = rate;
        end
    end
end

% Plot contrast response
figure;
plot(contrasts, mean_rates, 'o-');
xlabel('Contrast');
ylabel('Mean Firing Rate (Hz)');
title('Contrast Response Function');
```

## Example Workflows

### Workflow 1: Export and Analyze OnP Cells

```bash
# 1. Export OnP cells from specific experiment
python export_to_epictree.py
# Enter: username, exp_name="20250115A", type="OnP"
```

```matlab
% 2. Load and analyze in MATLAB
[data, ~] = loadEpicTreeData('onp_cells.mat');

% 3. Extract all spike times from contrast protocol
all_spikes = {};
for i = 1:length(data.experiments)
    exp = data.experiments(i);
    for j = 1:length(exp.cells)
        cell = exp.cells(j);
        for k = 1:length(cell.epoch_groups)
            eg = cell.epoch_groups(k);
            if strcmp(eg.protocol_name, 'Contrast')
                % Extract spikes from all epochs
                for m = 1:length(eg.epoch_blocks)
                    eb = eg.epoch_blocks(m);
                    for n = 1:length(eb.epochs)
                        epoch = eb.epochs(n);
                        if ~isempty(epoch.responses)
                            all_spikes{end+1} = epoch.responses(1).spike_times;
                        end
                    end
                end
            end
        end
    end
end

% 4. Analyze
```

### Workflow 2: Compare Protocols Across Experiments

```python
# Export all data from multiple experiments
experiments = ['20250115A', '20250116A', '20250117A']

for exp_name in experiments:
    query = {
        'experiment': {'COND': {'type': 'COND', 'value': f'exp_name="{exp_name}"'}}
    }
    exporter.export_query_to_mat(query, f'{exp_name}.mat')
```

```matlab
% Load and compare
exp_files = {'20250115A.mat', '20250116A.mat', '20250117A.mat'};

figure;
for i = 1:length(exp_files)
    [data, ~] = loadEpicTreeData(exp_files{i});

    % Analyze and plot
    % ...

    hold on;
end
legend(exp_files);
```

## Tips & Best Practices

### Efficient Querying
1. **Filter early**: Use specific queries rather than exporting everything
2. **Check counts**: Verify query returns expected number of results
3. **Exclude levels**: Skip hierarchy levels you don't need

### Data Organization
1. **Descriptive filenames**: Use experiment names and dates
2. **Batch exports**: Separate by experiment or cell type
3. **Document queries**: Save query objects for reproducibility

### Analysis
1. **Validate data**: Check for empty responses/stimuli
2. **Parameter access**: Always check if field exists before accessing
3. **Vectorize**: Use array operations instead of loops when possible

## Troubleshooting

### Export Issues

**Problem**: "Could not read H5 data"
- **Solution**: Check H5 file paths in database, verify file permissions

**Problem**: "Query returned 0 results"
- **Solution**: Verify query syntax, check database contents

### MATLAB Issues

**Problem**: "Undefined function 'loadEpicTreeData'"
- **Solution**: Add `/src` to MATLAB path: `addpath('src')`

**Problem**: Empty data when accessing epochs
- **Solution**: Check `is_mea` flag - MEA data uses different structure

## Advanced Topics

### Custom Export Functions

Create specialized exporters:

```python
class CustomExporter(EpicTreeExporter):
    def _build_epoch(self, epoch_node, experiment_id, is_mea):
        epoch = super()._build_epoch(epoch_node, experiment_id, is_mea)

        # Add custom processing
        epoch['custom_field'] = self.compute_custom_metric(epoch)

        return epoch
```

### Batch Analysis

```matlab
% Analyze all .mat files in directory
files = dir('*.mat');

results = struct();

for i = 1:length(files)
    [data, ~] = loadEpicTreeData(files(i).name);

    % Run analysis
    result = analyze_data(data);

    results(i).filename = files(i).name;
    results(i).data = result;
end

% Save results
save('analysis_results.mat', 'results');
```

## Reference Documentation

- **Data Format**: [DATA_FORMAT_SPECIFICATION.md](DATA_FORMAT_SPECIFICATION.md)
- **Export Guide**: [python_export/EXPORT_GUIDE.md](python_export/EXPORT_GUIDE.md)
- **Integration Details**: [INTEGRATION_INSTRUCTIONS.md](INTEGRATION_INSTRUCTIONS.md)

## Getting Help

1. Check documentation in `/docs` folder
2. Review example scripts in `/examples` folder
3. Validate data format: Use `validateEpicTreeData()` in MATLAB
4. Check export summary: Review output from `export_to_epictree.py`

## Next Steps

1. **Learn the Format**: Read [DATA_FORMAT_SPECIFICATION.md](DATA_FORMAT_SPECIFICATION.md)
2. **Try Examples**: Run example exports and analysis
3. **Develop Analysis**: Create custom analysis functions
4. **Share Data**: Export standardized datasets for collaboration
