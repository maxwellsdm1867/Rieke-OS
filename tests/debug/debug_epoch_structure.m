%% Debug Epoch Structure
% This script loads data and shows what fields are actually in an epoch

close all; clear; clc;

fprintf('=== Debugging Epoch Structure ===\n\n');

% Add paths
addpath('src/gui');
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');

% Load data
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
[data, ~] = loadEpicTreeData(data_file);

fprintf('Loaded %d epochs\n\n', length(data));

% Get first epoch
ep = data{1};

fprintf('===== EPOCH STRUCTURE =====\n');
fprintf('Class: %s\n\n', class(ep));

% Show all fields
fprintf('Top-level fields:\n');
fields = fieldnames(ep);
for i = 1:length(fields)
    fieldName = fields{i};
    fieldValue = ep.(fieldName);

    if isstruct(fieldValue)
        fprintf('  %s: [struct with %d fields]\n', fieldName, length(fieldnames(fieldValue)));
        % Show nested fields
        nestedFields = fieldnames(fieldValue);
        for j = 1:min(5, length(nestedFields))
            fprintf('    - %s\n', nestedFields{j});
        end
        if length(nestedFields) > 5
            fprintf('    - ... (%d more)\n', length(nestedFields) - 5);
        end
    elseif iscell(fieldValue)
        fprintf('  %s: [cell array %s]\n', fieldName, mat2str(size(fieldValue)));
    elseif ischar(fieldValue) || isstring(fieldValue)
        if length(fieldValue) < 50
            fprintf('  %s: "%s"\n', fieldName, fieldValue);
        else
            fprintf('  %s: "%s..." (%d chars)\n', fieldName, fieldValue(1:50), length(fieldValue));
        end
    elseif isnumeric(fieldValue) && length(fieldValue) == 1
        fprintf('  %s: %g\n', fieldName, fieldValue);
    else
        fprintf('  %s: [%s]\n', fieldName, class(fieldValue));
    end
end

fprintf('\n');

% Check for responses
if isfield(ep, 'responses')
    fprintf('===== RESPONSES STRUCTURE =====\n');
    resp = ep.responses;

    if isstruct(resp)
        fprintf('responses is a struct with %d elements\n', length(resp));
        if length(resp) > 0
            fprintf('\nFirst response fields:\n');
            respFields = fieldnames(resp);
            for i = 1:length(respFields)
                fieldName = respFields{i};
                fieldValue = resp(1).(fieldName);
                fprintf('  %s: [%s] size=%s\n', fieldName, class(fieldValue), mat2str(size(fieldValue)));
            end
        end
    elseif iscell(resp)
        fprintf('responses is a cell array: %s\n', mat2str(size(resp)));
    end
end

fprintf('\n');

% Check for protocol info
fprintf('===== PROTOCOL INFO =====\n');
if isfield(ep, 'protocolSettings')
    fprintf('Has protocolSettings\n');
    if isfield(ep.protocolSettings, 'protocolID')
        fprintf('  protocolID: %s\n', ep.protocolSettings.protocolID);
    end
elseif isfield(ep, 'parameters')
    fprintf('Has parameters\n');
    if isfield(ep.parameters, 'protocol')
        fprintf('  protocol: %s\n', ep.parameters.protocol);
    end
end

fprintf('\n');

% Check for date info
fprintf('===== DATE INFO =====\n');
if isfield(ep, 'expInfo')
    fprintf('Has expInfo\n');
    if isfield(ep.expInfo, 'date')
        fprintf('  date: %s\n', ep.expInfo.date);
    end
end
if isfield(ep, 'startTime')
    fprintf('Has startTime: %s\n', ep.startTime);
end

fprintf('\n=== DEBUG COMPLETE ===\n');
fprintf('Use this info to fix the data extraction in epicTreeGUI.m\n');
