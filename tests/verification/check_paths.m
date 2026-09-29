%% Check Paths and Fix graphicalTree Loading Issue
% This diagnostic script identifies which graphicalTree is being used
% and fixes path issues

close all;
clear;
clc;

fprintf('=== PATH DIAGNOSTIC ===\n\n');

%% 1. Check which graphicalTree is loaded
fprintf('1. Checking which graphicalTree.m is on path:\n');
which_result = which('graphicalTree', '-all');

if isempty(which_result)
    fprintf('   ERROR: No graphicalTree found!\n');
else
    for i = 1:length(which_result)
        fprintf('   [%d] %s\n', i, which_result{i});

        % Check if it's the old or new version
        if contains(which_result{i}, 'old_epochtree')
            fprintf('       ❌ OLD VERSION (will cause errors)\n');
        elseif contains(which_result{i}, 'src/gui')
            fprintf('       ✅ NEW VERSION (correct)\n');
        end
    end
end

fprintf('\n');

%% 2. Check if old_epochtree is on path
fprintf('2. Checking if old_epochtree is on MATLAB path:\n');
current_path = path;
if contains(current_path, 'old_epochtree')
    fprintf('   ❌ WARNING: old_epochtree IS on the path!\n');
    fprintf('   This will cause conflicts.\n');
else
    fprintf('   ✅ Good: old_epochtree is NOT on the path\n');
end

fprintf('\n');

%% 3. Fix the path
fprintf('3. Fixing path...\n');

% Remove old_epochtree completely
warning('off', 'MATLAB:rmpath:DirNotFound');
rmpath(genpath('old_epochtree'));
warning('on', 'MATLAB:rmpath:DirNotFound');
fprintf('   ✓ Removed old_epochtree from path\n');

% Add new code in correct order
addpath('src/gui');
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src');
fprintf('   ✓ Added src directories to path\n');

fprintf('\n');

%% 4. Verify fix
fprintf('4. Verifying fix:\n');
which_result_after = which('graphicalTree');

fprintf('   Now using: %s\n', which_result_after);

if contains(which_result_after, 'src/gui')
    fprintf('   ✅ SUCCESS: Correct version is loaded\n\n');
    fprintf('You can now run: test_epoch_display\n');
else
    fprintf('   ❌ STILL WRONG!\n\n');
    fprintf('Manual fix needed:\n');
    fprintf('1. Close MATLAB completely\n');
    fprintf('2. Restart MATLAB\n');
    fprintf('3. Run this command FIRST:\n');
    fprintf('   restoredefaultpath; cd(''/Users/maxwellsdm/Documents/GitHub/epicTreeGUI'');\n');
    fprintf('4. Then run: check_paths\n');
end

fprintf('\n=== DIAGNOSTIC COMPLETE ===\n');
