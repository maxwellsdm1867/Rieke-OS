%% Test Epoch Display - Individual Epochs at Leaf Level
% This script demonstrates the legacy behavior where individual epochs
% are flattened out as separate nodes at the leaf level of the tree.
%
% Expected behavior:
% 1. Tree shows hierarchy down to protocol level
% 2. Each protocol node expands to show individual epochs
% 3. Individual epochs have pink backgrounds
% 4. Clicking an epoch shows just that single epoch
% 5. Clicking a parent node shows aggregated data from all children

close all; clear; clc;

fprintf('=== Testing Individual Epoch Display ===\n\n');

%% CRITICAL: Path Setup and Verification
% The old graphicalTree.m will cause errors if it's loaded instead of the new one

fprintf('Setting up paths...\n');

% Remove old_epochtree from path
warning('off', 'MATLAB:rmpath:DirNotFound');
rmpath(genpath('old_epochtree'));
warning('on', 'MATLAB:rmpath:DirNotFound');

% Add NEW code paths (order matters!)
addpath('src/gui');
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');

% Verify correct graphicalTree is loaded
which_result = which('graphicalTree');
if ~contains(which_result, 'src/gui')
    error(['WRONG graphicalTree loaded!\n' ...
           'Found: %s\n' ...
           'Expected: .../src/gui/graphicalTree.m\n\n' ...
           'FIX: Close MATLAB, restart, and run:\n' ...
           '  restoredefaultpath;\n' ...
           '  cd(''/Users/maxwellsdm/Documents/GitHub/epicTreeGUI'');\n' ...
           '  run test_epoch_display.m'], which_result);
end

fprintf('✓ Paths verified (using NEW graphicalTree)\n\n');

%% Load Data
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

if ~exist(data_file, 'file')
    error('File not found: %s', data_file);
end

fprintf('Loading: %s\n', data_file);
[data, ~] = loadEpicTreeData(data_file);
fprintf('Loaded %d epochs\n\n', length(data));

%% Build Tree - Split to Protocol Level
% This creates a hierarchy that ends at the protocol level,
% allowing individual epochs to be displayed underneath

fprintf('Building tree: Cell Type → Protocol\n');

tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});

fprintf('Tree structure:\n');
for i = 1:tree.childrenLength()
    cellNode = tree.childAt(i);
    fprintf('  %s (%d epochs)\n', char(cellNode.splitValue), cellNode.epochCount());

    % Show protocols
    for j = 1:min(3, cellNode.childrenLength())
        protocolNode = cellNode.childAt(j);
        nEpochs = protocolNode.epochCount();
        fprintf('    └─ %s (%d individual epochs will be shown)\n', ...
            char(protocolNode.splitValue), nEpochs);
    end
    if cellNode.childrenLength() > 3
        fprintf('    └─ ... (%d more protocols)\n', cellNode.childrenLength() - 3);
    end
end

%% Launch GUI
fprintf('\n=== Launching GUI ===\n');
fprintf('Expected behavior:\n');
fprintf('1. Expand "RGC" node\n');
fprintf('2. Expand a protocol node (e.g., "SingleSpot")\n');
fprintf('3. You should see individual epochs with PINK backgrounds\n');
fprintf('4. Each epoch shows as: "#N: date/time"\n');
fprintf('5. Click an epoch → shows single epoch trace\n');
fprintf('6. Click protocol node → shows all epochs aggregated\n\n');

gui = epicTreeGUI(tree);

fprintf('✓ GUI launched\n');
fprintf('\nInstructions:\n');
fprintf('- Expand tree nodes to see individual epochs\n');
fprintf('- Pink background = individual epoch\n');
fprintf('- Click epoch to see single trace\n');
fprintf('- Click parent to see all traces aggregated\n');
