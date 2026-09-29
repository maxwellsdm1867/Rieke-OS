%% Quick Test - Just Test Class Creation
% Minimal test to verify renamed classes work

close all; clear; clc;

fprintf('=== Quick Class Test ===\n\n');

% Add paths
addpath('src/gui');
addpath('src/tree');
addpath('src');

% Test 1: Can we create epicGraphicalTree?
fprintf('Test 1: Creating epicGraphicalTree...\n');
try
    fig = figure('Visible', 'off');
    ax = axes('Parent', fig);
    tree = epicGraphicalTree(ax, 'TestTree');
    fprintf('   ✓ SUCCESS\n\n');
    delete(fig);
catch ME
    fprintf('   ✗ FAILED: %s\n\n', ME.message);
    if exist('fig', 'var') && ishandle(fig)
        delete(fig);
    end
    error('Cannot create epicGraphicalTree!');
end

% Test 2: Can we create epicGraphicalTreeNode?
fprintf('Test 2: Creating epicGraphicalTreeNode...\n');
try
    node = epicGraphicalTreeNode('TestNode');
    fprintf('   ✓ SUCCESS\n\n');
catch ME
    fprintf('   ✗ FAILED: %s\n\n', ME.message);
    error('Cannot create epicGraphicalTreeNode!');
end

% Test 3: Verify no conflicts with old classes
fprintf('Test 3: Checking for name conflicts...\n');
which_old = which('graphicalTree');
which_new = which('epicGraphicalTree');

fprintf('   Old graphicalTree: %s\n', which_old);
fprintf('   New epicGraphicalTree: %s\n', which_new);

if contains(which_new, 'src/gui')
    fprintf('   ✓ epicGraphicalTree found in correct location\n');
else
    fprintf('   ✗ epicGraphicalTree not found!\n');
    error('epicGraphicalTree not on path!');
end

fprintf('\n=== ALL TESTS PASSED ===\n');
fprintf('Ready to run: test_renamed.m\n');
