# EpicTreeGUI Data Format Specification

## Architecture: Separation of Concerns

This document defines the **standard data format** that acts as an interface between data packaging and visualization/analysis.

```
┌─────────────────────────────────────────────────────────────┐
│              DATA PACKAGING LAYER (Flexible)                │
│  Can be replaced without affecting visualization/analysis   │
├─────────────────────────────────────────────────────────────┤
│  Current Implementation: DataJoint Flask Web App            │
│  - Flask backend (Python) + Next.js frontend (React)        │
│  - MySQL 5.7 in Docker (DataJoint ORM)                     │
│  - Ingests H5 files + JSON metadata via /pop/add-data      │
│  - Exports to .mat via /results/export-mat                  │
│  - Imports .ugm masks via /results/import-ugm              │
│                                                              │
│  Alternative: RetinAnalysis Python Pipeline                  │
│  - Direct H5 parsing without database                       │
│                                                              │
│  Future Implementations: Could be anything!                  │
│  - Cloud-based data storage                                 │
│  - Different experiment management systems                   │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ Exports to
                   ▼
┌─────────────────────────────────────────────────────────────┐
│          STANDARD DATA FORMAT (.mat file)                   │
│                                                              │
│  This is the CONTRACT between layers                        │
│  - Defined structure (see below)                            │
│  - Contains ALL data needed for analysis                    │
│  - Independent of data source                               │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ Reads from
                   ▼
┌─────────────────────────────────────────────────────────────┐
│       EPIC TREE GUI BACKEND (Stable)                        │
│  Never needs to change when data source changes             │
├─────────────────────────────────────────────────────────────┤
│  - Tree visualization                                       │
│  - Epoch browsing                                           │
│  - Analysis functions (PSTH, RF analysis, etc.)            │
│  - Plotting routines                                        │
│  - Cell type classification tools                           │
└─────────────────────────────────────────────────────────────┘
```

## Standard Data Format Structure

The standard format is a MATLAB `.mat` file containing a structured hierarchy that mirrors experimental organization.

### Top-Level Structure

```matlab
% data.mat contains:
data = struct(...
    'format_version', '1.0', ...        % For future compatibility
    'metadata', metadata_struct, ...     % Experiment-level metadata
    'experiments', experiments_array ... % Array of experiment structs
);
```

### Metadata Structure

```matlab
metadata = struct(...
    'created_date', '2025-01-23 14:30:00', ...
    'data_source', 'DataJoint + H5 files', ...  % Or whatever system generated it
    'source_database', 'my_database', ...
    'export_user', 'username', ...
    'notes', 'Optional notes about this export' ...
);
```

### Experiment Structure

Each experiment contains the full hierarchy: Experiment → Cell → EpochGroup → EpochBlock → Epoch

```matlab
experiment = struct(...
    % Identification
    'id', 1, ...
    'exp_name', '20250115A', ...
    'label', 'Optional experiment label', ...

    % Metadata
    'is_mea', false, ...              % true for MEA, false for patch
    'start_time', datetime(...), ...
    'experimenter', 'John Doe', ...
    'rig', 'Rig1', ...
    'institution', 'University', ...

    % Data hierarchy
    'cells', cells_array ...          % Array of cell structs
);
```

### Cell Structure

```matlab
cell = struct(...
    % Identification
    'id', 42, ...
    'label', 'Cell 1', ...

    % Cell properties
    'type', 'OnP', ...                % Cell type classification
    'properties', struct(...), ...     % Additional cell properties

    % Noise/RF matching (if applicable)
    'noise_id', 15, ...               % Matched noise cell ID (0 if not matched)
    'rf_params', rf_struct, ...        % RF parameters (see below)

    % Data hierarchy
    'epoch_groups', epoch_groups_array ...
);
```

### RF Parameters Structure

```matlab
rf_params = struct(...
    'center_x', 0.0, ...      % RF center X coordinate (microns or degrees)
    'center_y', 0.0, ...      % RF center Y coordinate
    'std_x', 50.0, ...        % RF standard deviation X
    'std_y', 50.0, ...        % RF standard deviation Y
    'rotation', 0.0 ...       % RF rotation angle (degrees)
);
% Empty struct if no RF data available
```

### Epoch Group Structure

```matlab
epoch_group = struct(...
    % Identification
    'id', 1, ...
    'label', 'Group 1', ...

    % Protocol information
    'protocol_name', 'Contrast', ...
    'protocol_id', 5, ...

    % Timing
    'start_time', datetime(...), ...
    'end_time', datetime(...), ...

    % Data hierarchy
    'epoch_blocks', epoch_blocks_array ...
);
```

### Epoch Block Structure

```matlab
epoch_block = struct(...
    % Identification
    'id', 1, ...
    'label', 'Block 1', ...

    % Protocol
    'protocol_name', 'Contrast', ...
    'protocol_id', 5, ...

    % Timing
    'start_time', datetime(...), ...
    'end_time', datetime(...), ...

    % Parameters (common across epochs in this block)
    'parameters', struct(...
        'parameter1', value1, ...
        'parameter2', value2 ...
    ), ...

    % MEA-specific (optional, empty for patch)
    'data_dir', '', ...               % Path to MEA sorted data directory
    'sorting_algorithm', '', ...      % Sorting algorithm used

    % Data hierarchy
    'epochs', epochs_array ...
);
```

### Epoch Structure (The Core Data)

This is where the actual experimental data lives.

```matlab
epoch = struct(...
    % Identification
    'id', 123, ...
    'label', 'Epoch 1', ...

    % Timing
    'start_time', datetime(...), ...
    'end_time', datetime(...), ...
    'epoch_start_ms', 0.0, ...        % Start time in ms (relative to block)
    'epoch_end_ms', 5000.0, ...       % End time in ms

    % Stimulus timing
    'frame_times_ms', [0, 16.7, 33.3, ...], ...  % Frame onset times (ms)

    % Parameters (specific to this epoch)
    'parameters', struct(...
        'contrast', 0.5, ...
        'temporal_frequency', 2.0, ...
        'spatial_frequency', 0.1, ...
        ... % Protocol-specific parameters
    ), ...

    % Response data
    'responses', responses_array, ...  % Array of response structs

    % Stimulus data
    'stimuli', stimuli_array ...       % Array of stimulus structs
);
```

### Response Structure

```matlab
response = struct(...
    % Identification
    'id', 456, ...
    'device_name', 'Amp1', ...        % Recording device
    'label', 'Voltage response', ...

    % Data - can be either embedded or lazy-loaded from H5
    'data', [voltage_trace], ...      % Actual recorded data (may be empty for lazy loading)
    'spike_times', [50.2, 103.5, ...], ...  % Spike times in ms (if detected)

    % H5 Lazy Loading (for large datasets)
    'h5_path', '/experiment-.../responses/Amp1-...', ...  % Path within H5 file

    % Metadata
    'sample_rate', 10000, ...         % Hz
    'sample_rate_units', 'Hz', ...
    'units', 'mV', ...                % Units of 'data' field

    % Timing offsets (if needed)
    'offset_ms', 0.0 ...
);
```

### Lazy Loading from H5 Files

For large datasets, response data can be lazy-loaded from H5 files instead of embedding in the .mat file. This follows the retinanalysis pattern:

**Configuration (set once per session):**

```matlab
% Configure H5 directory - similar to retinanalysis H5_DIR
epicTreeConfig('h5_dir', '/Users/data/h5');
```

**Response Structure for Lazy Loading:**

- `response.data` may be empty
- `response.h5_path` contains the path within the H5 file (e.g., `/experiment-.../responses/Amp1-...`)
- H5 file is derived from experiment name: `{h5_dir}/{exp_name}.h5`

**H5 File Structure:**

```text
{exp_name}.h5
└── experiment-{uuid}/
    └── .../epochGroups/epochGroup-{uuid}/
        └── epochBlocks/{protocol}-{uuid}/
            └── epochs/epoch-{uuid}/
                └── responses/
                    └── Amp1-{uuid}/
                        └── data  (compound dataset with 'quantity' field)
```

**Loading Data:**

```matlab
% Get H5 file path from experiment name
h5_file = getH5FilePath(exp_name);  % Uses epicTreeConfig('h5_dir')

% Load response matrix with lazy loading from H5
[dataMatrix, sampleRate] = getResponseMatrix(epochs, 'Amp1', h5_file);

% Or use getSelectedData for selected epochs only
[data, epochs, fs] = getSelectedData(treeNode, 'Amp1', h5_file);
```

**Benefits:**

- .mat files remain small (metadata only)
- Raw data stays in original H5 files
- Data loaded on-demand when needed for analysis

### Stimulus Structure

```matlab
stimulus = struct(...
    % Identification
    'id', 789, ...
    'device_name', 'Stage', ...       % Stimulus device (e.g., 'LED', 'Stage')
    'label', 'LED stimulus', ...

    % Generator identification (for waveform reconstruction)
    'stimulus_id', 'symphonyui.builtin.stimuli.DirectCurrentGenerator', ...  % Fully-qualified Symphony generator class name
    'stimulus_parameters', struct(...   % Generator-specific parameters
        'time', 0.75, ...              % Varies by generator type
        'offset', 120, ...
        'sampleRate', 10000 ...
    ), ...

    % Data
    'data', [stimulus_trace], ...     % Reconstructed or pre-computed waveform
                                      % May be empty — MATLAB auto-reconstructs
                                      % from stimulus_id + stimulus_parameters

    % Metadata
    'sample_rate', 10000, ...         % Hz
    'units', 'normalized' ...         % Units of 'data' field
);
```

**Stimulus reconstruction:** When `data` is empty and `stimulus_id` is present,
`epicTreeTools.getStimulusByName()` auto-reconstructs the waveform using
`epicStimulusGenerators.generateStimulus(stimulus_id, stimulus_parameters)`.
This is transparent to callers — they always get a populated `data` field back.

**Note:** `stimulus_id` is the Symphony generator class name (e.g.,
`edu.washington.riekelab.stimuli.GaussianNoiseGeneratorV2`), NOT the protocol
name. The protocol name (e.g., `VariableMeanNoise`) is stored in `epoch_block.protocol_name`.

## DataJoint Database Schema (Stimulus Table)

The DataJoint `Stimulus` table stores metadata needed for waveform reconstruction:

```sql
CREATE TABLE stimulus (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    h5_uuid         VARCHAR(255) NOT NULL,
    parent_id       INT NOT NULL,           -- FK to epoch.id
    device_name     VARCHAR(255) NOT NULL,
    h5path          VARCHAR(511) NOT NULL,
    stimulus_id     VARCHAR(255) DEFAULT NULL,   -- Symphony generator class name
    sample_rate     VARCHAR(255) DEFAULT NULL,   -- e.g. '10000.0'
    sample_rate_units VARCHAR(255) DEFAULT NULL, -- e.g. 'Hz'
    duration_seconds VARCHAR(255) DEFAULT NULL,  -- e.g. '0.75'
    units           VARCHAR(255) DEFAULT NULL    -- e.g. 'A', 'V'
);
```

**Field mapping** (JSON metadata key → DB column):

| DB Column | JSON Key | Example Value |
|-----------|----------|---------------|
| `h5_uuid` | `uuid` | `db89fd05-2b19-4e28-95b6-40978a026f2f` |
| `stimulus_id` | `stimulusID` | `symphonyui.builtin.stimuli.DirectCurrentGenerator` |
| `sample_rate` | `sampleRate` | `10000.0` |
| `sample_rate_units` | `sampleRateUnits` | `Hz` |
| `duration_seconds` | `durationSeconds` | `0.75` |
| `units` | `units` | `A` |

The `stimulus_id` column is nullable — Stage-based spatial stimuli have no generator class.

**Data flow:**

```
H5 file attributes (stimulusID, parameters/*)
  → RetinAnalysis JSON metadata (stimulusID, sampleRate, sampleRateUnits, durationSeconds, units)
    → DataJoint Stimulus table (stimulus_id, sample_rate, etc.) via append_stimulus() + build_tuple()
      → Python export (stimulus_id + stimulus_parameters in .mat) via build_stimulus_struct()
        → MATLAB auto-reconstruction (epicStimulusGenerators.generateStimulus())
```

**Note:** `stimulus_parameters` (generator-specific params like `seed`, `freqCutoff`, `numFilters` for noise generators) come from the H5 `parameters` sub-group. These are included in the `.mat` export via `build_stimulus_struct()` but are NOT currently stored in the DataJoint Stimulus table (which only has the 5 metadata columns above). Full noise reconstruction via the DataJoint path requires the `.mat` export to include these parameters from the H5 file.

## Example: Loading in EpicTreeGUI Backend

```matlab
function epicTreeGUI_loadData()
    % Load data from standard format
    [file, path] = uigetfile('*.mat', 'Select EpicTree Data');
    if file == 0
        return;
    end

    % Load the data
    data = load(fullfile(path, file));

    % Validate format version
    if ~isfield(data, 'format_version')
        error('Invalid data format: missing format_version');
    end

    % Now we have standardized data - backend doesn't care where it came from!
    experiments = data.experiments;

    % Build tree structure for GUI
    for i = 1:length(experiments)
        exp = experiments(i);
        % Process each experiment...
        for j = 1:length(exp.cells)
            cell = exp.cells(j);
            % Process each cell...
            for k = 1:length(cell.epoch_groups)
                epoch_group = cell.epoch_groups(k);
                % Process epochs...
            end
        end
    end
end
```

## Example: Exporting from DataJoint + H5

```python
#!/usr/bin/env python3
"""
Export DataJoint query results to EpicTreeGUI standard format
"""

import datajoint as dj
import h5py
import scipy.io
from datetime import datetime
from helpers.query import create_query, generate_tree, get_options

def export_to_epictree_format(query_obj, output_file, username='user'):
    """
    Export DataJoint query to EpicTreeGUI standard format.

    Args:
        query_obj: DataJoint query object
        output_file: Output .mat file path
        username: Database username
    """

    # Connect and query
    db = dj.VirtualModule('schema.py', 'schema')
    query = create_query(query_obj, username, db)
    results = generate_tree(query, exclude_levels=[], include_meta=True)

    # Build standard format structure
    experiments = []

    for exp_node in results:
        experiment = {
            'id': exp_node['id'],
            'exp_name': exp_node['object'][0]['exp_name'],
            'is_mea': bool(exp_node['is_mea']),
            'label': exp_node.get('label', ''),
            'cells': []
        }

        # Process cells
        for cell_node in exp_node['children']:
            cell = {
                'id': cell_node['id'],
                'label': cell_node.get('label', ''),
                'type': cell_node['object'][0].get('type', ''),
                'epoch_groups': []
            }

            # Process epoch groups
            for eg_node in cell_node['children']:
                epoch_group = {
                    'id': eg_node['id'],
                    'protocol_name': eg_node.get('protocol', ''),
                    'epoch_blocks': []
                }

                # Process epoch blocks
                for eb_node in eg_node['children']:
                    epoch_block = {
                        'id': eb_node['id'],
                        'protocol_name': eb_node.get('protocol', ''),
                        'epochs': []
                    }

                    # Process epochs
                    for epoch_node in eb_node['children']:
                        epoch = build_epoch_data(epoch_node, experiment['id'])
                        epoch_block['epochs'].append(epoch)

                    epoch_group['epoch_blocks'].append(epoch_block)

                cell['epoch_groups'].append(epoch_group)

            experiment['cells'].append(cell)

        experiments.append(experiment)

    # Create final data structure
    export_data = {
        'format_version': '1.0',
        'metadata': {
            'created_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'data_source': 'DataJoint + H5 files',
            'export_user': username
        },
        'experiments': experiments
    }

    # Save to .mat file
    scipy.io.savemat(output_file, export_data, do_compression=True)
    print(f"Exported to {output_file}")

def build_epoch_data(epoch_node, experiment_id):
    """
    Extract epoch data including responses and stimuli from H5 files.
    """
    epoch_id = epoch_node['id']

    # Get H5 paths for this epoch
    options = get_options('epoch', epoch_id, experiment_id)

    epoch = {
        'id': epoch_id,
        'label': epoch_node.get('label', ''),
        'parameters': epoch_node['object'][0].get('parameters', {}),
        'responses': [],
        'stimuli': []
    }

    if options:
        # Process responses
        for response_data in options.get('responses', []):
            h5_file = response_data['h5_file']
            h5_path = response_data['h5_path']

            # Extract data from H5
            with h5py.File(h5_file, 'r') as f:
                data = f[h5_path]['data']['quantity'][:]

            response = {
                'device_name': response_data['label'],
                'data': data,
                'sample_rate': 10000  # Get from H5 metadata if available
            }
            epoch['responses'].append(response)

        # Process stimuli similarly
        for stimulus_data in options.get('stimuli', []):
            h5_file = stimulus_data['h5_file']
            h5_path = stimulus_data['h5_path']

            with h5py.File(h5_file, 'r') as f:
                data = f[h5_path]['data']['quantity'][:]

            stimulus = {
                'device_name': stimulus_data['label'],
                'data': data,
                'sample_rate': 10000
            }
            epoch['stimuli'].append(stimulus)

    return epoch

# Usage example
if __name__ == '__main__':
    query_obj = {
        'experiment': {'COND': {'type': 'COND', 'value': 'exp_name="20250115A"'}},
        'cell': {'COND': {'type': 'COND', 'value': 'type="OnP"'}},
    }

    export_to_epictree_format(query_obj, 'epictree_data.mat')
```

## Benefits of This Architecture

### 1. **Flexibility in Data Sources**
- Can swap out DataJoint for direct H5 reading
- Can add new data sources (cloud storage, different databases)
- Backend never needs to change

### 2. **Version Control**
- `format_version` field allows backward compatibility
- Can evolve format while supporting old files

### 3. **Testability**
- Easy to create synthetic data files for testing
- Can validate export without full database

### 4. **Portability**
- .mat files can be shared without database access
- Self-contained analysis packages

### 5. **Analysis Isolation**
- Analysis code only depends on data structure, not data source
- Can develop analysis offline with sample data

## Migration Path

### Phase 1: Define and Validate Format
1. Finalize this specification
2. Create sample .mat file with all fields
3. Test loading in MATLAB

### Phase 2: Implement Export
1. Create Python export script (see example above)
2. Test with subset of data
3. Validate all fields are populated correctly

### Phase 3: Update EpicTreeGUI Backend
1. Update `loadData()` function to read standard format
2. Build tree from standardized structure
3. Ensure all analysis functions work with new format

### Phase 4: Production
1. Export full datasets to standard format
2. Deprecate direct H5/database access in GUI
3. All analysis uses standard format files

## Format Extensions

Future versions can add fields without breaking compatibility:

```matlab
% v1.1 might add:
experiment.extended_metadata = struct(...);
cell.morphology_data = struct(...);
epoch.online_analysis = struct(...);
```

Old code will still work, just ignoring new fields.

## Validation

Create a validation function to check format compliance:

```matlab
function valid = validateEpicTreeData(data)
    valid = true;

    % Check required top-level fields
    if ~isfield(data, 'format_version')
        warning('Missing format_version');
        valid = false;
    end

    if ~isfield(data, 'experiments')
        warning('Missing experiments array');
        valid = false;
        return;
    end

    % Check each experiment
    for i = 1:length(data.experiments)
        exp = data.experiments(i);
        if ~isfield(exp, 'id') || ~isfield(exp, 'cells')
            warning('Experiment %d missing required fields', i);
            valid = false;
        end
    end

    % Add more validation as needed...
end
```

## Summary

This specification creates a **clean interface** between:
- **Frontend** (data acquisition/packaging) - can change freely
- **Backend** (visualization/analysis) - remains stable

The standard format is the **contract** that ensures they work together regardless of how the data source evolves.
