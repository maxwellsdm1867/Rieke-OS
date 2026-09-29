function str = formatEpicNodeData(nodeData)
% FORMATEPICNODEDATA Format node data for display
%
% Usage:
%   str = formatEpicNodeData(nodeData)
%
% Inputs:
%   nodeData - Struct containing 'type' and 'data' fields from tree node
%
% Outputs:
%   str - Cell array of formatted strings for display
%
% Description:
%   Formats node data based on type (experiment, cell, epoch, etc.)
%   for display in the EpicTreeGUI data panel.

    if isempty(nodeData) || ~isfield(nodeData, 'type')
        str = {'No data available'};
        return;
    end

    type = nodeData.type;
    data = nodeData.data;

    switch type
        case 'root'
            str = formatRootData(data);
        case 'experiment'
            str = formatExperimentData(data);
        case 'cell'
            str = formatCellData(data);
        case 'epoch_group'
            str = formatEpochGroupData(data);
        case 'epoch_block'
            str = formatEpochBlockData(data);
        case 'epoch'
            str = formatEpochData(data);
        otherwise
            str = {sprintf('Unknown type: %s', type)};
    end
end

function str = formatRootData(data)
    str = {};
    str{end+1} = '=== DATA OVERVIEW ===';
    str{end+1} = '';
    str{end+1} = sprintf('Format Version: %s', data.format_version);
    str{end+1} = sprintf('Number of Experiments: %d', length(data.experiments));
    str{end+1} = '';
    str{end+1} = 'Select a node to view details';
end

function str = formatExperimentData(exp)
    str = {};
    str{end+1} = '=== EXPERIMENT ===';
    str{end+1} = '';
    str{end+1} = sprintf('ID: %d', exp.id);
    str{end+1} = sprintf('Name: %s', exp.exp_name);
    str{end+1} = sprintf('Label: %s', exp.label);
    str{end+1} = sprintf('Type: %s', ternary(exp.is_mea, 'MEA', 'Patch'));
    str{end+1} = '';

    if ~isempty(exp.experimenter)
        str{end+1} = sprintf('Experimenter: %s', exp.experimenter);
    end
    if ~isempty(exp.rig)
        str{end+1} = sprintf('Rig: %s', exp.rig);
    end
    if ~isempty(exp.institution)
        str{end+1} = sprintf('Institution: %s', exp.institution);
    end
    if ~isempty(exp.lab)
        str{end+1} = sprintf('Lab: %s', exp.lab);
    end

    str{end+1} = '';
    str{end+1} = sprintf('Cells: %d', length(exp.cells));
end

function str = formatCellData(cell)
    str = {};
    str{end+1} = '=== CELL ===';
    str{end+1} = '';
    str{end+1} = sprintf('ID: %d', cell.id);
    str{end+1} = sprintf('Label: %s', cell.label);
    str{end+1} = sprintf('Type: %s', cell.type);
    str{end+1} = '';

    % RF parameters if available
    if ~isempty(cell.rf_params) && isstruct(cell.rf_params)
        str{end+1} = '--- RF Parameters ---';
        if isfield(cell.rf_params, 'center_x')
            str{end+1} = sprintf('Center X: %.2f', cell.rf_params.center_x);
            str{end+1} = sprintf('Center Y: %.2f', cell.rf_params.center_y);
        end
        if isfield(cell.rf_params, 'std_x')
            str{end+1} = sprintf('Std X: %.2f', cell.rf_params.std_x);
            str{end+1} = sprintf('Std Y: %.2f', cell.rf_params.std_y);
        end
        if isfield(cell.rf_params, 'rotation')
            str{end+1} = sprintf('Rotation: %.2f°', cell.rf_params.rotation);
        end
        str{end+1} = '';
    end

    % Properties if available
    if ~isempty(cell.properties) && isstruct(cell.properties)
        str{end+1} = '--- Properties ---';
        fields = fieldnames(cell.properties);
        for i = 1:length(fields)
            val = cell.properties.(fields{i});
            if isnumeric(val)
                str{end+1} = sprintf('%s: %s', fields{i}, num2str(val));
            elseif ischar(val)
                str{end+1} = sprintf('%s: %s', fields{i}, val);
            end
        end
        str{end+1} = '';
    end

    str{end+1} = sprintf('Epoch Groups: %d', length(cell.epoch_groups));
end

function str = formatEpochGroupData(eg)
    str = {};
    str{end+1} = '=== EPOCH GROUP ===';
    str{end+1} = '';
    str{end+1} = sprintf('ID: %d', eg.id);
    str{end+1} = sprintf('Label: %s', eg.label);
    str{end+1} = sprintf('Protocol: %s', eg.protocol_name);
    str{end+1} = '';

    if ~isempty(eg.start_time)
        str{end+1} = sprintf('Start Time: %s', eg.start_time);
    end
    if ~isempty(eg.end_time)
        str{end+1} = sprintf('End Time: %s', eg.end_time);
    end

    str{end+1} = '';
    str{end+1} = sprintf('Epoch Blocks: %d', length(eg.epoch_blocks));
end

function str = formatEpochBlockData(eb)
    str = {};
    str{end+1} = '=== EPOCH BLOCK ===';
    str{end+1} = '';
    str{end+1} = sprintf('ID: %d', eb.id);
    str{end+1} = sprintf('Label: %s', eb.label);
    str{end+1} = sprintf('Protocol: %s', eb.protocol_name);
    str{end+1} = '';

    % Parameters
    if ~isempty(eb.parameters) && isstruct(eb.parameters)
        str{end+1} = '--- Block Parameters ---';
        fields = fieldnames(eb.parameters);
        for i = 1:length(fields)
            val = eb.parameters.(fields{i});
            if isnumeric(val)
                str{end+1} = sprintf('%s: %s', fields{i}, num2str(val));
            elseif ischar(val)
                str{end+1} = sprintf('%s: %s', fields{i}, val);
            end
        end
        str{end+1} = '';
    end

    % MEA specific
    if ~isempty(eb.data_dir)
        str{end+1} = sprintf('Data Dir: %s', eb.data_dir);
        str{end+1} = '';
    end

    str{end+1} = sprintf('Epochs: %d', length(eb.epochs));
end

function str = formatEpochData(epoch)
    str = {};
    str{end+1} = '=== EPOCH ===';
    str{end+1} = '';
    str{end+1} = sprintf('ID: %d', epoch.id);
    str{end+1} = sprintf('Label: %s', epoch.label);
    str{end+1} = '';

    % Timing
    str{end+1} = sprintf('Start: %.2f ms', epoch.epoch_start_ms);
    str{end+1} = sprintf('End: %.2f ms', epoch.epoch_end_ms);
    if ~isempty(epoch.frame_times_ms)
        str{end+1} = sprintf('Frames: %d', length(epoch.frame_times_ms));
    end
    str{end+1} = '';

    % Parameters
    if ~isempty(epoch.parameters) && isstruct(epoch.parameters)
        str{end+1} = '--- Epoch Parameters ---';
        fields = fieldnames(epoch.parameters);
        for i = 1:min(10, length(fields))  % Show first 10
            val = epoch.parameters.(fields{i});
            if isnumeric(val)
                str{end+1} = sprintf('%s: %s', fields{i}, num2str(val));
            elseif ischar(val)
                str{end+1} = sprintf('%s: %s', fields{i}, val);
            end
        end
        if length(fields) > 10
            str{end+1} = sprintf('... and %d more', length(fields) - 10);
        end
        str{end+1} = '';
    end

    % Response data
    str{end+1} = sprintf('Responses: %d', length(epoch.responses));
    for i = 1:length(epoch.responses)
        resp = epoch.responses(i);
        dataLen = 0;
        if ~isempty(resp.data)
            dataLen = length(resp.data);
        end
        str{end+1} = sprintf('  [%d] %s: %d samples @ %g Hz', ...
            i, resp.device_name, dataLen, resp.sample_rate);
        if ~isempty(resp.spike_times)
            str{end+1} = sprintf('       Spikes: %d', length(resp.spike_times));
        end
    end

    str{end+1} = '';

    % Stimulus data
    str{end+1} = sprintf('Stimuli: %d', length(epoch.stimuli));
    for i = 1:length(epoch.stimuli)
        stim = epoch.stimuli(i);
        dataLen = 0;
        if ~isempty(stim.data)
            dataLen = length(stim.data);
        end
        str{end+1} = sprintf('  [%d] %s: %d samples @ %g Hz', ...
            i, stim.device_name, dataLen, stim.sample_rate);
    end
end

function result = ternary(condition, trueVal, falseVal)
    % Simple ternary operator
    if condition
        result = trueVal;
    else
        result = falseVal;
    end
end
