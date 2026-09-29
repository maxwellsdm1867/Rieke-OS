%% Test EpicTreeGUI with Different Split Configurations
% This script launches the GUI and demonstrates tree reorganization

clear all;
close all;
clc;

fprintf('=== Testing EpicTreeGUI Split Display ===\n\n');

% Add paths
addpath('src');
addpath('src/splitters');
addpath('src/tree');
addpath('src/tree/graphicalTree');

% Path to the data file
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

if ~exist(data_file, 'file')
    error('File not found: %s\nPlease update the path to your test data.', data_file);
end

fprintf('Data file: %s\n', data_file);
fprintf('Loading GUI...\n\n');

% Launch the GUI with data
gui = epicTreeGUI(data_file);

fprintf('=== GUI LAUNCHED ===\n\n');
fprintf('AVAILABLE SPLIT CONFIGURATIONS:\n');
fprintf('--------------------------------\n');
fprintf('1. Cell Type         - Groups by cellInfo.type\n');
fprintf('2. Contrast          - Groups by parameters.contrast\n');
fprintf('3. Protocol          - Groups by protocol name\n');
fprintf('4. Date              - Groups by experiment date\n');
fprintf('5. Cell Type + Contrast - Two-level hierarchy\n\n');

fprintf('TESTING INSTRUCTIONS:\n');
fprintf('--------------------\n');
fprintf('1. Use the "Split by" dropdown at the top of the tree panel\n');
fprintf('2. Watch the tree reorganize when you change the split\n');
fprintf('3. Expand nodes by clicking the [+] icon\n');
fprintf('4. Click on any node to see data in the right panel\n');
fprintf('5. Use checkboxes to select/deselect epochs\n\n');

fprintf('TREE NAVIGATION:\n');
fprintf('----------------\n');
fprintf('- Click [+] to expand a node and show its children\n');
fprintf('- Click [-] to collapse a node\n');
fprintf('- Click the node name to select it and view data\n');
fprintf('- Each node shows (N) where N = number of epochs\n\n');

fprintf('Try switching between different splits to see\n');
fprintf('how the same data reorganizes dynamically!\n\n');
