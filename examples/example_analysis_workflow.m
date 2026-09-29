%% Example Analysis Workflow with epicTreeGUI
% This script demonstrates common analysis patterns using epicTreeTools
%
% Prerequisites:
%   - Data file in standard format (.mat)
%   - H5 files for response data (optional, for lazy loading)
%
% Run sections individually (Ctrl+Enter) or run entire script

%% Setup
clear; clc;

% Get script directory for relative path resolution
scriptDir = fileparts(mfilename('fullpath'));
parentDir = fileparts(scriptDir);

% Check if epicTreeTools is on path, if not run install
if isempty(which('epicTreeTools'))
    fprintf('epicTreeTools not found on path. Running install...\n');
    installScript = fullfile(parentDir, 'install.m');
    if exist(installScript, 'file')
        run(installScript);
    else
        error('install.m not found. Please run install.m from repository root.');
    end
end

% Data file path - use bundled sample data by default
dataPath = fullfile(scriptDir, 'data', 'sample_epochs.mat');

% To use your own dataset, set dataPath to your .mat file:
%   dataPath = '/path/to/your/data.mat';
fprintf('Using data: %s\n', dataPath);

% Configure H5 directory (optional, for lazy loading)
% Set this to your H5 data directory if available:
%   h5Dir = '/path/to/h5/data';
%   epicTreeConfig('h5_dir', h5Dir);

%% Load Data
fprintf('\n=== Loading Data ===\n');

if ~exist(dataPath, 'file')
    error('Data file not found: %s', dataPath);
end

data = load(dataPath);
fprintf('Loaded: %s\n', dataPath);

% Create tree
tree = epicTreeTools(data);
fprintf('Total epochs: %d\n', length(tree.getAllEpochs(false)));

%% Example 1: Simple Tree - Split by Cell Type
fprintf('\n=== Example 1: Split by Cell Type ===\n');

tree.buildTree({'cellInfo.type'});

fprintf('Cell types found:\n');
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    fprintf('  %s: %d epochs\n', string(child.splitValue), child.epochCount());
end

%% Example 2: Multi-Level Tree
fprintf('\n=== Example 2: Cell Type -> Protocol ===\n');

tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});

% Show tree structure
fprintf('Tree structure:\n');
for i = 1:tree.childrenLength()
    cellNode = tree.childAt(i);
    fprintf('+ %s (%d epochs)\n', string(cellNode.splitValue), cellNode.epochCount());

    for j = 1:cellNode.childrenLength()
        protocolNode = cellNode.childAt(j);
        fprintf('    - %s (%d epochs)\n', string(protocolNode.splitValue), protocolNode.epochCount());
    end
end

%% Example 3: Navigation Patterns
fprintf('\n=== Example 3: Tree Navigation ===\n');

% Get leaf nodes
leaves = tree.leafNodes();
fprintf('Number of leaf nodes: %d\n', length(leaves));

% Examine a leaf node
leaf = leaves{1};
fprintf('\nLeaf node info:\n');
fprintf('  Path: %s\n', leaf.pathString());
fprintf('  Depth: %d\n', leaf.depth());
fprintf('  Epochs: %d\n', length(leaf.epochList));

% Navigate up
parent = leaf.parent;
fprintf('  Parent split value: %s\n', string(parent.splitValue));

root = leaf.getRoot();
fprintf('  Root has %d children\n', root.childrenLength());

%% Example 4: Get Data with Selection Filtering
fprintf('\n=== Example 4: Data Retrieval ===\n');

% Get first leaf node
testNode = leaves{1};
fprintf('Testing on: %s\n', testNode.pathString());

% Get selected data (H5 file optional for bundled data)
% Note: getSelectedData can work with embedded data (no H5 file needed)
try
    [dataMatrix, epochs, sampleRate] = epicTreeTools.getSelectedData(testNode, 'Amp1');
    fprintf('Retrieved:\n');
    fprintf('  Data size: [%d x %d]\n', size(dataMatrix, 1), size(dataMatrix, 2));
    fprintf('  Sample rate: %g Hz\n', sampleRate);
    fprintf('  Data range: [%.4f, %.4f]\n', min(dataMatrix(:)), max(dataMatrix(:)));
catch ME
    fprintf('Data retrieval skipped: %s\n', ME.message);
    fprintf('(H5 files not available for bundled sample data)\n');
    dataMatrix = [];
    sampleRate = 10000;  % Default for next examples
end

%% Example 5: Selection Filtering
fprintf('\n=== Example 5: Selection Filtering ===\n');

% Get all epochs from a node
allEpochs = testNode.getAllEpochs(false);
fprintf('All epochs: %d\n', length(allEpochs));

% Get only selected epochs
selectedEpochs = testNode.getAllEpochs(true);
fprintf('Selected epochs: %d\n', length(selectedEpochs));

% Mark some as unselected
nToDeselect = min(3, length(testNode.epochList));
for i = 1:nToDeselect
    testNode.epochList{i}.isSelected = false;
end

% Check counts again
fprintf('After deselecting %d:\n', nToDeselect);
fprintf('  All: %d\n', length(testNode.getAllEpochs(false)));
fprintf('  Selected: %d\n', length(testNode.getAllEpochs(true)));

% Restore
for i = 1:nToDeselect
    testNode.epochList{i}.isSelected = true;
end

%% Example 6: Controlled Access (putCustom/getCustom)
fprintf('\n=== Example 6: Controlled Access ===\n');

% Store analysis results
results = struct();
results.experimentDate = datestr(now);
results.nEpochs = size(dataMatrix, 1);
results.meanResponse = mean(dataMatrix, 1);
results.peakResponse = max(mean(dataMatrix, 1));

testNode.putCustom('analysisResults', results);
fprintf('Stored results at node\n');

% Check if exists
if testNode.hasCustom('analysisResults')
    fprintf('  hasCustom(''analysisResults'') = true\n');
end

% Retrieve
r = testNode.getCustom('analysisResults');
fprintf('  Peak response: %.4f\n', r.peakResponse);

% List all custom keys
keys = testNode.customKeys();
fprintf('  Custom keys: %s\n', strjoin(keys', ', '));

%% Example 7: Compute Mean Response Trace
fprintf('\n=== Example 7: Mean Response Trace ===\n');

% Get data
try
    [data_ex7, ~, fs] = epicTreeTools.getSelectedData(testNode, 'Amp1');
catch
    fprintf('Skipping Example 7: H5 data not available\n');
    return;
end

% Compute mean and SEM
meanTrace = mean(data_ex7, 1);
semTrace = std(data_ex7, [], 1) / sqrt(size(data_ex7, 1));
timeVector = (1:length(meanTrace)) / fs * 1000;  % ms

% Plot
figure('Name', 'Mean Response Trace');
hold on;
fill([timeVector fliplr(timeVector)], ...
     [meanTrace-semTrace fliplr(meanTrace+semTrace)], ...
     [0.8 0.8 1], 'EdgeColor', 'none', 'FaceAlpha', 0.5);
plot(timeVector, meanTrace, 'b', 'LineWidth', 2);
xlabel('Time (ms)');
ylabel('Response');
title(sprintf('Mean Response (n=%d)', size(data_ex7, 1)));
hold off;

%% Example 8: Compare Multiple Conditions (MeanSelectedNodes)
fprintf('\n=== Example 8: Compare Conditions ===\n');

% Rebuild tree with cell type at top level
tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});

% Get first cell type node
if tree.childrenLength() > 0
    cellTypeNode = tree.childAt(1);

    % Collect protocol nodes
    protocolNodes = {};
    for i = 1:cellTypeNode.childrenLength()
        protocolNodes{end+1} = cellTypeNode.childAt(i);
    end

    fprintf('Comparing %d protocols for %s\n', ...
        length(protocolNodes), string(cellTypeNode.splitValue));

    % Compare using MeanSelectedNodes
    if length(protocolNodes) >= 2
        figure('Name', 'Protocol Comparison');
        try
            results = epicTreeTools.MeanSelectedNodes(protocolNodes, 'Amp1', ...
                'BaselineCorrect', true, ...
                'ShowLegend', true, ...
                'ShowAnalysis', true);
        catch
            fprintf('MeanSelectedNodes skipped (requires H5 data)\n');
            results = struct('respAmp', []);
        end

        fprintf('Response amplitudes:\n');
        for i = 1:length(results.respAmp)
            fprintf('  %s: %.4f\n', string(protocolNodes{i}.splitValue), results.respAmp(i));
        end
    end
end

%% Example 9: Batch Analysis Over All Leaves
fprintf('\n=== Example 9: Batch Analysis ===\n');

% Get all leaf nodes
leaves = tree.leafNodes();
fprintf('Analyzing %d leaf nodes...\n', length(leaves));

% Analyze each leaf
batchResults = cell(length(leaves), 1);
for i = 1:length(leaves)
    leaf = leaves{i};

    % Get data
    try
        [leafData, ~, ~] = epicTreeTools.getSelectedData(leaf, 'Amp1');
    catch
        leafData = [];
    end

    if isempty(leafData)
        continue;
    end

    % Compute stats
    r = struct();
    r.path = leaf.pathString();
    r.nEpochs = size(leafData, 1);
    r.meanPeak = max(mean(leafData, 1));
    r.splitValue = leaf.splitValue;

    % Store at node
    leaf.putCustom('batchResults', r);
    batchResults{i} = r;

    fprintf('  %s: peak=%.4f (n=%d)\n', r.path, r.meanPeak, r.nEpochs);
end

%% Example 10: Query Stored Results
fprintf('\n=== Example 10: Query Stored Results ===\n');

% Retrieve results from all leaves
for i = 1:length(leaves)
    r = leaves{i}.getCustom('batchResults');
    if ~isempty(r) && r.nEpochs > 0
        fprintf('%s: %.4f\n', r.path, r.meanPeak);
    end
end

%% Summary
fprintf('\n=== Workflow Complete ===\n');
fprintf('Key functions demonstrated:\n');
fprintf('  - epicTreeTools()      : Create tree from data\n');
fprintf('  - buildTree()          : Organize by split keys\n');
fprintf('  - childAt(), childrenLength() : Navigate down\n');
fprintf('  - parent, parentAt(), depth() : Navigate up\n');
fprintf('  - getAllEpochs()       : Get epochs with selection filter\n');
fprintf('  - epicTreeTools.getSelectedData()    : Get response matrix\n');
fprintf('  - putCustom()/getCustom() : Store/retrieve results\n');
fprintf('  - epicTreeTools.MeanSelectedNodes()  : Compare conditions\n');
