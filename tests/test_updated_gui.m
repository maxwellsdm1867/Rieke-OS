%% Test Updated GUI with Better Splits
% Now includes: Cell Type, Cell Type + Cell ID, Cell Type + Date + Cell ID

clear all;
close all;
clc;

fprintf('=== Launching Updated EpicTreeGUI ===\n\n');

% Add paths
addpath('src');
addpath('src/splitters');
addpath('src/tree');
addpath('src/tree/graphicalTree');

% Data file
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

if ~exist(data_file, 'file')
    error('File not found: %s', data_file);
end

fprintf('Loading data: %s\n', data_file);
fprintf('Launching GUI...\n\n');

% Launch GUI
gui = epicTreeGUI(data_file);

fprintf('=== UPDATED DROPDOWN OPTIONS ===\n\n');
fprintf('1. Cell Type\n');
fprintf('   - Groups all epochs by cell type (OnP, OffP, RGC, etc.)\n\n');

fprintf('2. Cell Type + Cell ID\n');
fprintf('   - First level: Cell types\n');
fprintf('   - Second level: Individual cells within each type\n');
fprintf('   - Click [+] to expand and see cells!\n\n');

fprintf('3. Cell Type + Date + Cell ID\n');
fprintf('   - First level: Cell types\n');
fprintf('   - Second level: Experiment dates\n');
fprintf('   - Third level: Individual cells\n');
fprintf('   - This creates a 3-level hierarchy!\n\n');

fprintf('4. Contrast\n');
fprintf('   - Groups by stimulus contrast (if parameter exists)\n\n');

fprintf('5. Protocol\n');
fprintf('   - Groups by experimental protocol name\n\n');

fprintf('6. Date\n');
fprintf('   - Groups by experiment date\n\n');

fprintf('=== HOW TO USE ===\n');
fprintf('1. Click the dropdown at the top\n');
fprintf('2. Select "Cell Type + Cell ID" or "Cell Type + Date + Cell ID"\n');
fprintf('3. Watch the tree rebuild with nested levels\n');
fprintf('4. Click [+] icons to EXPAND nodes and see children\n');
fprintf('5. Click [-] icons to COLLAPSE nodes\n');
fprintf('6. Click node names to select and view data\n\n');
