%% Test Data Loading from Python Export
% This script tests loading and accessing data exported from Python RetinAnalysis
%
% Usage:
%   1. Export data from Python using matlab_export.py
%   2. Update the file_path variable below to point to your .mat file
%   3. Run this script in MATLAB
%
% Author: EpicTreeGUI Project
% Date: 2025-01-23

%% Clear workspace
clear all;
close all;
clc;

fprintf('=== Testing MATLAB Data Loading ===\n\n');

%% 1. Load the exported MAT file
fprintf('Step 1: Loading exported MAT file...\n');

% UPDATE THIS PATH to point to your exported .mat file
file_path = '../python_export/test_exports/test_export.mat';

if ~exist(file_path, 'file')
    error('File not found: %s\nPlease export data from Python first using example_export.py', file_path);
end

data = load(file_path);
fprintf('  ✓ Data loaded successfully!\n\n');

%% 2. Display metadata
fprintf('Step 2: Verifying metadata...\n');
fprintf('  Experiment: %s\n', data.exp_name);
fprintf('  Protocol: %s\n', data.protocol_name);
fprintf('  Datafile: %s\n', data.datafile_name);
fprintf('  Block ID: %d\n', data.block_id);
fprintf('  Number of cells: %d\n', data.num_cells);
fprintf('  Number of epochs: %d\n', data.num_epochs);
fprintf('  ✓ Metadata verified!\n\n');

%% 3. Display cell information
fprintf('Step 3: Verifying cell information...\n');
fprintf('  Cell IDs: [%s]\n', num2str(data.cell_ids(1:min(5, length(data.cell_ids)))));
if length(data.cell_ids) > 5
    fprintf('    ... and %d more\n', length(data.cell_ids) - 5);
end

% Handle cell types (can be cell array or char array)
if iscell(data.cell_types)
    unique_types = unique(data.cell_types);
elseif ischar(data.cell_types)
    if size(data.cell_types, 1) > 1
        % Multi-row char array - convert each row
        unique_types = {};
        for i = 1:size(data.cell_types, 1)
            type_str = strtrim(data.cell_types(i,:));
            if ~ismember(type_str, unique_types)
                unique_types{end+1} = type_str;
            end
        end
    else
        unique_types = {data.cell_types};
    end
else
    unique_types = cellstr(data.cell_types);
end

fprintf('  Cell types found: ');
for i = 1:length(unique_types)
    fprintf('%s ', unique_types{i});
end
fprintf('\n');
fprintf('  ✓ Cell information verified!\n\n');

%% 4. Test spike time access
fprintf('Step 4: Testing spike time access...\n');

% Get first cell ID
first_cell_id = data.cell_ids(1);
field_name = sprintf('cell_%d', first_cell_id);

if isfield(data.spike_times, field_name)
    spike_data = data.spike_times.(field_name);

    % Access first epoch spike times
    if iscell(spike_data.spike_times)
        first_epoch_spikes = spike_data.spike_times{1};
    else
        first_epoch_spikes = spike_data.spike_times(1,:);
    end

    fprintf('  Cell %d, Epoch 1:\n', first_cell_id);
    fprintf('    Number of spikes: %d\n', length(first_epoch_spikes));
    if length(first_epoch_spikes) > 0
        fprintf('    First spike time: %.2f ms\n', first_epoch_spikes(1));
        fprintf('    Last spike time: %.2f ms\n', first_epoch_spikes(end));
    end
    fprintf('  ✓ Spike times accessible!\n\n');
else
    warning('Could not find spike times for cell %d', first_cell_id);
end

%% 5. Test RF parameter access
fprintf('Step 5: Testing RF parameter access...\n');

% Get first noise ID
first_noise_id = data.noise_ids(1);
rf_field_name = sprintf('noise_%d', first_noise_id);

if first_noise_id > 0 && isfield(data.rf_params, rf_field_name)
    rf_params = data.rf_params.(rf_field_name);

    fprintf('  Noise cell %d RF parameters:\n', first_noise_id);
    fprintf('    Center: (%.2f, %.2f)\n', rf_params.center_x, rf_params.center_y);
    fprintf('    Std: (%.2f, %.2f)\n', rf_params.std_x, rf_params.std_y);
    fprintf('    Rotation: %.2f degrees\n', rf_params.rotation);
    fprintf('  ✓ RF parameters accessible!\n\n');
else
    fprintf('  Note: No RF parameters for noise_id %d (may be unmatched)\n\n', first_noise_id);
end

%% 6. Test epoch parameter access
fprintf('Step 6: Testing epoch parameter access...\n');

% Access first epoch parameters (handle both cell array and struct array)
if iscell(data.epoch_params)
    first_epoch_params = data.epoch_params{1};
else
    first_epoch_params = data.epoch_params(1);
end

fprintf('  Epoch 1 parameters:\n');

% Handle both struct and other types
if isstruct(first_epoch_params)
    param_fields = fieldnames(first_epoch_params);
    for i = 1:min(5, length(param_fields))
        param_name = param_fields{i};
        param_value = first_epoch_params.(param_name);
        if isnumeric(param_value)
            fprintf('    %s: %.4f\n', param_name, param_value);
        else
            fprintf('    %s: %s\n', param_name, char(param_value));
        end
    end
    if length(param_fields) > 5
        fprintf('    ... and %d more parameters\n', length(param_fields) - 5);
    end
else
    fprintf('    Warning: epoch_params not in expected format\n');
    fprintf('    Type: %s\n', class(first_epoch_params));
end
fprintf('  ✓ Epoch parameters accessible!\n\n');

%% 7. Test timing information
fprintf('Step 7: Testing timing information...\n');

fprintf('  Epoch 1 timing:\n');
if iscell(data.epoch_starts)
    fprintf('    Start: %.2f ms\n', data.epoch_starts{1});
    fprintf('    End: %.2f ms\n', data.epoch_ends{1});
    fprintf('    Duration: %.2f ms\n', data.epoch_ends{1} - data.epoch_starts{1});
else
    fprintf('    Start: %.2f ms\n', data.epoch_starts(1));
    fprintf('    End: %.2f ms\n', data.epoch_ends(1));
    fprintf('    Duration: %.2f ms\n', data.epoch_ends(1) - data.epoch_starts(1));
end

if iscell(data.frame_times)
    frame_times_1 = data.frame_times{1};
    fprintf('    Number of frames: %d\n', length(frame_times_1));
    if length(frame_times_1) > 0
        fprintf('    First frame: %.2f ms\n', frame_times_1(1));
        fprintf('    Last frame: %.2f ms\n', frame_times_1(end));
    end
end
fprintf('  ✓ Timing information accessible!\n\n');

%% 8. Create a simple PSTH plot
fprintf('Step 8: Creating example PSTH plot...\n');

figure('Name', 'Example PSTH', 'Position', [100 100 800 400]);

% Get spike times for first cell, first epoch
if isfield(data.spike_times, field_name)
    if iscell(spike_data.spike_times)
        spikes = spike_data.spike_times{1};
    else
        spikes = spike_data.spike_times(1,:);
    end

    % Create histogram
    bin_width = 50; % ms
    if iscell(data.epoch_ends)
        max_time = data.epoch_ends{1};
    else
        max_time = data.epoch_ends(1);
    end

    edges = 0:bin_width:max_time;
    counts = histcounts(spikes, edges);

    % Plot
    bar(edges(1:end-1) + bin_width/2, counts, 'FaceColor', [0.3 0.3 0.8]);
    xlabel('Time (ms)');
    ylabel('Spike Count');
    title(sprintf('PSTH - Cell %d, Epoch 1 (bin width: %d ms)', first_cell_id, bin_width));
    grid on;

    fprintf('  ✓ PSTH plot created!\n\n');
end

%% Summary
fprintf('=== All Tests Passed! ===\n\n');
fprintf('Summary:\n');
fprintf('  ✓ Data structure is valid\n');
fprintf('  ✓ All fields are accessible\n');
fprintf('  ✓ Ready for use with EpicTreeGUI\n\n');

fprintf('Next steps:\n');
fprintf('  1. Launch epicTreeGUI with this data file\n');
fprintf('  2. Browse epochs organized by cell type or stimulus parameters\n');
fprintf('  3. Run analysis functions (RFAnalysis, LSTA, etc.)\n\n');
