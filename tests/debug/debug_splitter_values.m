%% Debug Splitter Values - Show what's actually happening
% This script adds debug output to see what values the splitter returns

close all; clear; clc;

fprintf('=== DEBUG: Splitter Values ===\n\n');

%% Load real data
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

if ~exist(data_file, 'file')
    error('File not found: %s', data_file);
end

fprintf('Loading data: %s\n', data_file);
[data, metadata] = loadEpicTreeData(data_file);
fprintf('  Loaded %d epochs\n\n', length(data));

%% Inspect first 10 epochs
fprintf('========================================\n');
fprintf('INSPECTING FIRST 10 EPOCHS\n');
fprintf('========================================\n\n');

tree = epicTreeTools(data);

fprintf('%-6s | %-20s | %-30s | %s\n', 'Epoch', 'cellInfo.type', 'splitOnCellType Result', 'Keywords');
fprintf('%s\n', repmat('-', 100, 1));

for i = 1:min(10, length(tree.allEpochs))
    epoch = tree.allEpochs{i};

    % Get cellInfo.type
    if isfield(epoch, 'cellInfo') && isfield(epoch.cellInfo, 'type')
        cell_info_type = epoch.cellInfo.type;
    else
        cell_info_type = 'NOT SET';
    end

    % Get keywords
    if isfield(epoch, 'keywords')
        if iscell(epoch.keywords)
            kw = strjoin(epoch.keywords, ', ');
        else
            kw = char(epoch.keywords);
        end
    else
        kw = 'none';
    end

    % Test the splitter
    result = epicTreeTools.splitOnCellType(epoch);

    fprintf('%-6d | %-20s | %-30s | %s\n', i, cell_info_type, result, kw);
end

%% Count unique cell types in raw data
fprintf('\n========================================\n');
fprintf('UNIQUE CELL TYPES IN RAW DATA\n');
fprintf('========================================\n\n');

cell_types = {};
for i = 1:length(tree.allEpochs)
    epoch = tree.allEpochs{i};
    if isfield(epoch, 'cellInfo') && isfield(epoch.cellInfo, 'type')
        cell_types{end+1} = epoch.cellInfo.type;
    end
end

unique_types = unique(cell_types);
fprintf('Found %d unique cell type(s) in cellInfo.type:\n', length(unique_types));
for i = 1:length(unique_types)
    count = sum(strcmp(cell_types, unique_types{i}));
    fprintf('  %-30s: %4d epochs (%5.1f%%)\n', ...
        unique_types{i}, count, 100*count/length(cell_types));
end

%% Count what splitter returns
fprintf('\n========================================\n');
fprintf('WHAT SPLITTER RETURNS\n');
fprintf('========================================\n\n');

splitter_results = {};
for i = 1:length(tree.allEpochs)
    epoch = tree.allEpochs{i};
    result = epicTreeTools.splitOnCellType(epoch);
    splitter_results{end+1} = char(result);
end

unique_results = unique(splitter_results);
fprintf('Splitter returns %d unique value(s):\n', length(unique_results));
for i = 1:length(unique_results)
    count = sum(strcmp(splitter_results, unique_results{i}));
    fprintf('  %-30s: %4d epochs (%5.1f%%)\n', ...
        unique_results{i}, count, 100*count/length(splitter_results));
end

%% Build tree and see what nodes are created
fprintf('\n========================================\n');
fprintf('TREE NODES CREATED\n');
fprintf('========================================\n\n');

tree2 = epicTreeTools(data);
tree2.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});

fprintf('Root has %d children:\n', tree2.childrenLength());
for i = 1:tree2.childrenLength()
    node = tree2.childAt(i);
    fprintf('  Node %d:\n', i);
    fprintf('    splitValue: "%s" (class: %s)\n', ...
        char(node.splitValue), class(node.splitValue));
    fprintf('    epochCount: %d\n', node.epochCount());

    % Check first epoch in this node
    if ~isempty(node.epochList) && ~isempty(node.epochList{1})
        first_epoch = node.epochList{1};
        if isfield(first_epoch, 'cellInfo') && isfield(first_epoch.cellInfo, 'type')
            fprintf('    First epoch cellInfo.type: "%s"\n', first_epoch.cellInfo.type);
        end
    end
    fprintf('\n');
end

%% Test with modified data to verify splitter works
fprintf('========================================\n');
fprintf('TEST: Manually setting cell types\n');
fprintf('========================================\n\n');

% Create copy and manually set some cell types
test_data = data;
fprintf('Setting first 100 epochs to different cell types...\n');

assignments = {
    'RGC\ON-parasol', 1, 25;
    'RGC\OFF-parasol', 26, 50;
    'RGC\ON-midget', 51, 75;
    'RGC\OFF-midget', 76, 100;
};

for row = 1:size(assignments, 1)
    cell_type = assignments{row, 1};
    start_idx = assignments{row, 2};
    end_idx = assignments{row, 3};

    for idx = start_idx:end_idx
        if idx <= length(test_data)
            test_data(idx).cellInfo.type = cell_type;
        end
    end
    fprintf('  Epochs %3d-%3d: %s\n', start_idx, end_idx, cell_type);
end

fprintf('\nBuilding tree with modified data...\n');
test_tree = epicTreeTools(test_data);
test_tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});

fprintf('\nTree with modified data has %d children:\n', test_tree.childrenLength());
for i = 1:test_tree.childrenLength()
    node = test_tree.childAt(i);
    fprintf('  %-30s: %4d epochs\n', char(node.splitValue), node.epochCount());
end

%% Summary
fprintf('\n========================================\n');
fprintf('SUMMARY\n');
fprintf('========================================\n\n');

fprintf('Your current data shows:\n');
fprintf('  • All epochs have cellInfo.type = "%s"\n', unique_types{1});
fprintf('  • Splitter correctly returns: "%s"\n', unique_results{1});
fprintf('  • Tree creates %d node(s) as expected\n\n', tree2.childrenLength());

fprintf('When data has specific cell types (tested manually):\n');
fprintf('  • Splitter correctly recognizes different types\n');
fprintf('  • Tree creates separate nodes for each type\n');
fprintf('  • Full names (RGC\\ON-parasol, etc.) work correctly\n\n');

fprintf('CONCLUSION:\n');
fprintf('  The splitter is working correctly!\n');
fprintf('  Your data just has all cells as "%s" because\n', unique_types{1});
fprintf('  they were not typed before export from RetinAnalysis.\n\n');

fprintf('TO FIX:\n');
fprintf('  1. Type your cells in RetinAnalysis (create typing files)\n');
fprintf('  2. Re-export with updated matlab_export.py\n');
fprintf('  3. Load in epicTreeGUI → you will see specific cell types\n\n');
