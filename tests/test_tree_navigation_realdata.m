%% Test Tree Navigation with REAL DATA
% This script tests epicTreeTools navigation using real experimental data
%
% Prerequisites:
%   - Real data at: /Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat
%   - H5 files at: /Users/maxwellsdm/Documents/epicTreeTest/h5/
%
% Run from epicTreeGUI directory:
%   cd /Users/maxwellsdm/Documents/GitHub/epicTreeGUI
%   run tests/test_tree_navigation_realdata.m

clear; clc;
fprintf('\n========================================\n');
fprintf('  EPICTREETOOLS TEST WITH REAL DATA\n');
fprintf('========================================\n\n');

%% Add paths
baseDir = fileparts(fileparts(mfilename('fullpath')));
if isempty(baseDir)
    baseDir = '/Users/maxwellsdm/Documents/GitHub/epicTreeGUI';
end
addpath(genpath(fullfile(baseDir, 'src')));
fprintf('Base dir: %s\n', baseDir);

%% Configure paths
dataPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';

% Check if files exist
if ~exist(dataPath, 'file')
    fprintf('[ERROR] Data file not found: %s\n', dataPath);
    fprintf('Please ensure real test data is available.\n');
    return;
end

fprintf('Data file: %s\n', dataPath);
fprintf('H5 directory: %s\n\n', h5Dir);

%% Configure H5 directory (like retinanalysis pattern)
epicTreeConfig('h5_dir', h5Dir);

%% 1. LOAD DATA
fprintf('1. LOAD DATA\n');
fprintf('   ---------\n');

try
    data = load(dataPath);
    fprintf('   Loaded fields: %s\n', strjoin(fieldnames(data), ', '));

    % Check structure
    if isfield(data, 'experiments')
        fprintf('   Found experiments field\n');
    end
    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% 2. CREATE TREE
fprintf('2. CREATE EPICTREETOOLS\n');
fprintf('   --------------------\n');

try
    tree = epicTreeTools(data);
    fprintf('   Tree created\n');

    % Check all epochs
    allEpochs = tree.getAllEpochs(false);
    fprintf('   Total epochs: %d\n', length(allEpochs));

    if length(allEpochs) == 0
        fprintf('   [WARN] No epochs found - check data structure\n');
    end
    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n', ME.message);
    disp(getReport(ME));
    return;
end

%% 3. BUILD TREE WITH SPLITTERS
fprintf('3. BUILD TREE WITH SPLITTERS\n');
fprintf('   -------------------------\n');

try
    % Try different splitter combinations
    % Based on DATA_FORMAT_SPECIFICATION: cellInfo.type, blockInfo.protocol_name, parameters.*

    % First, examine what fields are available
    if ~isempty(allEpochs)
        ep1 = allEpochs{1};
        fprintf('   Epoch fields: %s\n', strjoin(fieldnames(ep1), ', '));

        if isfield(ep1, 'parameters') && ~isempty(ep1.parameters)
            paramFields = fieldnames(ep1.parameters);
            fprintf('   Parameter fields: %s\n', strjoin(paramFields, ', '));
        end
    end

    % Try building with cell type and protocol
    tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});
    fprintf('   Built tree with: cellType -> protocol\n');
    fprintf('   Top-level children: %d\n', tree.childrenLength());

    % Show tree structure
    fprintf('\n   Tree structure:\n');
    showTreeStructure(tree, 3);

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n', ME.message);
    disp(getReport(ME));
    return;
end

%% 4. NAVIGATE DOWN
fprintf('4. NAVIGATE DOWN (children)\n');
fprintf('   ------------------------\n');

try
    % childrenLength
    n = tree.childrenLength();
    fprintf('   tree.childrenLength() = %d\n', n);

    if n > 0
        % childAt
        firstChild = tree.childAt(1);
        fprintf('   tree.childAt(1).splitValue = "%s"\n', string(firstChild.splitValue));

        % leafNodes
        leaves = tree.leafNodes();
        fprintf('   tree.leafNodes() count = %d\n', length(leaves));

        % Show first few leaves
        fprintf('   First 3 leaves:\n');
        for i = 1:min(3, length(leaves))
            leaf = leaves{i};
            fprintf('     %d. %s (%d epochs)\n', i, leaf.pathString(), length(leaf.epochList));
        end
    end

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% 5. NAVIGATE UP (parents)
fprintf('5. NAVIGATE UP (parents)\n');
fprintf('   ---------------------\n');

try
    if ~isempty(leaves)
        leaf = leaves{1};

        % depth
        d = leaf.depth();
        fprintf('   leaf.depth() = %d\n', d);

        % parent
        if ~isempty(leaf.parent)
            fprintf('   leaf.parent.splitValue = "%s"\n', string(leaf.parent.splitValue));
        end

        % parentAt
        if d >= 2
            ancestor = leaf.parentAt(d-1);
            fprintf('   leaf.parentAt(%d).splitValue = "%s"\n', d-1, string(ancestor.splitValue));
        end

        % getRoot
        root = leaf.getRoot();
        fprintf('   leaf.getRoot() is root: %s\n', string(isempty(root.parent)));

        % pathString
        pathStr = leaf.pathString();
        fprintf('   leaf.pathString() = "%s"\n', pathStr);
    end

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% 6. CONTROLLED ACCESS (putCustom/getCustom)
fprintf('6. CONTROLLED ACCESS\n');
fprintf('   -----------------\n');

try
    if tree.childrenLength() > 0
        testNode = tree.childAt(1);

        % putCustom
        testResults = struct('mean', 42.5, 'std', 3.2, 'n', 10);
        testNode.putCustom('testResults', testResults);
        fprintf('   putCustom("testResults", ...) - stored\n');

        % hasCustom
        hasIt = testNode.hasCustom('testResults');
        fprintf('   hasCustom("testResults") = %s\n', string(hasIt));

        % getCustom
        retrieved = testNode.getCustom('testResults');
        fprintf('   getCustom("testResults").mean = %.1f\n', retrieved.mean);

        % removeCustom
        testNode.removeCustom('testResults');
        hasItNow = testNode.hasCustom('testResults');
        fprintf('   After removeCustom: hasCustom = %s\n', string(hasItNow));
    end

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% 7. FULL WORKFLOW (navigate + analyze + store)
fprintf('7. FULL WORKFLOW (per riekesuitworkflow.md)\n');
fprintf('   ----------------------------------------\n');

try
    analysisLog = {};

    % Navigate tree and analyze
    for i = 1:tree.childrenLength()
        cellTypeNode = tree.childAt(i);
        cellType = cellTypeNode.splitValue;

        for j = 1:cellTypeNode.childrenLength()
            protocolNode = cellTypeNode.childAt(j);
            protocolName = protocolNode.splitValue;

            % Get epochs from this node
            epochs = protocolNode.getAllEpochs(false);

            if ~isempty(epochs)
                % Create results
                results = struct();
                results.cellType = cellType;
                results.protocol = protocolName;
                results.n_epochs = length(epochs);
                results.timestamp = now;

                % Store at this node
                protocolNode.putCustom('results', results);

                % Log
                analysisLog{end+1} = sprintf('%s | %s | n=%d', ...
                    string(cellType), string(protocolName), length(epochs));
            end
        end
    end

    fprintf('   Analyzed %d conditions\n', length(analysisLog));
    for i = 1:min(5, length(analysisLog))
        fprintf('     %s\n', analysisLog{i});
    end
    if length(analysisLog) > 5
        fprintf('     ... and %d more\n', length(analysisLog) - 5);
    end

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n', ME.message);
    disp(getReport(ME));
    return;
end

%% 8. GET DATA FROM LEAF NODES (with H5 lazy loading)
fprintf('8. GET DATA FROM LEAF NODES\n');
fprintf('   ------------------------\n');

try
    if ~isempty(leaves)
        testLeaf = leaves{1};
        fprintf('   Testing leaf: %s\n', testLeaf.pathString());
        fprintf('   Epochs in leaf: %d\n', length(testLeaf.epochList));

        % Get H5 file path
        if isfield(data, 'experiments')
            if iscell(data.experiments)
                exp = data.experiments{1};
            else
                exp = data.experiments(1);
            end
            if isfield(exp, 'exp_name')
                exp_name = exp.exp_name;
            elseif isfield(exp, 'h5_file')
                h5_file = exp.h5_file;
            else
                exp_name = '2025-12-02_F';
            end
        else
            exp_name = '2025-12-02_F';
        end

        if ~exist('h5_file', 'var')
            h5_file = getH5FilePath(exp_name);
        end
        fprintf('   H5 file: %s\n', h5_file);

        % Use getSelectedData
        [dataMatrix, epochs, sampleRate] = epicTreeTools.getSelectedData(testLeaf, 'Amp1', h5_file);
        fprintf('   getSelectedData returned:\n');
        fprintf('     dataMatrix size: [%d x %d]\n', size(dataMatrix, 1), size(dataMatrix, 2));
        fprintf('     epochs: %d\n', length(epochs));
        fprintf('     sampleRate: %g Hz\n', sampleRate);

        if ~isempty(dataMatrix) && any(dataMatrix(:) ~= 0)
            fprintf('     data range: [%.4f, %.4f]\n', min(dataMatrix(:)), max(dataMatrix(:)));
            fprintf('   [PASS] Data loaded from H5!\n\n');
        else
            fprintf('   [WARN] Data is empty or zeros (check H5 paths)\n\n');
        end
    end
catch ME
    fprintf('   [FAIL] %s\n', ME.message);
    disp(getReport(ME));
end

%% Summary
fprintf('========================================\n');
fprintf('  TEST COMPLETE\n');
fprintf('========================================\n\n');

fprintf('Real data summary:\n');
fprintf('  Experiment: %s\n', dataPath);
fprintf('  Total epochs: %d\n', length(allEpochs));
fprintf('  Tree depth: %d levels\n', leaves{1}.depth());
fprintf('  Leaf nodes: %d\n', length(leaves));
fprintf('\n');

fprintf('Navigation API:\n');
fprintf('  DOWN: childAt(i), childrenLength(), childBySplitValue(v), leafNodes()\n');
fprintf('  UP:   parent, parentAt(n), getRoot(), depth(), pathFromRoot(), pathString()\n');
fprintf('\n');

fprintf('Controlled access:\n');
fprintf('  putCustom(key, value), getCustom(key), hasCustom(key), removeCustom(key)\n');

%% Helper function
function showTreeStructure(node, maxDepth, depth)
    if nargin < 3
        depth = 0;
    end

    indent = repmat('   ', 1, depth);

    if isempty(node.splitValue)
        name = 'Root';
    else
        name = string(node.splitValue);
    end

    if node.isLeaf
        fprintf('%s- %s (%d epochs)\n', indent, name, length(node.epochList));
    else
        fprintf('%s+ %s (%d children)\n', indent, name, node.childrenLength());
        if depth < maxDepth
            for i = 1:min(node.childrenLength(), 3)
                showTreeStructure(node.childAt(i), maxDepth, depth + 1);
            end
            if node.childrenLength() > 3
                fprintf('%s   ... +%d more\n', indent, node.childrenLength() - 3);
            end
        end
    end
end
