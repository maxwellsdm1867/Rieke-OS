%% Test Fix for Blank GUI Issue
% This script tests that the GUI doesn't become blank after
% clicking "Select All", "Clear Selection", or "Set Example"

% Scientific recordings are local-only and never bundled.
if ~isfile(getenv('RIEKE_TEST_MAT'))
    warning('epicTreeGUI:SkippedLocalFixture', ...
        'Skipped: set RIEKE_TEST_MAT to a local recording export.');
    return;
end

close all; clear; clc;

fprintf('=== Testing Blank GUI Fix ===\n\n');

%% Setup Paths
addpath('src/gui');
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');
addpath('src/config');

% Set H5 directory
h5Dir = getenv('RIEKE_H5_DIR');
if exist(h5Dir, 'dir')
    epicTreeConfig('h5_dir', h5Dir);
end

%% Load Data
data_file = getenv('RIEKE_TEST_MAT');

if ~exist(data_file, 'file')
    error('File not found: %s', data_file);
end

fprintf('Loading data: %s\n', data_file);
[data, ~] = loadEpicTreeData(data_file);
fprintf('  Loaded %d epochs\n\n', length(data));

%% Build Tree
fprintf('Building tree...\n');
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnExperimentDate,
    'cellInfo.id'
});
fprintf('  Tree built\n\n');

%% Launch GUI
fprintf('Launching GUI...\n');
gui = epicTreeGUI(tree);
fprintf('✓ GUI launched\n\n');

%% Test Actions That Previously Caused Blank Screen
fprintf('=== Testing Actions ===\n');
fprintf('Manually test these actions and verify tree remains visible:\n\n');
fprintf('  1. Click "Select All" button\n');
fprintf('     → Tree should remain visible with all nodes checked\n\n');
fprintf('  2. Click "Clear Sel" button\n');
fprintf('     → Tree should remain visible with no nodes checked\n\n');
fprintf('  3. Select a node and click "Set Example" button\n');
fprintf('     → Tree should remain visible with node highlighted in pink\n\n');
fprintf('  4. Click "Select All" again\n');
fprintf('     → Tree should still be visible\n\n');

fprintf('If the tree remains visible after all actions, the bug is FIXED!\n');
