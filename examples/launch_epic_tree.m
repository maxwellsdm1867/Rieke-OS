function launch_epic_tree()
    % LAUNCH_EPIC_TREE Safe launcher for epicTreeGUI
    %
    % This function ensures the correct paths are set up before using
    % any epicTreeGUI functionality. It prevents the "brace indexing"
    % error by ensuring the NEW graphicalTree.m is loaded.
    %
    % Usage:
    %   launch_epic_tree
    %
    % After running this, you can use:
    %   run test_epoch_display.m
    %   run test_legacy_pattern.m
    %   gui = epicTreeGUI('data.mat')

    fprintf('\n=== EpicTreeGUI Launcher ===\n\n');

    % Ensure we're in the right directory
    [scriptPath, ~, ~] = fileparts(mfilename('fullpath'));
    cd(scriptPath);
    fprintf('Working directory: %s\n', pwd);

    % Clear and reset
    fprintf('Clearing workspace...\n');
    close all;
    clear classes;

    % Remove old code from path
    fprintf('Removing old code from path...\n');
    warning('off', 'MATLAB:rmpath:DirNotFound');
    rmpath(genpath('old_epochtree'));
    warning('on', 'MATLAB:rmpath:DirNotFound');

    % Add correct paths (order matters!)
    fprintf('Adding new code paths...\n');
    addpath('src/gui');           % CRITICAL: graphicalTree
    addpath('src/tree');          % epicTreeTools
    addpath('src/splitters');     % Splitter functions
    addpath('src/utilities');     % Helper functions
    addpath('src');               % Main code

    % Verify correct version is loaded
    fprintf('Verifying graphicalTree...\n');
    which_result = which('graphicalTree');

    if ~contains(which_result, 'src/gui')
        error(['❌ ERROR: Wrong graphicalTree loaded!\n' ...
               '\n' ...
               'Expected: .../src/gui/graphicalTree.m\n' ...
               'Got:      %s\n' ...
               '\n' ...
               'FIX:\n' ...
               '1. Close MATLAB completely\n' ...
               '2. Restart MATLAB\n' ...
               '3. Run: restoredefaultpath\n' ...
               '4. cd(''/Users/maxwellsdm/Documents/GitHub/epicTreeGUI'')\n' ...
               '5. Run: launch_epic_tree\n'], which_result);
    end

    fprintf('\n');
    fprintf('✅ SUCCESS! Paths configured correctly.\n');
    fprintf('   Using: %s\n\n', which_result);

    fprintf('Ready to use epicTreeGUI!\n\n');
    fprintf('Quick start:\n');
    fprintf('  run test_epoch_display.m    - Test epoch flattening\n');
    fprintf('  run test_legacy_pattern.m   - Test legacy tree building\n');
    fprintf('  gui = epicTreeGUI(''data.mat'')  - Launch GUI with file\n\n');

    fprintf('=== Setup Complete ===\n\n');
end
