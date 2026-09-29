%% Test Fixed GUI
% Should now work without errors when clicking nodes

clear all;
close all;
clc;

fprintf('=== Testing Fixed GUI ===\n\n');

% Add paths
addpath('src');
addpath('src/splitters');
addpath('src/tree');
addpath('src/tree/graphicalTree');

% Data file
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

fprintf('Launching GUI with: %s\n', data_file);
fprintf('Fix applied: Table data now uses char instead of string objects\n\n');

% Launch GUI
gui = epicTreeGUI(data_file);

fprintf('=== TEST THE FIX ===\n');
fprintf('1. Click on any node in the tree\n');
fprintf('2. The info table should update WITHOUT errors\n');
fprintf('3. Try different dropdown options:\n');
fprintf('   - Cell Type + Cell ID\n');
fprintf('   - Cell Type + Date + Cell ID\n');
fprintf('4. Expand nodes with [+] and click on children\n\n');

fprintf('The error "Values within a cell array must be numeric, logical, or char"\n');
fprintf('should now be FIXED!\n\n');
