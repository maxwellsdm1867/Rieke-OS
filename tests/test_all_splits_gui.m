%% Test All Splitter Options in GUI
% Updated dropdown with Date and Cell Type combinations

clear all;
close all;
clc;

fprintf('=== Testing All Splitter Options ===\n\n');

% Add paths
addpath('src');
addpath('src/splitters');
addpath('src/tree');
addpath('src/tree/graphicalTree');

% Data file
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

fprintf('Launching GUI...\n\n');

% Launch GUI
gui = epicTreeGUI(data_file);

fprintf('=== DROPDOWN OPTIONS ===\n\n');

fprintf('1. Cell Type\n');
fprintf('   - Groups by cell type (RGC, OnP, OffP, etc.)\n\n');

fprintf('2. Date\n');
fprintf('   - Groups by experiment date\n\n');

fprintf('3. Cell Type + Cell ID\n');
fprintf('   - First level: Cell types\n');
fprintf('   - Second level: Individual cells\n\n');

fprintf('4. Date + Cell ID\n');
fprintf('   - First level: Experiment dates\n');
fprintf('   - Second level: Individual cells\n\n');

fprintf('5. Cell Type + Date + Cell ID\n');
fprintf('   - First level: Cell types\n');
fprintf('   - Second level: Dates\n');
fprintf('   - Third level: Individual cells\n\n');

fprintf('6. Date + Cell Type\n');
fprintf('   - First level: Experiment dates\n');
fprintf('   - Second level: Cell types\n\n');

fprintf('7. Protocol\n');
fprintf('   - Groups by experimental protocol\n\n');

fprintf('=== HOW TO USE ===\n');
fprintf('1. Click the dropdown at the top\n');
fprintf('2. Select any split option (2, 4, or 6 are good for your data!)\n');
fprintf('3. Click [+] to expand nodes\n');
fprintf('4. Click node names to select and view data\n');
fprintf('5. Switch between splits to see the tree reorganize!\n\n');

fprintf('RECOMMENDED: Try "Date + Cell ID" or "Date + Cell Type"\n');
fprintf('to see the multi-level hierarchy!\n\n');
