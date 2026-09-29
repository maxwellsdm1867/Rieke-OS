function install()
% INSTALL  Add epicTreeGUI to MATLAB path
%
% Usage:
%   install
%
% Description:
%   Adds all epicTreeGUI source directories to the MATLAB path and
%   verifies that the installation succeeded. Optionally saves the
%   path for future MATLAB sessions.
%
% What gets added to path:
%   - epicTreeGUI root directory (epicTreeGUI.m)
%   - src/                   (getSelectedData, loadEpicTreeData, etc.)
%   - src/tree/              (epicTreeTools)
%   - src/gui/               (visual tree rendering)
%   - src/splitters/         (splitter functions)
%   - src/utilities/         (utility functions)
%   - src/config/            (if exists)
%
% After installation:
%   - Run 'help epicTreeTools' to verify installation
%   - See README.md for usage examples
%
% Example:
%   cd /path/to/epicTreeGUI
%   install
%
% See also: ADDPATH, SAVEPATH, RMPATH

% Copyright (c) 2026 The epicTreeGUI Authors
% MIT License

    fprintf('\n');
    fprintf('========================================\n');
    fprintf('  epicTreeGUI Installation\n');
    fprintf('========================================\n\n');

    % Get installation directory from this script's location
    installDir = fileparts(mfilename('fullpath'));
    fprintf('[INFO] Installation directory: %s\n\n', installDir);

    % Check that src/ directory exists
    srcDir = fullfile(installDir, 'src');
    if ~exist(srcDir, 'dir')
        fprintf('[ERROR] Source directory not found: %s\n', srcDir);
        fprintf('[ERROR] Please ensure you are running install.m from the epicTreeGUI root directory.\n');
        error('Installation failed: src/ directory not found');
    end

    % Define paths to add (explicit subdirectories only, not genpath)
    pathsToAdd = {
        installDir,                                    % Root (epicTreeGUI.m)
        fullfile(installDir, 'src'),                   % Core functions
        fullfile(installDir, 'src', 'tree'),           % epicTreeTools
        fullfile(installDir, 'src', 'gui'),              % GUI & visual tree
        fullfile(installDir, 'src', 'splitters'),      % Splitter functions
        fullfile(installDir, 'src', 'utilities')       % Utilities
    };

    % Add src/config/ if it exists
    configDir = fullfile(installDir, 'src', 'config');
    if exist(configDir, 'dir')
        pathsToAdd{end+1} = configDir;
    end

    % Add paths
    fprintf('[INFO] Adding paths to MATLAB:\n');
    for i = 1:length(pathsToAdd)
        if exist(pathsToAdd{i}, 'dir')
            addpath(pathsToAdd{i});
            fprintf('  [OK] %s\n', pathsToAdd{i});
        else
            fprintf('  [WARN] Directory not found (skipping): %s\n', pathsToAdd{i});
        end
    end
    fprintf('\n');

    % Verify installation
    fprintf('[INFO] Verifying installation...\n');
    verificationPassed = true;

    % Check epicTreeTools
    epicTreeToolsPath = which('epicTreeTools');
    if isempty(epicTreeToolsPath)
        fprintf('  [ERROR] epicTreeTools not found on path\n');
        verificationPassed = false;
    elseif ~startsWith(epicTreeToolsPath, installDir)
        fprintf('  [WARN] epicTreeTools found but not from this installation:\n');
        fprintf('         %s\n', epicTreeToolsPath);
    else
        fprintf('  [OK] epicTreeTools found: %s\n', epicTreeToolsPath);
    end

    % Check epicTreeGUI
    epicTreeGUIPath = which('epicTreeGUI');
    if isempty(epicTreeGUIPath)
        fprintf('  [ERROR] epicTreeGUI not found on path\n');
        verificationPassed = false;
    elseif ~startsWith(epicTreeGUIPath, installDir)
        fprintf('  [WARN] epicTreeGUI found but not from this installation:\n');
        fprintf('         %s\n', epicTreeGUIPath);
    else
        fprintf('  [OK] epicTreeGUI found: %s\n', epicTreeGUIPath);
    end

    % Check getSelectedData
    getSelectedDataPath = which('getSelectedData');
    if isempty(getSelectedDataPath)
        fprintf('  [ERROR] getSelectedData not found on path\n');
        verificationPassed = false;
    elseif ~startsWith(getSelectedDataPath, installDir)
        fprintf('  [WARN] getSelectedData found but not from this installation:\n');
        fprintf('         %s\n', getSelectedDataPath);
    else
        fprintf('  [OK] getSelectedData found: %s\n', getSelectedDataPath);
    end

    fprintf('\n');

    % Report verification result
    if ~verificationPassed
        fprintf('========================================\n');
        fprintf('[ERROR] Installation verification FAILED\n');
        fprintf('========================================\n');
        fprintf('\nSome required functions were not found on the MATLAB path.\n');
        fprintf('Please check that all source files are present in the installation directory.\n\n');
        error('Installation verification failed');
    end

    fprintf('========================================\n');
    fprintf('[OK] Installation verification PASSED\n');
    fprintf('========================================\n');
    fprintf('\nepicTreeGUI v1.0.0 is now available for this MATLAB session.\n\n');

    % Ask user if they want to save the path
    fprintf('Do you want to save these paths for future MATLAB sessions?\n');
    fprintf('This will modify your MATLAB path permanently.\n\n');

    response = input('Save path? (y/n): ', 's');

    if strcmpi(response, 'y') || strcmpi(response, 'yes')
        try
            savepath;
            fprintf('\n[OK] Path saved successfully.\n');
            fprintf('epicTreeGUI will be available in all future MATLAB sessions.\n\n');
        catch ME
            fprintf('\n[ERROR] Failed to save path:\n');
            fprintf('  %s\n', ME.message);
            fprintf('\nYou may need to run MATLAB as administrator to save the path,\n');
            fprintf('or save to a user-specific pathdef.m file.\n');
            fprintf('\nFor this session, epicTreeGUI is still available.\n\n');
        end
    else
        fprintf('\n[INFO] Path NOT saved.\n');
        fprintf('epicTreeGUI is available for this MATLAB session only.\n');
        fprintf('Run install.m again in future sessions to re-add paths.\n\n');
    end

    % Final usage instructions
    fprintf('========================================\n');
    fprintf('  Quick Start\n');
    fprintf('========================================\n');
    fprintf('Verify installation:\n');
    fprintf('  >> help epicTreeTools\n\n');
    fprintf('Launch GUI:\n');
    fprintf('  >> [data, ~] = loadEpicTreeData(''data.mat'');\n');
    fprintf('  >> tree = epicTreeTools(data);\n');
    fprintf('  >> tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});\n');
    fprintf('  >> gui = epicTreeGUI(tree);\n\n');
    fprintf('For more information, see README.md\n');
    fprintf('========================================\n\n');
end
