%% Test H5 Lazy Loading in GUI
% This verifies that data is ONLY loaded when you click, not at startup

close all; clear; clc;

fprintf('=== Testing H5 Lazy Loading ===\n\n');

% Add paths
addpath('src/gui');
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');

% Configure H5 directory
h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';
if ~exist(h5Dir, 'dir')
    error('H5 directory not found: %s', h5Dir);
end
epicTreeConfig('h5_dir', h5Dir);
fprintf('H5 directory: %s\n', h5Dir);

% Load data
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
fprintf('Loading: %s\n', data_file);
[data, ~] = loadEpicTreeData(data_file);
fprintf('Loaded %d epochs\n\n', length(data));

% Build tree
fprintf('Building tree...\n');
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});
fprintf('Tree built\n\n');

% Launch GUI
fprintf('=== Launching GUI ===\n');
fprintf('DATA IS NOT LOADED YET - only metadata in memory\n');
fprintf('When you CLICK a node, it will lazy load from H5\n\n');

gui = epicTreeGUI(tree);

fprintf('✓ GUI launched\n\n');
fprintf('Instructions:\n');
fprintf('1. Click on "SingleSpot" → Should load and plot data\n');
fprintf('2. Click on individual epoch (#1, #2) → Should load single epoch\n');
fprintf('3. Data is loaded ON DEMAND from H5 files\n');
fprintf('4. No slowdown at startup!\n');
