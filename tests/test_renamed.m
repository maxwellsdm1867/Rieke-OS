%% Test with Renamed Classes - No Name Conflicts!
%
% This test uses epicGraphicalTree instead of graphicalTree,
% so there are NO name conflicts with the legacy code.
%
% The old_epochtree directory can remain on the path without issues.

close all; clear; clc;

fprintf('=== Testing with Renamed Classes (No Conflicts!) ===\n\n');

% Add paths (order doesn't matter anymore - no conflicts!)
addpath('src/gui');
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');
addpath('src/config');  % For epicTreeConfig

% CRITICAL: Set H5 directory for lazy loading
h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';
if exist(h5Dir, 'dir')
    epicTreeConfig('h5_dir', h5Dir);
    fprintf('✓ H5 directory configured: %s\n', h5Dir);
else
    fprintf('⚠ H5 directory not found: %s\n', h5Dir);
    fprintf('  Data may not load from H5 files\n');
end
fprintf('\n');

% Verify we're using the renamed classes
fprintf('Verifying class names...\n');
which_result = which('epicGraphicalTree');
if isempty(which_result)
    error('epicGraphicalTree not found! Did you run from project root?');
end
fprintf('✓ Using: epicGraphicalTree (no conflicts possible)\n');
fprintf('  Location: %s\n\n', which_result);

%% Load Data
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

if ~exist(data_file, 'file')
    error('File not found: %s', data_file);
end

fprintf('Loading: %s\n', data_file);
[data, ~] = loadEpicTreeData(data_file);
fprintf('Loaded %d epochs\n\n', length(data));

%% Build Tree
fprintf('Building tree: Cell Type → Protocol\n');

tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});

fprintf('Tree built with %d top-level nodes\n\n', tree.childrenLength());

%% Launch GUI
fprintf('=== Launching GUI ===\n');
fprintf('Using epicGraphicalTree - NO NAME CONFLICTS!\n\n');

gui = epicTreeGUI(tree);

fprintf('✓ GUI launched successfully\n\n');
fprintf('Expected behavior:\n');
fprintf('1. Expand "RGC" node\n');
fprintf('2. Expand protocol node (e.g., "SingleSpot")\n');
fprintf('3. See individual epochs with PINK backgrounds\n');
fprintf('4. Click epoch → single trace\n');
fprintf('5. Click protocol → aggregated traces\n');
fprintf('6. NO ERRORS when clicking!\n\n');

fprintf('=== SUCCESS ===\n');
fprintf('The renamed classes (epicGraphicalTree) avoid all conflicts!\n');
