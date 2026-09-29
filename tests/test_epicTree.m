%% Test EpicTreeGUI with real data
% Test script to verify tree building and data access
%
% This follows the retinanalysis pattern where:
% 1. Configure H5 directory once at startup
% 2. Load .mat file containing metadata and h5_paths
% 3. Data is lazy-loaded from H5 files when needed

clear; clc;

%% Add paths
addpath(genpath('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src'));

%% Configure H5 directory (like retinanalysis H5_DIR)
% This only needs to be set once per session
epicTreeConfig('h5_dir', '/Users/maxwellsdm/Documents/epicTreeTest/h5');
fprintf('H5 directory: %s\n', epicTreeConfig('h5_dir'));

%% Load data
dataPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
fprintf('Loading data from: %s\n', dataPath);

data = load(dataPath);
fprintf('Loaded variables: %s\n', strjoin(fieldnames(data), ', '));

%% Inspect data structure
disp('--- Data Structure ---');
fn = fieldnames(data);
for i = 1:length(fn)
    val = data.(fn{i});
    if isstruct(val)
        fprintf('%s: struct with fields: %s\n', fn{i}, strjoin(fieldnames(val), ', '));
    elseif iscell(val)
        fprintf('%s: cell array [%s]\n', fn{i}, num2str(size(val)));
    else
        fprintf('%s: %s [%s]\n', fn{i}, class(val), num2str(size(val)));
    end
end

%% Try to understand the epoch structure
% Look for epochs in the data
disp('');
disp('--- Looking for epochs ---');

% Check common field names
possibleEpochFields = {'epochs', 'epochList', 'experiments', 'cells', 'data'};
for i = 1:length(possibleEpochFields)
    if isfield(data, possibleEpochFields{i})
        fprintf('Found field: %s\n', possibleEpochFields{i});
    end
end

%% If we have experiments structure, explore it
if isfield(data, 'experiments')
    disp('');
    disp('--- Experiments Structure ---');
    exps = data.experiments;
    fprintf('Number of experiments: %d\n', length(exps));
    if length(exps) > 0
        % Handle both cell array and struct array
        if iscell(exps)
            exp1 = exps{1};
        else
            exp1 = exps(1);
        end
        fprintf('Experiment 1 fields: %s\n', strjoin(fieldnames(exp1), ', '));

        if isfield(exp1, 'cells')
            cells = exp1.cells;
            if iscell(cells)
                fprintf('  Number of cells: %d\n', length(cells));
                if length(cells) > 0
                    cell1 = cells{1};
                end
            else
                fprintf('  Number of cells: %d\n', length(cells));
                if length(cells) > 0
                    cell1 = cells(1);
                end
            end

            if exist('cell1', 'var')
                fprintf('  Cell 1 fields: %s\n', strjoin(fieldnames(cell1), ', '));

                if isfield(cell1, 'epoch_groups')
                    egs = cell1.epoch_groups;
                    if iscell(egs)
                        fprintf('    Number of epoch_groups: %d\n', length(egs));
                        if length(egs) > 0
                            eg1 = egs{1};
                            fprintf('    EpochGroup 1 fields: %s\n', strjoin(fieldnames(eg1), ', '));

                            if isfield(eg1, 'epoch_blocks')
                                ebs = eg1.epoch_blocks;
                                if iscell(ebs)
                                    fprintf('      Number of epoch_blocks: %d\n', length(ebs));
                                    if length(ebs) > 0
                                        eb1 = ebs{1};
                                        fprintf('      EpochBlock 1 fields: %s\n', strjoin(fieldnames(eb1), ', '));

                                        if isfield(eb1, 'epochs')
                                            eps = eb1.epochs;
                                            if iscell(eps)
                                                fprintf('        Number of epochs: %d\n', length(eps));
                                                if length(eps) > 0
                                                    epoch1 = eps{1};
                                                    fprintf('        Epoch 1 fields: %s\n', strjoin(fieldnames(epoch1), ', '));
                                                end
                                            end
                                        end
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end
    end
end

%% Try loading with loadEpicTreeData
disp('');
disp('--- Try loadEpicTreeData ---');
try
    [treeData, metadata] = loadEpicTreeData(dataPath);
    fprintf('loadEpicTreeData succeeded!\n');
    fprintf('treeData fields: %s\n', strjoin(fieldnames(treeData), ', '));
catch ME
    fprintf('loadEpicTreeData failed: %s\n', ME.message);
    fprintf('Will try direct approach...\n');
end

%% Try creating epicTreeTools
disp('');
disp('--- Try epicTreeTools ---');
try
    tree = epicTreeTools(data);
    fprintf('epicTreeTools created!\n');
    fprintf('tree properties: splitKey=%s, isLeaf=%d\n', ...
        string(tree.splitKey), tree.isLeaf);
catch ME
    fprintf('epicTreeTools failed: %s\n', ME.message);
    disp(getReport(ME));
end

%% Try building tree with splitters
disp('');
disp('--- Try buildTree ---');
try
    tree.buildTree({'cellInfo.type'});
    fprintf('buildTree succeeded!\n');
    fprintf('Number of children: %d\n', length(tree.children));

    % Show tree structure
    disp('Tree structure:');
    showTreeStructure(tree, 0);
catch ME
    fprintf('buildTree failed: %s\n', ME.message);
    disp(getReport(ME));
end

%% Try getAllEpochs
disp('');
disp('--- Try getAllEpochs ---');
try
    allEpochs = tree.getAllEpochs(false);
    fprintf('Total epochs: %d\n', length(allEpochs));

    if length(allEpochs) > 0
        ep1 = allEpochs{1};
        fprintf('Epoch 1 fields: %s\n', strjoin(fieldnames(ep1), ', '));

        if isfield(ep1, 'responses')
            fprintf('  Number of responses: %d\n', length(ep1.responses));
        end
        if isfield(ep1, 'parameters')
            fprintf('  Parameters: %s\n', strjoin(fieldnames(ep1.parameters), ', '));
        end
    end
catch ME
    fprintf('getAllEpochs failed: %s\n', ME.message);
end

%% Test different split configurations
disp('');
disp('--- Test Multi-Level Splits ---');
try
    % Rebuild with multiple split keys
    tree2 = epicTreeTools(data);
    tree2.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});
    fprintf('Multi-level tree: %d top-level children\n', length(tree2.children));

    % Show structure
    disp('Tree with cellType + protocol:');
    showTreeStructure(tree2, 0);
catch ME
    fprintf('Multi-level split failed: %s\n', ME.message);
end

%% Get H5 file path for lazy loading
% Extract experiment name from loaded data to construct H5 path
disp('');
disp('--- Get H5 File Path ---');
try
    % Get exp_name from loaded data
    if isfield(data, 'experiments') && iscell(data.experiments) && ~isempty(data.experiments)
        exp = data.experiments{1};
        if isfield(exp, 'exp_name')
            exp_name = exp.exp_name;
        else
            exp_name = '2025-12-02_F';  % Fallback
        end
    else
        exp_name = '2025-12-02_F';  % Fallback
    end

    % Get H5 file path using config (like retinanalysis pattern)
    h5_file = getH5FilePath(exp_name);
    fprintf('Experiment: %s\n', exp_name);
    fprintf('H5 file: %s\n', h5_file);

    if exist(h5_file, 'file')
        fprintf('  ✓ H5 file exists\n');
    else
        fprintf('  ✗ H5 file NOT FOUND\n');
    end
catch ME
    fprintf('Failed to get H5 path: %s\n', ME.message);
    h5_file = '';
end

%% Test getSelectedData
disp('');
disp('--- Test getSelectedData ---');
try
    % Get data from a leaf node
    if ~isempty(tree.children)
        leafNode = tree.children{1};
        fprintf('Testing on node: %s\n', string(leafNode.splitValue));

        % Pass h5_file for lazy loading from H5
        [dataMatrix, epochs, sampleRate] = epicTreeTools.getSelectedData(leafNode, 'Amp1', h5_file);
        fprintf('getSelectedData returned:\n');
        fprintf('  dataMatrix size: [%d x %d]\n', size(dataMatrix, 1), size(dataMatrix, 2));
        fprintf('  epochs: %d\n', length(epochs));
        fprintf('  sampleRate: %g Hz\n', sampleRate);

        % Check if data looks reasonable
        if ~isempty(dataMatrix)
            fprintf('  data range: [%.2f, %.2f]\n', min(dataMatrix(:)), max(dataMatrix(:)));
        else
            fprintf('  ✗ dataMatrix is EMPTY - check H5 loading\n');
        end
    end
catch ME
    fprintf('getSelectedData failed: %s\n', ME.message);
    disp(getReport(ME));
end

%% Test getResponseMatrix directly
disp('');
disp('--- Test getResponseMatrix ---');
try
    % Get first 5 epochs
    testEpochs = allEpochs(1:min(5, length(allEpochs)));

    % Pass h5_file for lazy loading
    [respMatrix, fs] = epicTreeTools.getResponseMatrix(testEpochs, 'Amp1', h5_file);
    fprintf('getResponseMatrix returned:\n');
    fprintf('  matrix size: [%d x %d]\n', size(respMatrix, 1), size(respMatrix, 2));
    fprintf('  sample rate: %g Hz\n', fs);

    if ~isempty(respMatrix) && any(respMatrix(:) ~= 0)
        fprintf('  data range: [%.4f, %.4f]\n', min(respMatrix(:)), max(respMatrix(:)));
        fprintf('  ✓ Data loaded successfully!\n');
    else
        fprintf('  ✗ Data is empty or all zeros\n');
    end
catch ME
    fprintf('getResponseMatrix failed: %s\n', ME.message);
    disp(getReport(ME));
end

%% Test getMeanResponseTrace
disp('');
disp('--- Test getMeanResponseTrace ---');
try
    if exist('testEpochs', 'var') && ~isempty(testEpochs)
        % getMeanResponseTrace expects (epochs, streamName)
        % Need to pass h5_file through - let's update epochs to have h5_file
        for i = 1:length(testEpochs)
            testEpochs{i}.h5_file = h5_file;
        end

        result = epicTreeTools.getMeanResponseTrace(testEpochs, 'Amp1');
        fprintf('getMeanResponseTrace returned:\n');
        fprintf('  n: %d\n', result.n);
        fprintf('  mean length: %d\n', length(result.mean));
        fprintf('  timeVector length: %d\n', length(result.timeVector));
        fprintf('  mean range: [%.2f, %.2f]\n', min(result.mean), max(result.mean));

        % Quick plot to verify
        fprintf('  ✓ Analysis complete!\n');
    else
        fprintf('  No epochs to analyze\n');
    end
catch ME
    fprintf('getMeanResponseTrace failed: %s\n', ME.message);
end

%% List available response streams
disp('');
disp('--- Available Response Streams ---');
if ~isempty(allEpochs)
    ep = allEpochs{1};
    if isfield(ep, 'responses')
        for i = 1:length(ep.responses)
            resp = ep.responses(i);
            if iscell(ep.responses)
                resp = ep.responses{i};
            end
            fprintf('  %s: %d samples @ %g Hz\n', resp.device_name, length(resp.data), resp.sample_rate);
        end
    end
end

disp('');
disp('=== Test Complete ===');

%% Helper function
function showTreeStructure(node, depth)
    indent = repmat('  ', 1, depth);
    if isempty(node.splitValue)
        name = 'Root';
    else
        name = string(node.splitValue);
    end

    if node.isLeaf
        fprintf('%s- %s (leaf, %d epochs)\n', indent, name, length(node.epochList));
    else
        fprintf('%s+ %s (%d children)\n', indent, name, length(node.children));
        for i = 1:min(length(node.children), 5)  % Show first 5
            showTreeStructure(node.children{i}, depth + 1);
        end
        if length(node.children) > 5
            fprintf('%s  ... and %d more\n', indent, length(node.children) - 5);
        end
    end
end
