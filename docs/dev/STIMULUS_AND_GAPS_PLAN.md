# Planning Document: Stimulus Reconstruction & Data Access Unification

> **STATUS (2026-02-17):** Core implementation COMPLETE. See "Implementation Status" section at the end for details.

## Executive Summary

After deep-diving the legacy Java code, the H5 file structure, the Python DataJoint export pipeline, and our current MATLAB codebase, the picture is clear:

**Stimulus waveforms are never stored anywhere** — not in H5 files, not in the DataJoint database, not in MAT files. The H5 `stimuli/` group contains only attributes (stimulus_id, parameters, sampleRate, duration). The DataJoint `Stimulus` table stores only `(device_name, h5path)`. The MAT export builds a struct with `(device_name, stimulus_id, parameters, duration_seconds, units)`. Nobody stores the actual waveform.

The legacy Java system solved this with `riekesuite.getStimulusVector()` which instantiated the generator class from `stimulus_id`, fed it the stored parameters, and called `generate()`. We need to replicate this — but we can do it better by making it a natural part of our data access layer rather than a separate function.

This document covers:
1. **The data access problem** — how response and stimulus data flow differently
2. **Stimulus reconstruction** — porting the generator system
3. **Unified `getSelectedData` redesign** — the one function to rule them all
4. **DataJoint front-end integration** — where reconstruction should happen
5. **Remaining gaps** — per-epoch metadata, node custom persistence

---

## 1. The Data Access Problem

### Two Asymmetric Paths

Response and stimulus data take fundamentally different paths:

```
RESPONSE DATA (lazy-loaded):
  H5 file → resp.h5_path → h5read() → double[]
  Already works via getResponseFromEpoch() → getResponseMatrix() → getSelectedData()

STIMULUS DATA (reconstructed):
  H5 file → stim attributes → stimulus_id + parameters → generator.generate() → double[]
  COMPLETELY MISSING. stimuliByStreamName() returns []. getLinearFilterAndPrediction() gets [].
```

### What Each Layer Stores

| Layer | Response | Stimulus |
|-------|----------|----------|
| **H5 file** | `data/quantity` dataset (actual waveform) | NO data. Only attributes: stimulusID, parameters/*, sampleRate, units |
| **DataJoint DB** | `h5path` pointing to H5 dataset | `h5path` pointing to H5 group (no data there) |
| **Python export** | `build_response_struct()` → `{data: [], h5_path: ...}` | `build_stimulus_struct()` → `{data: [], h5_path: ...}` |
| **MAT file** | `{data: [], h5_path: '/...', sample_rate: 10000}` | `{device_name, stimulus_id, parameters, duration_seconds, units}` |
| **MATLAB runtime** | H5 lazy load fills `data` field | **NOTHING** — needs reconstruction |

### The Python Export Gap

The `build_stimulus_struct()` in `field_mapper.py` (line 303-321) creates:
```python
{
    'device_name': ...,
    'data': [],          # Always empty
    'h5_path': ...,      # Points to H5 group with only attributes
    'h5_file': ...,
    'sample_rate': ...,
    'units': ...
}
```

But critically, it does NOT extract `stimulus_id` or `parameters` from the H5 file. Those fields only appear in the MAT file when data is loaded directly from H5 (the non-DataJoint path via `loadEpicTreeData` parsing the H5 structure). The DataJoint export path loses the stimulus_id and parameters entirely.

**This means: the DataJoint export path currently cannot support stimulus reconstruction at all.** The fix must happen in `build_stimulus_struct()` — it needs to read the H5 attributes at the stimulus h5path to extract stimulus_id and parameters.

### Two Data Source Paths

```
Path A: H5-direct (current test data)
  loadEpicTreeData() reads H5 file structure directly
  → epoch.stimuli{1}.stimulus_id = 'edu.washington.riekelab.stimuli.GaussianNoiseGeneratorV2'
  → epoch.stimuli{1}.parameters = struct(seed=..., stDev=..., freqCutoff=..., ...)
  → RECONSTRUCTION IS POSSIBLE ✓

Path B: DataJoint export
  export_to_mat() → build_stimulus_struct()
  → epoch.stimuli{1}.device_name = 'UV LED'
  → epoch.stimuli{1}.data = []
  → epoch.stimuli{1}.h5_path = '/experiment-.../stimuli/UV LED-...'
  → NO stimulus_id, NO parameters
  → RECONSTRUCTION IS IMPOSSIBLE ✗ (without fixing the export)
```

---

## 2. Stimulus Reconstruction System

### The Two Classes of Stimuli

From the real data (2025-12-02_F.mat):

**Waveform stimuli** — the generator IS the stimulus:
| Protocol | stimulus_id | Device | Must Reconstruct |
|---|---|---|---|
| VariableMeanNoise | `edu.washington.riekelab.stimuli.GaussianNoiseGeneratorV2` | UV LED | **YES — critical for STA/LN analysis** |

**Parametric stimuli** — the generator is just the holding current:
| Protocol | stimulus_id | Device | What It Actually Is |
|---|---|---|---|
| SingleSpot | `symphonyui.builtin.stimuli.DirectCurrentGenerator` | Amp1 | Amplifier holding signal (0 pA DC) |
| ExpandingSpots | `symphonyui.builtin.stimuli.DirectCurrentGenerator` | Amp1 | Same |
| SplitFieldCentering | `symphonyui.builtin.stimuli.DirectCurrentGenerator` | Amp1 | Same |

For parametric stimuli, reconstructing the `DirectCurrentGenerator` gives you a flat line — useless. The actual light stimulus is described by protocol parameters (preTime, stimTime, tailTime, spotIntensity, backgroundIntensity). A separate `reconstructLightStimulus()` function handles this.

### Generator Implementation

Port the exact algorithms from `jauimodel64/` with all Symphony.Core/.NET wrapping stripped:

```
src/stimuli/
├── StimulusGenerator.m              % Base class: accepts struct, returns double[]
├── PulseGenerator.m                 % preTime/stimTime/tailTime/amplitude/mean
├── SineGenerator.m                  % + period/phase
├── SquareGenerator.m                % + period/phase
├── RampGenerator.m                  % linear ramp
├── PulseTrainGenerator.m            % + numPulses/increments
├── DirectCurrentGenerator.m         % constant offset (time/offset)
├── GaussianNoiseGeneratorV2.m       % FFT-filtered noise (V2 — corrected)
├── GaussianNoiseGenerator.m         % V1 (legacy compat, different FFT)
├── BinaryNoiseGenerator.m           % segmented binary noise
└── WaveformGenerator.m              % stored waveform passthrough
```

Key differences from legacy generators:
- Accept **struct** not `containers.Map` (our epochs use structs)
- Return **double[]** directly not Symphony.Core.Stimulus
- No Symphony.Core imports, no .NET interop, no Measurement wrapping
- Same math, same RNG seeding → bit-exact reconstruction

### Reconstruction Dispatcher

Static method on epicTreeTools:

```matlab
function [data, sampleRate] = reconstructStimulus(epoch, deviceName)
    % RECONSTRUCTSTIMULUS Reconstruct stimulus waveform from stored parameters
    %
    % Two-level lookup:
    %   1. If stim.data exists and is non-empty → return it directly
    %   2. If stim.stimulus_id exists → instantiate generator, call generate()
    %   3. If neither → return []
    %
    % This parallels getResponseFromEpoch() — same interface, different source.

    stim = epicTreeTools.getStimulusByName(epoch, deviceName);
    if isempty(stim), data = []; sampleRate = []; return; end

    % Already has data (future: Python pre-reconstruction, or WaveformGenerator)
    if isfield(stim, 'data') && ~isempty(stim.data)
        data = stim.data(:)';
        sampleRate = [];
        if isfield(stim, 'sample_rate'), sampleRate = stim.sample_rate; end
        return;
    end

    % Reconstruct from generator
    if ~isfield(stim, 'stimulus_id') || isempty(stim.stimulus_id)
        data = []; sampleRate = []; return;
    end

    stimId = char(stim.stimulus_id);
    params = stim.parameters;

    % Extract sample rate from params or stim struct
    sampleRate = [];
    if isfield(params, 'sampleRate'), sampleRate = params.sampleRate; end
    if isempty(sampleRate) && isfield(stim, 'sample_rate'), sampleRate = stim.sample_rate; end

    % Strip package prefix: 'edu.washington.riekelab.stimuli.GaussianNoiseGeneratorV2' → 'GaussianNoiseGeneratorV2'
    parts = strsplit(stimId, '.');
    className = parts{end};

    if exist(className, 'class') == 8  % 8 = class exists on path
        try
            gen = feval(className, params);
            data = gen.generate();
            data = data(:)';
        catch ME
            warning('epicTreeTools:GeneratorFailed', ...
                'Generator %s failed: %s', className, ME.message);
            data = [];
        end
    else
        warning('epicTreeTools:UnknownGenerator', ...
            'No generator class found for: %s (looked for %s)', stimId, className);
        data = [];
    end
end
```

### Light Stimulus Reconstruction

For parametric protocols where the stored stimulus is just DC holding current:

```matlab
function [data, sampleRate] = reconstructLightStimulus(epoch)
    % RECONSTRUCTLIGHTSTIMULUS Build light waveform from protocol parameters
    %
    % For protocols like SingleSpot, ExpandingSpots, Gratings where the
    % visual stimulus is described parametrically. Returns a step function
    % [background → intensity → background] with correct timing.

    params = epicTreeTools.getParams(epoch);
    if isempty(params), data = []; sampleRate = []; return; end

    % Required: timing and sample rate
    if ~isfield(params, 'sampleRate') || ~isfield(params, 'preTime') || ~isfield(params, 'stimTime')
        data = []; sampleRate = []; return;
    end

    sampleRate = params.sampleRate;
    timeToPts = @(t) round(t / 1e3 * sampleRate);
    prePts = timeToPts(params.preTime);
    stimPts = timeToPts(params.stimTime);
    tailPts = 0;
    if isfield(params, 'tailTime'), tailPts = timeToPts(params.tailTime); end

    % Background level
    bg = 0;
    if isfield(params, 'backgroundIntensity'), bg = params.backgroundIntensity; end

    % Stimulus intensity — check several common parameter names
    intensity = bg;
    intensityFields = {'spotIntensity', 'contrast', 'amplitude', 'intensity', 'ledIntensity'};
    for i = 1:length(intensityFields)
        if isfield(params, intensityFields{i})
            intensity = params.(intensityFields{i});
            break;
        end
    end

    data = ones(1, prePts + stimPts + tailPts) * bg;
    data(prePts+1 : prePts+stimPts) = intensity;
end
```

---

## 3. Unified `getSelectedData` Redesign

### Current Signature

```matlab
[dataMatrix, selectedEpochs, sampleRate] = getSelectedData(treeNodeOrEpochs, streamName, h5_file)
```

This only returns response data. The stimulus gap means every analysis function that needs both (STA, linear filter, LN model, etc.) has to separately reconstruct stimuli — and currently can't.

### Proposed Redesign

```matlab
[dataMatrix, selectedEpochs, sampleRate, stimMatrix] = getSelectedData(treeNodeOrEpochs, streamName, h5_file)
```

**4th output `stimMatrix`** — only computed when `nargout >= 4`. This is the stimulus matrix aligned row-for-row with the response matrix:

```matlab
% Inside getSelectedData, after building dataMatrix:
if nargout >= 4
    stimMatrix = zeros(size(dataMatrix));
    for i = 1:length(selectedEpochs)
        [stimData, ~] = epicTreeTools.reconstructStimulus(selectedEpochs{i}, streamName);
        if ~isempty(stimData)
            nS = min(length(stimData), size(stimMatrix, 2));
            stimMatrix(i, 1:nS) = stimData(1:nS);
        end
    end
end
```

**Stream name resolution for stimuli:**

Here's a subtlety. For noise protocols, the response stream is `'Amp1'` but the stimulus stream is `'UV LED'`. When you call `getSelectedData(node, 'Amp1')`, the 4th output needs to find the stimulus — but it's on a different device.

Resolution strategy:
1. First try `reconstructStimulus(epoch, streamName)` — same device name
2. If empty, try each stimulus device in the epoch — there's usually only one non-DC stimulus
3. If the stimulus_id is `DirectCurrentGenerator`, skip it and try `reconstructLightStimulus()` instead

```matlab
if nargout >= 4
    stimMatrix = zeros(size(dataMatrix));
    for i = 1:length(selectedEpochs)
        ep = selectedEpochs{i};

        % Try direct device match first
        [stimData, ~] = epicTreeTools.reconstructStimulus(ep, streamName);

        % If empty or DC, look for actual stimulus on other devices
        if isempty(stimData) || epicTreeTools.isDCStimulus(ep, streamName)
            stimData = epicTreeTools.findBestStimulus(ep);
        end

        if ~isempty(stimData)
            nS = min(length(stimData), size(stimMatrix, 2));
            stimMatrix(i, 1:nS) = stimData(1:nS);
        end
    end
end
```

Where `findBestStimulus` implements the search:
```matlab
function [data, sampleRate, deviceName] = findBestStimulus(epoch)
    % Try all stimulus devices, prefer non-DC generators
    if ~isfield(epoch, 'stimuli'), data = []; return; end

    stimuli = epoch.stimuli;
    if iscell(stimuli), items = stimuli;
    elseif isstruct(stimuli), items = num2cell(stimuli);
    else data = []; return;
    end

    for i = 1:length(items)
        s = items{i};
        if isfield(s, 'stimulus_id')
            stimId = char(s.stimulus_id);
            if ~contains(stimId, 'DirectCurrentGenerator')
                % Found a non-DC stimulus — reconstruct it
                [data, sampleRate] = epicTreeTools.reconstructStimulus(epoch, s.device_name);
                deviceName = s.device_name;
                return;
            end
        end
    end

    % All stimuli are DC — fall back to parametric light stimulus
    [data, sampleRate] = epicTreeTools.reconstructLightStimulus(epoch);
    deviceName = 'light';
end
```

### Why This Design

The key insight is that **the caller shouldn't have to know about stimulus device names or generator classes.** When you ask for `getSelectedData(node, 'Amp1')`, you want the response on Amp1 and whatever stimulus drove it. The system should figure out that the noise on 'UV LED' is the stimulus for the 'Amp1' response.

This mirrors how the legacy system worked — `epochList.dataMatrix('Amp1')` for responses, and the MATLAB wrapper functions figured out the stimulus separately. We're just making it one call.

### Parallel Standalone Functions

For users who want explicit control:

```matlab
% Response matrix (existing — no change)
[respMatrix, sampleRate] = epicTreeTools.getResponseMatrix(epochList, 'Amp1', h5_file)

% Stimulus matrix (NEW — parallel to getResponseMatrix)
[stimMatrix, sampleRate] = epicTreeTools.getStimulusMatrix(epochList, 'UV LED')

% Single-epoch reconstruction (NEW)
[stimData, sampleRate] = epicTreeTools.reconstructStimulus(epoch, 'UV LED')
[lightData, sampleRate] = epicTreeTools.reconstructLightStimulus(epoch)
```

---

## 4. DataJoint Front-End Integration

### The Problem

The DataJoint export currently loses stimulus reconstruction info:

```python
# field_mapper.py line 303-321
def build_stimulus_struct(stim_dict, h5_file):
    return {
        'device_name': stim_dict.get('device_name', ''),
        'data': [],              # Always empty
        'h5_path': stim_dict.get('h5path', ''),
        'h5_file': h5_file,
        'sample_rate': ...,
        'units': ...
        # MISSING: stimulus_id, parameters
    }
```

The DataJoint `Stimulus` table only stores `(h5_uuid, parent_id, device_name, h5path)`. No stimulus_id, no parameters.

### Where Should Reconstruction Happen?

Three options:

**Option A: MATLAB-side H5 read (recommended)**
When MATLAB encounters a stimulus with no `stimulus_id` field but a valid `h5_path`, read the H5 attributes at that path to get the stimulus_id and parameters, then reconstruct.

```matlab
function [data, sampleRate] = reconstructStimulus(epoch, deviceName)
    stim = epicTreeTools.getStimulusByName(epoch, deviceName);

    % If no stimulus_id, try reading from H5
    if ~isfield(stim, 'stimulus_id') || isempty(stim.stimulus_id)
        if isfield(stim, 'h5_path') && ~isempty(stim.h5_path)
            stim = epicTreeTools.enrichStimulusFromH5(stim, epoch);
        end
    end

    % ... proceed with reconstruction
end

function stim = enrichStimulusFromH5(stim, epoch)
    % Read stimulus_id and parameters from H5 file attributes
    h5file = '';
    if isfield(stim, 'h5_file'), h5file = stim.h5_file; end
    if isempty(h5file) && isfield(epoch, 'h5_file'), h5file = epoch.h5_file; end
    if isempty(h5file), return; end

    try
        stim.stimulus_id = h5readatt(h5file, stim.h5_path, 'stimulusID');
        stim.sample_rate = h5readatt(h5file, stim.h5_path, 'sampleRate');

        % Read parameters from subgroup
        paramPath = [stim.h5_path '/parameters'];
        info = h5info(h5file, paramPath);
        params = struct();
        for i = 1:length(info.Attributes)
            attr = info.Attributes(i);
            params.(attr.Name) = attr.Value;
        end
        stim.parameters = params;
    catch
        % H5 read failed — can't reconstruct
    end
end
```

**Pros:** No Python changes needed. Works with existing DataJoint exports. Falls through gracefully.
**Cons:** Requires H5 file to be accessible at MATLAB runtime (already required for response data anyway).

**Option B: Fix the Python export**
Add stimulus_id and parameters to `build_stimulus_struct()` by reading them from the H5 file during export.

```python
def build_stimulus_struct(stim_dict, h5_file):
    result = {
        'device_name': stim_dict.get('device_name', ''),
        'data': [],
        'h5_path': stim_dict.get('h5path', ''),
        'h5_file': h5_file if h5_file else '',
        'sample_rate': parse_sample_rate(stim_dict.get('sample_rate')),
        'units': stim_dict.get('units', 'normalized'),
    }

    # Enrich with stimulus_id and parameters from H5
    if h5_file and result['h5_path']:
        try:
            import h5py
            with h5py.File(h5_file, 'r') as f:
                stim_group = f[result['h5_path']]
                result['stimulus_id'] = stim_group.attrs.get('stimulusID', '')
                if 'parameters' in stim_group:
                    params = {}
                    for key, val in stim_group['parameters'].attrs.items():
                        params[key] = val
                    result['parameters'] = params
        except Exception:
            pass

    return result
```

**Pros:** MAT file becomes self-contained. No H5 needed at MATLAB runtime for stimulus info.
**Cons:** Requires Python pipeline change. Existing exports won't retroactively have the data.

**Option C: Reconstruct in Python, store waveform**
Generate the stimulus waveform in Python during export and store it in the `data` field.

**Pros:** MATLAB gets the waveform directly, no generators needed.
**Cons:** Massive. Requires porting all generators to Python. Inflates MAT file size. Defeats the purpose of parametric storage.

### Recommendation: Option A + B

Do **both**:
1. **Option A (MATLAB-side)** — immediate fix, works with all existing data
2. **Option B (Python export)** — fix `build_stimulus_struct()` so future exports are self-contained

The MATLAB-side fallback (Option A) handles the case where:
- Old DataJoint exports lack stimulus_id/parameters
- H5 file is available (which it must be anyway for response lazy loading)

The Python fix ensures that new exports carry the stimulus metadata, reducing H5 dependency.

### DataJoint Schema Consideration

Long-term, the `Stimulus` table should store stimulus_id and parameters:

```python
class Stimulus(dj.Manual):
    definition = """
    id: int auto_increment
    ---
    h5_uuid: varchar(255)
    -> Epoch.proj(parent_id='id')
    device_name: varchar(255)
    h5path: varchar(511)
    stimulus_id = NULL : varchar(511)     # NEW: generator class name
    parameters = NULL : longblob          # NEW: JSON parameters
    """
```

But this is a schema migration — defer until the current system is working. The H5 fallback covers it.

---

## 5. Fixing Broken Methods

### `stimuliByStreamName()` (line 1013-1052)

Currently checks `isfield(stim, 'data')` which doesn't exist. Replace with `reconstructStimulus`:

```matlab
function dataMatrix = stimuliByStreamName(obj, streamName)
    epochs = obj.epochList;
    if isempty(epochs), dataMatrix = []; return; end

    % Get first stimulus to determine size
    [firstData, ~] = epicTreeTools.reconstructStimulus(epochs{1}, streamName);
    if isempty(firstData), dataMatrix = []; return; end

    nSamples = length(firstData);
    nEpochs = length(epochs);
    dataMatrix = zeros(nEpochs, nSamples);
    dataMatrix(1, :) = firstData;

    for i = 2:nEpochs
        [data, ~] = epicTreeTools.reconstructStimulus(epochs{i}, streamName);
        if ~isempty(data)
            if length(data) ~= nSamples
                error('epicTreeTools:InconsistentLength', ...
                    'Inconsistent stimulus length in epoch %d (was %d, expected %d).', ...
                    i, length(data), nSamples);
            end
            dataMatrix(i, :) = data;
        end
    end
end
```

### `getLinearFilterAndPrediction()` (line 3433-3444)

Replace the broken stimulus extraction:

```matlab
% BEFORE (broken — stim.data doesn't exist):
stimMatrix = zeros(size(respMatrix));
for i = 1:result.n
    stim = epicTreeTools.getStimulusByName(epochs{i}, stimStreamName);
    if ~isempty(stim) && isfield(stim, 'data')
        data = stim.data(:)';
        ...

% AFTER (uses reconstruction):
stimMatrix = zeros(size(respMatrix));
for i = 1:result.n
    [stimData, ~] = epicTreeTools.reconstructStimulus(epochs{i}, stimStreamName);
    if isempty(stimData)
        % Try finding best stimulus (non-DC) on other devices
        [stimData, ~] = epicTreeTools.findBestStimulus(epochs{i});
    end
    if ~isempty(stimData)
        data = stimData(:)';
        if length(data) >= size(stimMatrix, 2)
            stimMatrix(i, :) = data(1:size(stimMatrix, 2));
        else
            stimMatrix(i, 1:length(data)) = data;
        end
    end
end
```

---

## 6. Remaining Gaps

### Per-Epoch User Metadata (Priority: Low)

Java allowed `epoch.setProtocolSetting("user:myTag", value)`. We could add:
- `userProperties` field on epoch structs
- `setEpochProperty(tree, epochIndex, key, value)` instance method (updates root.allEpochs + leaf epochList)
- Persist in .ugm file alongside selection mask

**Defer until users request it.** Node-level `putCustom()` covers most analysis result storage.

### Node Custom Data Persistence (Priority: Medium)

When the tree is rebuilt, `putCustom()` data is lost. Fix by saving custom data in .ugm:

```matlab
% In saveUserMetadata:
ugm.nodeCustomData = obj.collectCustomData();
% Map of pathString → custom struct (excluding display/selection state)

% In loadUserMetadata, after building tree:
obj.restoreCustomData(ugm.nodeCustomData);
% Match by pathString (splitKey:splitValue chain from root)
```

Only works when same splitters are used — acceptable (same limitation as Java serialized trees).

### Stream Name Robustness (Priority: Already Done)

`getStreamNames()` (line 1936-1979) already scans ALL epochs and returns the union. No fix needed. This is better than the Java version which only checked `firstValue()`.

---

## 7. Implementation Order

### Phase 1: Generator Framework + Core Reconstruction
1. Create `src/stimuli/StimulusGenerator.m` base class
2. Port all 10 generator classes (strip Symphony/.NET)
3. Add `reconstructStimulus()` static method to epicTreeTools
4. Add `enrichStimulusFromH5()` for DataJoint export fallback
5. Add `reconstructLightStimulus()` for parametric protocols
6. Add `findBestStimulus()` helper
7. **Test:** Verify GaussianNoiseGeneratorV2 is bit-exact with known seed

### Phase 2: Fix Broken Methods
1. Fix `stimuliByStreamName()` — use `reconstructStimulus()`
2. Fix `getLinearFilterAndPrediction()` — use `reconstructStimulus()` + `findBestStimulus()`
3. **Test:** `stimuliByStreamName('UV LED')` returns non-empty on VariableMeanNoise data
4. **Test:** `getLinearFilterAndPrediction()` produces valid filter on noise data

### Phase 3: Unified getSelectedData
1. Add optional 4th output `stimMatrix` to `getSelectedData()`
2. Implement smart stimulus device resolution (skip DC, find actual stimulus)
3. Add `getStimulusMatrix()` static method (parallel to `getResponseMatrix()`)
4. **Test:** `[resp, eps, fs, stim] = getSelectedData(node, 'Amp1')` returns aligned matrices

### Phase 4: Python Export Fix
1. Update `build_stimulus_struct()` in `field_mapper.py` to read H5 attributes
2. Add `stimulus_id` and `parameters` fields to stimulus struct
3. **Test:** Round-trip: DataJoint export → MATLAB load → stimulus reconstruction works

### Phase 5: Node Custom Persistence (if needed)
1. Add `collectCustomData()` / `restoreCustomData()` to epicTreeTools
2. Extend .ugm save/load with nodeCustomData field
3. Version the .ugm format for backward compatibility

---

## 8. Files to Create/Modify

### New Files
```
src/stimuli/StimulusGenerator.m           % Base class
src/stimuli/PulseGenerator.m              % Port from legacy
src/stimuli/SineGenerator.m
src/stimuli/SquareGenerator.m
src/stimuli/RampGenerator.m
src/stimuli/PulseTrainGenerator.m
src/stimuli/DirectCurrentGenerator.m
src/stimuli/GaussianNoiseGeneratorV2.m    % Critical — must be bit-exact
src/stimuli/GaussianNoiseGenerator.m      % V1 legacy compat
src/stimuli/BinaryNoiseGenerator.m
src/stimuli/WaveformGenerator.m
tests/test_stimulus_reconstruction.m      % Validation tests
```

### Modified Files
```
src/tree/epicTreeTools.m
  Static methods (add):
    - reconstructStimulus(epoch, deviceName) → [data, sampleRate]
    - enrichStimulusFromH5(stim, epoch) → stim  (H5 attribute reader)
    - reconstructLightStimulus(epoch) → [data, sampleRate]
    - findBestStimulus(epoch) → [data, sampleRate, deviceName]
    - isDCStimulus(epoch, deviceName) → logical
    - getStimulusMatrix(epochList, streamName) → [matrix, sampleRate]

  Instance methods (fix):
    - stimuliByStreamName(streamName) → use reconstructStimulus

  Static methods (fix):
    - getSelectedData() → add optional 4th output stimMatrix
    - getLinearFilterAndPrediction() → use reconstructStimulus + findBestStimulus

python/field_mapper.py
  - build_stimulus_struct() → read stimulus_id + parameters from H5 attributes

python/export_mat.py
  - No changes needed (build_stimulus_struct handles it)
```

---

## 9. Testing Strategy

### Bit-Exact Generator Validation
```matlab
% Use known parameters from real VariableMeanNoise epoch
params.seed = 142395000;
params.stDev = 1;
params.freqCutoff = 10;
params.numFilters = 4;
params.mean = 0.5;
params.preTime = 0;
params.stimTime = 600;
params.tailTime = 0;
params.sampleRate = 10000;
params.inverted = false;
params.upperLimit = 10.239;
params.lowerLimit = -10.24;
params.units = 'V';

gen = GaussianNoiseGeneratorV2(params);
data = gen.generate();

% Verify: deterministic (same seed → same output)
gen2 = GaussianNoiseGeneratorV2(params);
data2 = gen2.generate();
assert(isequal(data, data2), 'Generator must be deterministic');

% Verify: correct length
expectedPts = round(600 / 1e3 * 10000);  % 6000 pts
assert(length(data) == expectedPts, 'Wrong length');

% Verify: values are in bounds
assert(all(data >= -10.24) && all(data <= 10.239), 'Out of bounds');
```

### End-to-End Integration
```matlab
% Load real data
[treeData, ~] = loadEpicTreeData('/path/to/2025-12-02_F.mat');
tree = epicTreeTools(treeData, 'LoadUserMetadata', 'none');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnProtocol, @epicTreeTools.splitOnCellType});

% Find noise protocol node
noiseNode = tree.childBySplitValue('VariableMeanNoise');

% Test 1: stimuliByStreamName returns non-empty
stimMatrix = noiseNode.stimuliByStreamName('UV LED');
assert(~isempty(stimMatrix), 'stimuliByStreamName should return data');
assert(size(stimMatrix, 1) == noiseNode.epochCount(), 'Row count mismatch');

% Test 2: getSelectedData returns aligned stimulus
noiseNode.setSelected(true, true);
[resp, eps, fs, stim] = epicTreeTools.getSelectedData(noiseNode, 'Amp1', tree.h5File);
assert(size(stim) == size(resp), 'Stimulus and response matrix sizes must match');
assert(any(stim(:) ~= 0), 'Stimulus matrix should not be all zeros');

% Test 3: Linear filter produces valid output
result = epicTreeTools.getLinearFilterAndPrediction(noiseNode, 'UV LED', 'Amp1');
assert(~isempty(result.filter), 'Filter should not be empty');
assert(~isnan(result.correlation), 'Correlation should be computed');
```

---

## 10. Risk Assessment

| Risk | Impact | Mitigation |
|---|---|---|
| GaussianNoiseGeneratorV2 math differs from legacy | High — wrong STA/linear filter | Port code verbatim, test with known seeds, compare if legacy system available |
| Unknown generators in other datasets | Medium — silent failure | Graceful fallback (warning + return []), extensible class registry |
| H5 file not available at MATLAB runtime | Medium — can't enrich DataJoint stim | Fix Python export (Phase 4) to include stimulus_id in MAT file |
| Stimulus/response sample count mismatch | Low — noise stim may have different duration | Pad/truncate to response length (match legacy zero-fill behavior) |
| Performance: reconstruction for large datasets | Low — generators are fast | Cache at node level if needed; lazy nargout-gated computation |
| .ugm format change for custom persistence | Low — backward compat | Version the ugm format, older files load without custom data |
| `findBestStimulus` picks wrong device | Low — most epochs have 1 stimulus | Check device count, warn if ambiguous, let caller override |

---

## 11. Implementation Status (2026-02-17)

### COMPLETED

**Phase 1: Generator Framework** — DONE
- Created `src/stimuli/epicStimulusGenerators.m` (single static class, not individual files)
- 11 generators ported: pulse, repeatingPulse, pulseTrain, sine, square, ramp, directCurrent, gaussianNoise, gaussianNoiseV2, binaryNoise, sumGenerator
- Dispatcher `generateStimulus(stimulusID, params)` maps fully-qualified class names
- Seeded RNG verified: same seed → identical output across calls
- Design choice: single class with static methods (not base class + subclasses) for simplicity

**Phase 2: Fix Broken Methods** — DONE
- `stimuliByStreamName()` — fixed empty data check, uses auto-reconstruction via `getStimulusByName()`
- `getLinearFilterAndPrediction()` — uses `getStimulusMatrix()`, with fallback to per-epoch `getStimulusByName()` + padding/trimming
- `getStimulusByName()` — auto-reconstructs when `.data` is empty but `.stimulus_id` is present

**Phase 3 (partial): Stimulus Matrix** — DONE
- `getStimulusFromEpoch(epoch, deviceName)` — mirrors `getResponseFromEpoch()`
- `getStimulusMatrix(epochs, deviceName)` — mirrors `getResponseMatrix()`

**Phase 4: Python Export + DataJoint Pipeline** — DONE
- `field_mapper.py`: `build_stimulus_struct()` includes `stimulus_id` and `stimulus_parameters`
- DataJoint `schema.py`: 5 new nullable columns on Stimulus table
- DataJoint `utils.py`: New `'stimulus'` field mapping
- DataJoint `pop.py`: `append_stimulus()` uses `build_tuple()` pattern
- End-to-end tested: schema migration, backfill, fresh insert all verified

**Tests** — 19 new tests in `tests/test_stimulus_generators.m`, all passing

### DEFERRED

- `getSelectedData()` 4th output `stimMatrix` — not yet implemented (callers use `getStimulusMatrix()` directly instead)
- `reconstructLightStimulus()` — not needed yet (Stage-based stimuli don't have generator classes)
- `findBestStimulus()` / `isDCStimulus()` — not needed; callers specify stimulus device name explicitly
- `enrichStimulusFromH5()` — not needed; Python export now includes stimulus_id in MAT file
- Node custom persistence (Phase 5) — deferred until users request it

### DESIGN CHANGES FROM PLAN

| Planned | Actual | Reason |
|---|---|---|
| Individual generator class files | Single `epicStimulusGenerators.m` static class | Simpler, no class hierarchy needed for pure math functions |
| `reconstructStimulus()` as separate method | Auto-reconstruction inside `getStimulusByName()` | Transparent to callers — no code changes needed downstream |
| `findBestStimulus()` smart device resolution | Callers specify device name explicitly | User confirmed response device (Amp1) ≠ stimulus device (LED) — no auto-pairing |
| H5 fallback for DataJoint exports | Fix DataJoint pipeline to include stimulus_id | Better: data is self-contained in MAT file, no H5 needed at runtime |
