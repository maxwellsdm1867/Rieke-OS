# Integration Instructions: DataJoint Query + H5 Epoch Data Extraction

This document explains how to combine two tools to query metadata and extract specific epoch data from h5 files.

## Overview

This document describes **Phase 1: Data Extraction** - how to query and extract data from source systems.

For the complete architecture including the standard format interface, see [DATA_FORMAT_SPECIFICATION.md](DATA_FORMAT_SPECIFICATION.md).

### System Components

1. **DataJoint Tool** (`/Users/maxwellsdm/Documents/GitHub/datajoint`) - Queries metadata and points to specific epochs
2. **RetinAnalysis Tool** - Parses h5 files and extracts epoch data
3. **Standard Format Export** - Packages data for EpicTreeGUI (see DATA_FORMAT_SPECIFICATION.md)
4. **EpicTreeGUI Backend** - Visualization and analysis (independent of data source)

## Complete Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DataJoint Query Tool                      │
│  - Queries database for experiments, cells, epochs          │
│  - Returns metadata + h5 file paths + epoch identifiers     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ outputs: h5_file path, h5_path, epoch_id
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    H5 Data Extraction                        │
│  - Uses h5py to read from specific h5_path                  │
│  - Extracts epoch data (spike times, stimulus, etc.)        │
└─────────────────────────────────────────────────────────────┘
```

## Tool 1: DataJoint - Query and Metadata Extraction

### Location
`/Users/maxwellsdm/Documents/GitHub/datajoint/next-app/api/`

### Key Components

#### Database Schema (schema.py)
Hierarchical structure:
```
Experiment
  └─ Animal
      └─ Preparation
          └─ Cell
              └─ EpochGroup
                  └─ EpochBlock
                      └─ Epoch
                          ├─ Response (contains h5_path to response data)
                          └─ Stimulus (contains h5_path to stimulus data)
```

#### Query Functions (helpers/query.py)

**1. Create and Execute Query**
```python
from helpers.query import create_query, generate_tree

# Define query object (example: filter by cell type)
query_obj = {
    'experiment': None,  # No filter on experiment
    'animal': None,
    'preparation': None,
    'cell': {'COND': {'type': 'TAG', 'value': 'cell_type="OnP"'}},
    'epoch_group': None,
    'epoch_block': {'COND': {'type': 'TAG', 'value': 'protocol_name="Contrast"'}},
    'epoch': None
}

# Create the query
query = create_query(query_obj, username='your_username', db_param=db)

# Generate results tree
results = generate_tree(query, exclude_levels=[], include_meta=True)
```

**2. Get H5 File Paths for Specific Epochs**

The `get_options()` function retrieves h5 paths for a specific epoch:

```python
from helpers.query import get_options

# For a specific epoch
epoch_id = 42
experiment_id = 1

options = get_options(level='epoch', id=epoch_id, experiment_id=experiment_id)

# Returns:
# {
#   'responses': [
#     {'label': 'Amp1', 'h5_path': '/epochs/epoch_1/responses/Amp1',
#      'h5_file': '/path/to/data.h5', 'vis_type': 'epoch-singlecell'}
#   ],
#   'stimuli': [
#     {'label': 'Stage', 'h5_path': '/epochs/epoch_1/stimuli/Stage',
#      'h5_file': '/path/to/data.h5', 'vis_type': 'epoch-singlecell'}
#   ]
# }
```

**3. Direct Data Access from H5**

The `get_data_generic()` function directly reads data from h5 files:

```python
from helpers.query import get_data_generic

# Get stimulus data for a specific stimulus ID
stimulus_id = 123
data = get_data_generic(table_name='Stimulus', id=stimulus_id)

# Or for response data
response_id = 456
data = get_data_generic(table_name='Response', id=response_id)
```

This function:
1. Queries the database to get the experiment's h5 file path
2. Gets the h5_path for the specific Response/Stimulus
3. Opens the h5 file and reads from `f[h5_path]['data']['quantity']`

### Database Schema Key Fields

**Experiment Table:**
- `data_file`: Path to h5 file (empty for MEA data)
- `is_mea`: Flag indicating if MEA (1) or patch (0)

**Epoch Table:**
- `id`: Epoch ID
- `parent_id`: Links to EpochBlock
- `parameters`: JSON with epoch-specific parameters
- `start_time`, `end_time`: Timing information

**Response/Stimulus Tables:**
- `h5path`: Path within h5 file to the data (e.g., `/epochs/epoch_1/responses/Amp1`)
- `device_name`: Name of recording device
- `parent_id`: Links to Epoch

## Tool 2: H5 Data Extraction Methods

### Using h5py Directly (from DataJoint code)

```python
import h5py

# Example from query.py:get_data_generic
def extract_epoch_data(h5_file: str, h5_path: str):
    """
    Extract data from specific h5 path.

    Args:
        h5_file: Full path to h5 file (from Experiment.data_file)
        h5_path: Path within h5 file (from Response.h5path or Stimulus.h5path)

    Returns:
        Data array from h5 file
    """
    with h5py.File(h5_file, 'r') as f:
        # Navigate to the data
        data = f[h5_path]['data']['quantity'][:]

        # Optional: get metadata
        if 'metadata' in f[h5_path].keys():
            metadata = dict(f[h5_path]['metadata'].attrs)

        return data
```

### Using RetinAnalysis Pipeline (for MEA data)

Based on the existing [matlab_export.py](new_retinanalysis/src/retinanalysis/utils/matlab_export.py):

```python
import retinanalysis as ra
from retinanalysis.utils.matlab_export import export_pipeline_to_matlab

# Create pipeline from experiment
pipeline = ra.create_mea_pipeline('20250115A', 'data000')

# Access epoch data
epoch_idx = 0
spike_times = pipeline.response_block.df_spike_times

# Get timing information
epoch_start = pipeline.response_block.d_timing['epochStarts'][epoch_idx]
epoch_end = pipeline.response_block.d_timing['epochEnds'][epoch_idx]
frame_times = pipeline.response_block.d_timing['frameTimesMs'][epoch_idx]

# Get stimulus parameters for epoch
epoch_params = pipeline.stim_block.df_epochs.iloc[epoch_idx]['epoch_parameters']
```

## Complete Workflow Example

### Step 1: Query for Specific Epochs

```python
import datajoint as dj
from helpers.query import create_query, generate_tree, get_options

# Connect to database
db = dj.VirtualModule('schema.py', 'schema')

# Query for epochs matching criteria
query_obj = {
    'experiment': {'COND': {'type': 'COND', 'value': 'exp_name="20250115A"'}},
    'epoch_block': {'COND': {'type': 'COND', 'value': 'protocol_name="Contrast"'}},
    # ... other filters
}

query = create_query(query_obj, username='user', db_param=db)
results = generate_tree(query, exclude_levels=[], include_meta=True)
```

### Step 2: Extract Epoch Metadata

```python
# Navigate the results tree to get specific epoch
for experiment in results:
    for animal in experiment['children']:
        for prep in animal['children']:
            for cell in prep['children']:
                for epoch_group in cell['children']:
                    for epoch_block in epoch_group['children']:
                        for epoch in epoch_block['children']:
                            epoch_id = epoch['id']
                            experiment_id = epoch['experiment_id']

                            # Get h5 paths for this epoch
                            options = get_options('epoch', epoch_id, experiment_id)

                            if options:
                                for response in options['responses']:
                                    h5_file = response['h5_file']
                                    h5_path = response['h5_path']

                                    print(f"Epoch {epoch_id}: {h5_file} -> {h5_path}")
```

### Step 3: Extract Actual Data from H5

```python
import h5py
import numpy as np

def extract_epoch_response_data(h5_file: str, h5_path: str):
    """
    Extract response data for a specific epoch.

    Returns:
        dict with 'data', 'sample_rate', and other metadata
    """
    with h5py.File(h5_file, 'r') as f:
        epoch_group = f[h5_path]

        result = {}

        # Get the actual data
        if 'data' in epoch_group:
            result['quantity'] = epoch_group['data']['quantity'][:]

            # Get sample rate if available
            if 'sampleRate' in epoch_group['data'].attrs:
                result['sample_rate'] = epoch_group['data'].attrs['sampleRate']

        # Get any parameters stored in the epoch
        if 'parameters' in epoch_group.attrs:
            result['parameters'] = dict(epoch_group.attrs['parameters'])

        return result

# Usage
data = extract_epoch_response_data(h5_file, h5_path)
spike_trace = data['quantity']
sample_rate = data.get('sample_rate', 10000)  # Default 10kHz
```

## Key Functions Reference

### From datajoint/next-app/api/helpers/query.py

| Function | Purpose | Returns |
|----------|---------|---------|
| `create_query(query_obj, username, db_param)` | Create DataJoint query from filter object | DataJoint query expression |
| `generate_tree(query, exclude_levels, include_meta)` | Execute query and build hierarchical result tree | List of nested dicts |
| `get_options(level, id, experiment_id)` | Get h5 paths for visualization/data access | Dict with h5_file and h5_path lists |
| `get_data_generic(table_name, id)` | Directly read data from h5 for Response/Stimulus | NumPy array from h5 file |
| `get_metadata_helper(level, id)` | Get all metadata for a specific database entry | Dict of metadata fields |

### H5 File Structure (Patch Data)

```
/
├── epochs/
│   ├── epoch_0/
│   │   ├── responses/
│   │   │   └── Amp1/
│   │   │       ├── data/
│   │   │       │   └── quantity (actual voltage/current trace)
│   │   │       └── metadata (attributes)
│   │   └── stimuli/
│   │       └── Stage/
│   │           ├── data/
│   │           │   └── quantity (stimulus trace)
│   │           └── metadata
│   ├── epoch_1/
│   └── ...
```

## Integration Checklist

- [ ] Set up DataJoint connection to database
- [ ] Define query criteria (cell types, protocols, parameters)
- [ ] Execute query to get filtered epochs
- [ ] Extract h5_file and h5_path from results
- [ ] Read epoch data from h5 files using h5py
- [ ] Process/analyze extracted epoch data
- [ ] (Optional) Export to MATLAB format using matlab_export.py

## Notes

- **MEA vs Patch**: MEA data may have empty `data_file` in Experiment table, with data stored in directories referenced by EpochBlock.data_dir
- **Multiple Responses**: Each epoch can have multiple responses (different recording devices) - iterate through all
- **Caching**: DataJoint queries can be cached; h5 file access should be minimized for performance
- **Error Handling**: Always check if h5_path exists in file before accessing
- **Data Types**: Convert numpy arrays to native Python types when exporting (see matlab_export.py)

## Example: Complete Pipeline

```python
#!/usr/bin/env python3
"""
Complete example: Query epochs and extract data
"""

import datajoint as dj
import h5py
import numpy as np
from helpers.query import create_query, generate_tree, get_options

# 1. Connect to database
db = dj.VirtualModule('schema.py', 'schema')

# 2. Define query
query_obj = {
    'experiment': {'COND': {'type': 'COND', 'value': 'exp_name="20250115A"'}},
    'cell': {'COND': {'type': 'COND', 'value': 'type="OnP"'}},
    'epoch_block': {'COND': {'type': 'COND', 'value': 'protocol_name="Contrast"'}},
}

# 3. Execute query
query = create_query(query_obj, username='user', db_param=db)
results = generate_tree(query, exclude_levels=['animal', 'preparation'], include_meta=True)

# 4. Extract data for each epoch
all_epoch_data = []

for exp in results:
    for cell in exp['children']:
        for epoch_group in cell['children']:
            for epoch_block in epoch_group['children']:
                for epoch in epoch_block['children']:
                    # Get h5 info
                    epoch_id = epoch['id']
                    options = get_options('epoch', epoch_id, exp['id'])

                    if not options or not options['responses']:
                        continue

                    # Get first response
                    response = options['responses'][0]
                    h5_file = response['h5_file']
                    h5_path = response['h5_path']

                    # Extract data
                    with h5py.File(h5_file, 'r') as f:
                        data = f[h5_path]['data']['quantity'][:]

                    all_epoch_data.append({
                        'epoch_id': epoch_id,
                        'cell_id': cell['id'],
                        'data': data,
                        'metadata': epoch.get('object', {})
                    })

print(f"Extracted {len(all_epoch_data)} epochs")
```

## Next Step: Export to Standard Format

After extracting epoch data using the methods above, the next step is to **export to the standard EpicTreeGUI format**.

See [DATA_FORMAT_SPECIFICATION.md](DATA_FORMAT_SPECIFICATION.md) for:

- Complete data structure specification
- Example export script from DataJoint → Standard Format
- How EpicTreeGUI backend loads and uses the data
- Architecture ensuring backend isolation from data source changes

## Additional Resources

- **Standard Format Spec**: [DATA_FORMAT_SPECIFICATION.md](DATA_FORMAT_SPECIFICATION.md) - **READ THIS NEXT**
- DataJoint API: [helpers/query.py](../../datajoint/next-app/api/helpers/query.py:296)
- Database Schema: [schema.py](../../datajoint/next-app/api/schema.py:1)
- MATLAB Export: [matlab_export.py](new_retinanalysis/src/retinanalysis/utils/matlab_export.py:1)
- RetinAnalysis Demo: https://github.com/DRezeanu/retinanalysis/blob/dev_vr/demos/4_patchdata_demo.ipynb
