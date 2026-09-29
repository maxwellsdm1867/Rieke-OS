%% Test EpicTreeGUI - Exact Legacy Pattern
% This matches the exact pattern from your legacy code:
%
% dateSplit = @(list)splitOnExperimentDate(list);
% dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);
% tree = riekesuite.analysis.buildTree(list, {
%     'protocolSettings(source:type)',
%     dateSplit_java,
%     'cell.label',
%     'protocolSettings(useRandomSeed)',
%     'protocolSettings(epochGroup:label)',
%     'protocolSettings(frequencyCutoff)',
%     'protocolSettings(currentSD)'
% });
% gui = epochTreeGUI(tree);

close all; clear; clc;

fprintf('=== Exact Legacy Pattern Example ===\n\n');

% CRITICAL: Remove old_epochtree from path if it's there
warning('off', 'MATLAB:rmpath:DirNotFound');
rmpath(genpath('old_epochtree'));
warning('on', 'MATLAB:rmpath:DirNotFound');

% Add NEW code paths (in correct order - most specific first)
addpath('src/gui');           % CRITICAL: Add this first for graphicalTree
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');

%% Load Data
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

if ~exist(data_file, 'file')
    error('File not found: %s', data_file);
end

fprintf('Loading: %s\n', data_file);
[data, ~] = loadEpicTreeData(data_file);
fprintf('Loaded %d epochs\n\n', length(data));

%% Define Custom Splitter (like your dateSplit function)
% In legacy code: dateSplit = @(list)splitOnExperimentDate(list);
% In new code: Already available as static method @epicTreeTools.splitOnExperimentDate

% If you want to create a custom splitter:
function dateStr = myCustomDateSplitter(epoch)
    % Extract date from experiment info
    dateStr = epicTreeTools.getNestedValue(epoch, 'expInfo.date');
    if isempty(dateStr)
        dateStr = 'Unknown';
    end
end

%% Build Tree (matching your legacy hierarchy exactly)
fprintf('Building tree structure matching legacy code...\n');

tree = epicTreeTools(data);

% Legacy:  tree = riekesuite.analysis.buildTree(list, {...});
% New:     tree.buildTreeWithSplitters({...});

tree.buildTreeWithSplitters({
    'cellInfo.type',                              % Was: 'protocolSettings(source:type)'
    @epicTreeTools.splitOnExperimentDate,         % Was: dateSplit_java
    'cellInfo.id',                                % Was: 'cell.label'
    'parameters.useRandomSeed',                   % Was: 'protocolSettings(useRandomSeed)'
    'parameters.epochGroup',                      % Was: 'protocolSettings(epochGroup:label)'
    'parameters.frequencyCutoff',                 % Was: 'protocolSettings(frequencyCutoff)'
    'parameters.currentSD'                        % Was: 'protocolSettings(currentSD)'
});

fprintf('Tree built with %d-level hierarchy\n\n', 7);

%% Display Tree Structure (like the GUI tree view)
fprintf('Top-level structure:\n');
fprintf('ROOT: @(list)splitOnExperimentDate(list)\n');  % Shows the root split function
for i = 1:tree.childrenLength()
    node1 = tree.childAt(i);
    fprintf('├─ %s (%d epochs)\n', char(node1.splitValue), node1.epochCount());

    for j = 1:min(2, node1.childrenLength())
        node2 = node1.childAt(j);
        fprintf('│  ├─ %s (%d epochs)\n', char(node2.splitValue), node2.epochCount());

        for k = 1:min(2, node2.childrenLength())
            node3 = node2.childAt(k);
            fprintf('│  │  └─ %s (%d epochs)\n', char(node3.splitValue), node3.epochCount());
        end
    end
end

%% Launch GUI
fprintf('\n=== Launching GUI ===\n');
fprintf('The GUI will show the exact tree structure defined above.\n');
fprintf('NO dropdown menu - structure is fixed by the code.\n\n');

gui = epicTreeGUI(tree);

fprintf('✓ GUI launched successfully\n');
fprintf('\nTo modify the tree structure:\n');
fprintf('  1. Edit the buildTreeWithSplitters({...}) call above\n');
fprintf('  2. Re-run this script\n');
