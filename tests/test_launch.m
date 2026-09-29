%% Launch EpicTreeGUI with Test Data
% This script loads the test data and launches the GUI

clear all;
close all;
clc;

fprintf('=== Launching EpicTreeGUI with Test Data ===\n\n');

% CRITICAL: Remove old_epochtree from path if it's there
warning('off', 'MATLAB:rmpath:DirNotFound');
rmpath(genpath('old_epochtree'));
warning('on', 'MATLAB:rmpath:DirNotFound');

% Add NEW code paths (in correct order - most specific first)
addpath('src/gui');           % CRITICAL: Add this first for graphicalTree
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');

% Path to the data file
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

if ~exist(data_file, 'file')
    error('File not found: %s', data_file);
end

fprintf('Data file found: %s\n', data_file);
fprintf('File size: %.1f KB\n\n', dir(data_file).bytes/1024);

% Launch the GUI
fprintf('Launching EpicTreeGUI...\n');
epicTreeGUI();

fprintf('\n=== GUI Instructions ===\n');
fprintf('1. Click "File > Load Data"\n');
fprintf('2. Select: %s\n', data_file);
fprintf('3. Use the "Split by" dropdown to reorganize the tree\n');
fprintf('4. Click on tree nodes to see spike rasters and PSTHs\n\n');

