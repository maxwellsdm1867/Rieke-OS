function singleEpoch(treeNode, panel, doInit)
% SINGLEEPOCH Display single epoch data with slider navigation
%
% Creates an interactive viewer for browsing individual epochs within
% a tree node. Includes response plotting, info table, and slider
% for navigation.
%
% Usage:
%   singleEpoch(treeNode, panel)
%   singleEpoch(treeNode, panel, true)  % Force re-initialization
%
% Inputs:
%   treeNode - epicTreeTools node containing epochs
%   panel    - Parent panel/figure to display in
%   doInit   - (optional) Force re-initialization of UI components
%
% Description:
%   - Info table shows epoch number, date, selection state, parameters
%   - Plot shows response traces for all streams
%   - Slider navigates between epochs
%   - Checkbox toggles epoch selection state
%
% See also: epicTreeGUI, getTreeEpochs

if nargin < 3
    doInit = false;
end

% Get epochs from tree node
if isa(treeNode, 'epicTreeTools')
    epochs = treeNode.getAllEpochs(false);  % All epochs, not just selected
else
    epochs = treeNode;  % Assume it's already a cell array
end

n = length(epochs);

if n == 0
    % No epochs - show message
    if ishandle(panel)
        children = get(panel, 'Children');
        delete(children);
        uicontrol('Parent', panel, 'Style', 'text', ...
            'String', 'No epochs to display', ...
            'Units', 'normalized', 'Position', [0.3 0.5 0.4 0.1]);
    end
    return;
end

% Get or create figure data
figData = get(panel, 'UserData');
if isempty(figData) || doInit || ~isfield(figData, 'plotAxes')
    figData = createUI(panel);
end

% Store epochs
figData.epochs = epochs;
figData.treeNode = treeNode;

% Configure slider
if n > 1
    set(figData.slider, ...
        'Min', 1, ...
        'Max', n + 0.001, ...  % Avoid Max == Min
        'SliderStep', [1/(n-1), 1/(n-1)], ...
        'Value', 1, ...
        'Enable', 'on');
else
    set(figData.slider, 'Enable', 'off', 'Value', 1);
end

% Update epoch count label
set(figData.countLabel, 'String', sprintf('1 of %d', n));

% Store data and plot first epoch
set(panel, 'UserData', figData);
plotEpoch(figData, 1);

end


function figData = createUI(panel)
% CREATEUI Create UI components for epoch viewer

% Clear existing children
children = get(panel, 'Children');
delete(children);

figData = struct();

% Info table (top)
figData.infoTable = uitable('Parent', panel, ...
    'Units', 'normalized', ...
    'Position', [0.02 0.75 0.96 0.23], ...
    'ColumnName', {'Property', 'Value'}, ...
    'ColumnWidth', {100, 180}, ...
    'RowName', [], ...
    'Data', {'Index', ''; 'Date', ''; 'Selected', ''; 'Protocol', ''; 'Parameters', ''});

% Plot axes (middle)
figData.plotAxes = axes('Parent', panel, ...
    'Units', 'normalized', ...
    'Position', [0.1 0.22 0.85 0.48]);
xlabel(figData.plotAxes, 'Time (ms)');
ylabel(figData.plotAxes, 'Response');
title(figData.plotAxes, 'Epoch Response');

% Navigation panel (bottom)
navPanel = uipanel('Parent', panel, ...
    'Title', '', ...
    'BorderType', 'none', ...
    'Units', 'normalized', ...
    'Position', [0.02 0.02 0.96 0.18]);

% Slider
figData.slider = uicontrol('Parent', navPanel, ...
    'Style', 'slider', ...
    'Units', 'normalized', ...
    'Position', [0.15 0.55 0.7 0.35], ...
    'Min', 1, 'Max', 2, 'Value', 1, ...
    'Callback', @(src,evt) onSliderChange(src, panel));

% Previous button
figData.prevBtn = uicontrol('Parent', navPanel, ...
    'Style', 'pushbutton', ...
    'String', '<', ...
    'Units', 'normalized', ...
    'Position', [0.02 0.55 0.1 0.35], ...
    'Callback', @(src,evt) onPrevious(panel));

% Next button
figData.nextBtn = uicontrol('Parent', navPanel, ...
    'Style', 'pushbutton', ...
    'String', '>', ...
    'Units', 'normalized', ...
    'Position', [0.88 0.55 0.1 0.35], ...
    'Callback', @(src,evt) onNext(panel));

% Count label
figData.countLabel = uicontrol('Parent', navPanel, ...
    'Style', 'text', ...
    'String', '1 of 1', ...
    'Units', 'normalized', ...
    'Position', [0.35 0.1 0.3 0.35], ...
    'FontSize', 10);

% Selection checkbox
figData.selectCheck = uicontrol('Parent', navPanel, ...
    'Style', 'checkbox', ...
    'String', 'Selected', ...
    'Value', 1, ...
    'Units', 'normalized', ...
    'Position', [0.02 0.1 0.25 0.35], ...
    'Callback', @(src,evt) onSelectionToggle(src, panel));

% Include in analysis checkbox
figData.includeCheck = uicontrol('Parent', navPanel, ...
    'Style', 'checkbox', ...
    'String', 'Include', ...
    'Value', 1, ...
    'Units', 'normalized', ...
    'Position', [0.7 0.1 0.28 0.35], ...
    'Callback', @(src,evt) onIncludeToggle(src, panel));

end


function plotEpoch(figData, idx)
% PLOTEPOCH Plot response data for a single epoch

epochs = figData.epochs;
if idx < 1 || idx > length(epochs)
    return;
end

epoch = epochs{idx};
ax = figData.plotAxes;

% Update slider position
set(figData.slider, 'Value', idx);

% Update count label
set(figData.countLabel, 'String', sprintf('%d of %d', idx, length(epochs)));

% Update checkboxes
if isfield(epoch, 'isSelected')
    set(figData.selectCheck, 'Value', epoch.isSelected);
else
    set(figData.selectCheck, 'Value', 1);
end

if isfield(epoch, 'includeInAnalysis')
    set(figData.includeCheck, 'Value', epoch.includeInAnalysis);
else
    set(figData.includeCheck, 'Value', 1);
end

% Update info table
infoData = buildInfoData(epoch, idx, length(epochs));
set(figData.infoTable, 'Data', infoData);

% Plot responses
cla(ax);
hold(ax, 'on');

if isfield(epoch, 'responses') && ~isempty(epoch.responses)
    colors = lines(length(epoch.responses));
    legendEntries = {};

    for i = 1:length(epoch.responses)
        resp = epoch.responses(i);

        if isfield(resp, 'data') && ~isempty(resp.data)
            data = resp.data(:)';

            % Get time vector
            if isfield(resp, 'sample_rate') && resp.sample_rate > 0
                t = (1:length(data)) / resp.sample_rate * 1000;  % ms
            else
                t = 1:length(data);
            end

            plot(ax, t, data, 'Color', colors(i,:), 'LineWidth', 1.5);

            if isfield(resp, 'device_name')
                legendEntries{end+1} = resp.device_name;
            else
                legendEntries{end+1} = sprintf('Response %d', i);
            end
        end
    end

    if ~isempty(legendEntries)
        legend(ax, legendEntries, 'Location', 'best');
    end
end

hold(ax, 'off');
xlabel(ax, 'Time (ms)');
ylabel(ax, 'Response');

% Add stimulus timing markers if available
if isfield(epoch, 'parameters')
    params = epoch.parameters;
    if isfield(params, 'preTime') && isfield(params, 'stimTime')
        preTime = params.preTime;
        stimTime = params.stimTime;

        ylims = ylim(ax);
        hold(ax, 'on');
        % Pre-stim shading
        patch(ax, [0 preTime preTime 0], [ylims(1) ylims(1) ylims(2) ylims(2)], ...
            [0.9 0.9 0.9], 'EdgeColor', 'none', 'FaceAlpha', 0.3);
        % Stim onset line
        plot(ax, [preTime preTime], ylims, 'g--', 'LineWidth', 1);
        % Stim offset line
        plot(ax, [preTime+stimTime preTime+stimTime], ylims, 'r--', 'LineWidth', 1);
        hold(ax, 'off');
    end
end

title(ax, sprintf('Epoch %d', idx));

end


function infoData = buildInfoData(epoch, idx, total)
% BUILDINFODATA Build info table data for an epoch

infoData = cell(5, 2);

% Index
infoData{1,1} = 'Index';
infoData{1,2} = sprintf('%d of %d', idx, total);

% Date/time
infoData{2,1} = 'Date';
if isfield(epoch, 'start_time')
    infoData{2,2} = datestr(epoch.start_time);
elseif isfield(epoch, 'expInfo') && isfield(epoch.expInfo, 'exp_name')
    infoData{2,2} = epoch.expInfo.exp_name;
else
    infoData{2,2} = 'N/A';
end

% Selection state
infoData{3,1} = 'Selected';
if isfield(epoch, 'isSelected')
    infoData{3,2} = sprintf('%d', epoch.isSelected);
else
    infoData{3,2} = 'true';
end

% Protocol
infoData{4,1} = 'Protocol';
if isfield(epoch, 'groupInfo') && isfield(epoch.groupInfo, 'protocol_name')
    infoData{4,2} = epoch.groupInfo.protocol_name;
elseif isfield(epoch, 'blockInfo') && isfield(epoch.blockInfo, 'protocol_name')
    infoData{4,2} = epoch.blockInfo.protocol_name;
else
    infoData{4,2} = 'N/A';
end

% Key parameters
infoData{5,1} = 'Parameters';
if isfield(epoch, 'parameters')
    params = epoch.parameters;
    paramStr = '';

    % Show key parameters
    keyParams = {'contrast', 'size', 'temporal_frequency', 'preTime', 'stimTime'};
    for i = 1:length(keyParams)
        if isfield(params, keyParams{i})
            val = params.(keyParams{i});
            if isnumeric(val)
                paramStr = [paramStr sprintf('%s=%.2g ', keyParams{i}, val)];
            end
        end
    end

    if isempty(paramStr)
        paramStr = 'N/A';
    end
    infoData{5,2} = paramStr;
else
    infoData{5,2} = 'N/A';
end

end


function onSliderChange(src, panel)
% Handle slider value change

figData = get(panel, 'UserData');
if isempty(figData)
    return;
end

idx = round(get(src, 'Value'));
idx = max(1, min(idx, length(figData.epochs)));
plotEpoch(figData, idx);

end


function onPrevious(panel)
% Handle previous button click

figData = get(panel, 'UserData');
if isempty(figData)
    return;
end

idx = round(get(figData.slider, 'Value'));
if idx > 1
    plotEpoch(figData, idx - 1);
end

end


function onNext(panel)
% Handle next button click

figData = get(panel, 'UserData');
if isempty(figData)
    return;
end

idx = round(get(figData.slider, 'Value'));
if idx < length(figData.epochs)
    plotEpoch(figData, idx + 1);
end

end


function onSelectionToggle(src, panel)
% Handle selection checkbox toggle

figData = get(panel, 'UserData');
if isempty(figData)
    return;
end

idx = round(get(figData.slider, 'Value'));
if idx >= 1 && idx <= length(figData.epochs)
    figData.epochs{idx}.isSelected = get(src, 'Value');
    set(panel, 'UserData', figData);
end

end


function onIncludeToggle(src, panel)
% Handle include in analysis checkbox toggle

figData = get(panel, 'UserData');
if isempty(figData)
    return;
end

idx = round(get(figData.slider, 'Value'));
if idx >= 1 && idx <= length(figData.epochs)
    figData.epochs{idx}.includeInAnalysis = get(src, 'Value');
    set(panel, 'UserData', figData);
end

end
