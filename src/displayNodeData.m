function displayNodeData(axesHandle, nodeData, treeData)
% DISPLAYNODEDATA Display data for selected tree node with plots
%
% Usage:
%   displayNodeData(axesHandle, nodeData, treeData)
%
% Inputs:
%   axesHandle - Handle to axes where plots should be displayed
%   nodeData - Structure containing node information
%   treeData - Full tree data structure from loadEpicTreeData
%
% Description:
%   Creates visual display of selected node data including:
%   - Spike raster plots
%   - PSTH (peri-stimulus time histogram)
%   - Stimulus parameters
%   - Cell/epoch metadata

    % Clear existing content
    cla(axesHandle, 'reset');
    
    if isempty(nodeData) || ~isfield(nodeData, 'type')
        text(axesHandle, 0.5, 0.5, 'No data selected', ...
            'HorizontalAlignment', 'center', 'FontSize', 12);
        return;
    end
    
    % Get the actual data - could be in 'data' field or directly in nodeData
    if isfield(nodeData, 'data')
        actualData = nodeData.data;
    else
        actualData = nodeData;
    end
    
    % Handle different node types
    switch nodeData.type
        case 'epoch'
            plotEpochData(axesHandle, actualData, treeData);
        case 'epoch_block'
            plotBlockSummary(axesHandle, actualData);
        case 'epoch_group'
            plotGroupSummary(axesHandle, actualData);
        case 'cell'
            plotCellSummary(axesHandle, actualData);
        case 'experiment'
            plotExperimentSummary(axesHandle, actualData);
        otherwise
            text(axesHandle, 0.5, 0.5, sprintf('Node type: %s', nodeData.type), ...
                'HorizontalAlignment', 'center', 'FontSize', 12);
    end
end

function plotEpochData(ax, epoch, treeData)
    % Plot detailed epoch data with PSTH and raster
    
    % Check if this is a valid epoch with data
    if ~isstruct(epoch)
        text(ax, 0.5, 0.5, 'Invalid epoch data', ...
            'HorizontalAlignment', 'center', 'FontSize', 11);
        return;
    end
    
    % Try to plot raw trace first if available
    if isfield(epoch, 'raw_trace') && ~isempty(epoch.raw_trace)
        plotRawTrace(ax, epoch);
        return;
    end
    
    % Check if spike data exists
    if isfield(epoch, 'spike_data') && ~isempty(epoch.spike_data)
        plotSpikeData(ax, epoch);
        return;
    end
    
    % Show epoch info without spike/raw data
    showEpochInfo(ax, epoch);
end

function plotRawTrace(ax, epoch)
    % Plot raw voltage/current trace
    raw = epoch.raw_trace;
    
    % Get sample rate (default to 10kHz if not specified)
    if isfield(epoch, 'sample_rate')
        fs = epoch.sample_rate;
    else
        fs = 10000;  % Default 10 kHz
    end

    % Time vector
    time_ms = (0:length(raw)-1) / fs * 1000;

    % Plot
    plot(ax, time_ms, raw, 'k-', 'LineWidth', 0.5);
    xlabel(ax, 'Time (ms)');
    ylabel(ax, 'Amplitude');
    title(ax, sprintf('Epoch %d - Raw Trace', epoch.id));
    grid(ax, 'on');
end

function plotSpikeData(ax, epoch)
    % Plot spike data (raster and PSTH)
    spike_times = epoch.spike_data.spike_times;
    if iscell(spike_times)
        spike_times = spike_times{1};
    end
    
    if isempty(spike_times)
        showEpochInfo(ax, epoch);
        return;
    end
    
    % Create 2x1 subplot layout if parent allows
    % Top: Spike raster, Bottom: PSTH
    parentFig = ancestor(ax, 'figure');
    clf(parentFig);
    
    subplot(2, 1, 1);
    plotSpikeRaster(spike_times);
    title(sprintf('Epoch %d - Cell %d', epoch.id, epoch.cell_id));
    
    subplot(2, 1, 2);
    plotPSTH(spike_times);
    
    % Add parameter info if available
    if isfield(epoch, 'parameters') && ~isempty(epoch.parameters)
        addParameterInfo(gca, epoch.parameters);
    end
end

function showEpochInfo(ax, epoch)
    % Show text-based epoch information
    infoStr = {sprintf('Epoch %d', epoch.id), ''};
    
    if isfield(epoch, 'parameters') && ~isempty(epoch.parameters)
        infoStr{end+1} = 'Parameters:';
        params = fieldnames(epoch.parameters);
        for i = 1:min(5, length(params))
            pname = params{i};
            pval = epoch.parameters.(pname);
            if isnumeric(pval) && ~isempty(pval)
                infoStr{end+1} = sprintf('  %s: %.2g', pname, pval);
            elseif ischar(pval)
                infoStr{end+1} = sprintf('  %s: %s', pname, pval);
            end
        end
        if length(params) > 5
            infoStr{end+1} = sprintf('  ... and %d more', length(params) - 5);
        end
    end
    
    infoStr{end+1} = '';
    infoStr{end+1} = 'No spike or raw trace data available';
    
    text(ax, 0.1, 0.5, infoStr, ...
        'VerticalAlignment', 'middle', ...
        'FontSize', 10, 'FontName', 'FixedWidth');
    axis(ax, 'off');
end

function addParameterInfo(ax, params)
    % Add parameter info to current axes xlabel
    param_names = fieldnames(params);
    if length(param_names) > 5
        param_names = param_names(1:5);
    end
    
    param_str = '';
    for i = 1:length(param_names)
        pname = param_names{i};
        pval = params.(pname);
        if isnumeric(pval) && ~isempty(pval)
            param_str = [param_str sprintf('%s=%.2g  ', pname, pval(1))];
        end
    end
    
    if ~isempty(param_str)
        xlabel(ax, param_str);
    end
end


function plotSpikeRaster(spike_times)
    % Plot spike raster for single trial or multiple trials
    
    if iscell(spike_times)
        % Multiple trials
        n_trials = length(spike_times);
        for i = 1:n_trials
            st = spike_times{i};
            if ~isempty(st)
                line([st; st], [i-0.4; i+0.4]*ones(size(st)), ...
                    'Color', 'k', 'LineWidth', 1);
            end
        end
        ylim([0.5 n_trials+0.5]);
        ylabel('Trial');
    else
        % Single trial
        if ~isempty(spike_times)
            line([spike_times; spike_times], [0.4; 1.4]*ones(size(spike_times)), ...
                'Color', 'k', 'LineWidth', 1.5);
        end
        ylim([0 2]);
        set(gca, 'YTick', []);
    end
    
    xlabel('Time (ms)');
    title('Spike Raster');
    grid on;
end

function plotPSTH(spike_times)
    % Plot PSTH with Gaussian smoothing
    
    % Flatten spike times if cell array
    if iscell(spike_times)
        all_spikes = [];
        for i = 1:length(spike_times)
            all_spikes = [all_spikes; spike_times{i}(:)];
        end
        spike_times = all_spikes;
    end
    
    if isempty(spike_times)
        return;
    end
    
    % Create histogram
    bin_size = 10; % ms
    edges = 0:bin_size:max(spike_times)+bin_size;
    counts = histcounts(spike_times, edges);
    bin_centers = edges(1:end-1) + bin_size/2;
    
    % Smooth with Gaussian
    sigma = 2; % bins
    if length(counts) > sigma*4
        smoothed = imgaussfilt(counts, sigma);
    else
        smoothed = counts;
    end
    
    % Plot
    plot(bin_centers, smoothed, 'k-', 'LineWidth', 1.5);
    xlabel('Time (ms)');
    ylabel('Spike Rate (Hz)');
    title('PSTH (smoothed)');
    grid on;
    if ~isempty(spike_times)
        xlim([0 max(spike_times)]);
    end
end

function plotBlockSummary(ax, block)
    % Summary for epoch block
    
    n_epochs = length(block.epochs);
    
    str = sprintf(['Epoch Block %d\n\n', ...
                  'Number of epochs: %d\n', ...
                  'Protocol: %s\n\n'], ...
                  block.id, n_epochs, block.protocol_name);
    
    if isfield(block, 'parameters') && ~isempty(block.parameters)
        str = [str 'Block Parameters:\n'];
        params = block.parameters;
        param_names = fieldnames(params);
        for i = 1:min(10, length(param_names))
            pname = param_names{i};
            pval = params.(pname);
            if isnumeric(pval)
                str = [str sprintf('  %s: %.2f\n', pname, pval)];
            else
                str = [str sprintf('  %s: %s\n', pname, mat2str(pval))];
            end
        end
    end
    
    text(ax, 0.1, 0.5, str, ...
        'VerticalAlignment', 'middle', ...
        'FontSize', 10, 'FontName', 'FixedWidth');
    axis(ax, 'off');
end

function plotGroupSummary(ax, group)
    % Summary for epoch group
    
    str = sprintf(['Epoch Group %d\n\n', ...
                  'Label: %s\n', ...
                  'Protocol: %s\n', ...
                  'Number of blocks: %d\n'], ...
                  group.id, group.label, group.protocol_name, ...
                  length(group.epoch_blocks));
    
    text(ax, 0.1, 0.5, str, ...
        'VerticalAlignment', 'middle', ...
        'FontSize', 10, 'FontName', 'FixedWidth');
    axis(ax, 'off');
end

function plotCellSummary(ax, cell)
    % Summary for cell
    
    str = sprintf(['Cell %d\n\n', ...
                  'Type: %s\n', ...
                  'Label: %s\n', ...
                  'Number of epoch groups: %d\n'], ...
                  cell.id, cell.type, cell.label, ...
                  length(cell.epoch_groups));
    
    % Add RF parameters if available
    if isfield(cell, 'rf_params') && ~isempty(cell.rf_params)
        str = [str sprintf('\nRF Parameters:\n')];
        if isfield(cell.rf_params, 'center_x')
            str = [str sprintf('  Center: (%.1f, %.1f) um\n', ...
                cell.rf_params.center_x, cell.rf_params.center_y)];
        end
        if isfield(cell.rf_params, 'std_x')
            str = [str sprintf('  Size: %.1f x %.1f um\n', ...
                cell.rf_params.std_x, cell.rf_params.std_y)];
        end
    end
    
    text(ax, 0.1, 0.5, str, ...
        'VerticalAlignment', 'middle', ...
        'FontSize', 10, 'FontName', 'FixedWidth');
    axis(ax, 'off');
end

function plotExperimentSummary(ax, exp)
    % Summary for experiment
    
    str = sprintf(['Experiment: %s\n\n', ...
                  'ID: %d\n', ...
                  'Type: %s\n', ...
                  'Number of cells: %d\n'], ...
                  exp.exp_name, exp.id, ...
                  iff(exp.is_mea, 'MEA', 'Patch'), ...
                  length(exp.cells));
    
    text(ax, 0.1, 0.5, str, ...
        'VerticalAlignment', 'middle', ...
        'FontSize', 10, 'FontName', 'FixedWidth');
    axis(ax, 'off');
end

function addParameterText(params)
    % Add parameter info to current axes
    
    param_names = fieldnames(params);
    if length(param_names) > 5
        param_names = param_names(1:5);
    end
    
    param_str = 'Parameters: ';
    for i = 1:length(param_names)
        pname = param_names{i};
        pval = params.(pname);
        if isnumeric(pval) && ~isempty(pval)
            param_str = [param_str sprintf('%s=%.2g ', pname, pval(1))];
        end
    end
    
    xlabel(param_str);
end

function result = iff(condition, trueVal, falseVal)
    % Inline if-then-else
    if condition
        result = trueVal;
    else
        result = falseVal;
    end
end
