%% Test EpicTreeGUI with Legacy Pattern
% This script demonstrates building the tree structure in code
% before launching the GUI, matching the legacy epochTreeGUI workflow.
%
% Compare with legacy code pattern:
%   tree = riekesuite.analysis.buildTree(list, {
%       'protocolSettings(source:type)',
%       dateSplit_java,
%       'cell.label',
%       ...
%   });
%   gui = epochTreeGUI(tree);

close all; clear; clc;

fprintf('=== EpicTreeGUI - Legacy Pattern Demo ===\n\n');

%% CRITICAL: Path Setup and Verification
fprintf('Setting up paths...\n');

% Remove old_epochtree from path
warning('off', 'MATLAB:rmpath:DirNotFound');
rmpath(genpath('old_epochtree'));
warning('on', 'MATLAB:rmpath:DirNotFound');

% Add NEW code paths (in correct order - most specific first)
addpath('src/gui');           % CRITICAL: graphicalTree
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');
addpath('src/config');        % For epicTreeConfig

% Set H5 directory for lazy loading
h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';
if exist(h5Dir, 'dir')
    epicTreeConfig('h5_dir', h5Dir);
end

% Verify correct graphicalTree is loaded
which_result = which('graphicalTree');
if ~contains(which_result, 'src/gui')
    error(['WRONG graphicalTree loaded!\n' ...
           'Run check_paths.m to diagnose and fix.\n' ...
           'Found: %s'], which_result);
end
fprintf('✓ Paths verified\n\n');

%% 1. Load Data
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

if ~exist(data_file, 'file')
    error('File not found: %s', data_file);
end

fprintf('Loading data: %s\n', data_file);
[data, ~] = loadEpicTreeData(data_file);
fprintf('  Loaded %d total epochs\n\n', length(data));

%% 2. Build Tree Structure in Code
% This is where YOU define the hierarchy, just like legacy code:
% tree = riekesuite.analysis.buildTree(list, {...});

fprintf('Building tree with custom splitter hierarchy...\n');

% Create tree root
tree = epicTreeTools(data);

% Define split hierarchy (like legacy code)
% You can mix key paths and function handles
splitHierarchy = {
    @epicTreeTools.splitOnCellType,        % Level 1: Cell Type
    @epicTreeTools.splitOnExperimentDate,  % Level 2: Date
    'cellInfo.id',                        % Level 3: Cell ID
    @epicTreeTools.splitOnProtocol         % Level 4: Protocol
};

% Build the tree
tree.buildTreeWithSplitters(splitHierarchy);

fprintf('  Tree built with %d levels\n', length(splitHierarchy));
fprintf('  Root has %d children (cell types)\n', tree.childrenLength());

% Print tree structure
fprintf('\nTree structure:\n');
for i = 1:tree.childrenLength()
    cellTypeNode = tree.childAt(i);
    fprintf('  [%s] - %d epochs\n', char(cellTypeNode.splitValue), cellTypeNode.epochCount());

    % Show next level
    for j = 1:min(3, cellTypeNode.childrenLength())
        dateNode = cellTypeNode.childAt(j);
        fprintf('    └─ %s - %d epochs\n', char(dateNode.splitValue), dateNode.epochCount());
    end
    if cellTypeNode.childrenLength() > 3
        fprintf('    └─ ... (%d more dates)\n', cellTypeNode.childrenLength() - 3);
    end
end

%% 3. Launch GUI with Pre-Built Tree
fprintf('\n=== Launching GUI ===\n');
fprintf('The tree structure is FIXED - no dropdown to change splits.\n');
fprintf('This matches the legacy epochTreeGUI behavior.\n\n');

% Launch GUI - tree structure is already built
gui = epicTreeGUI(tree);

fprintf('GUI launched. The tree structure you see reflects the code above.\n');
fprintf('To change the hierarchy, modify the splitHierarchy cell array and re-run.\n');
