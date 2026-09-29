function [matPath, h5Dir] = getTestDataPath()
% getTestDataPath - Get paths to test data for epicTreeGUI tests
%
% Returns:
%   matPath - Path to test .mat file
%   h5Dir   - Path to directory containing .h5 files
%
% This function provides centralized test data path resolution for all test
% scripts. It uses hardcoded paths relative to the test data location.
%
% Example:
%   [matPath, h5Dir] = getTestDataPath();
%   [data, h5File] = loadEpicTreeData(matPath);

    % Get path to test data file
    % Use absolute path to standard test data location
    matPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
    h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';

    % Verify file exists
    if ~isfile(matPath)
        error('epicTreeGUI:TestDataNotFound', ...
            ['Test data file not found: %s\n\n' ...
             'Please ensure test data is available at this location.\n' ...
             'See TESTING.md for data preparation instructions.'], matPath);
    end

    % Verify H5 directory exists
    if ~isfolder(h5Dir)
        warning('epicTreeGUI:H5DirNotFound', ...
            'H5 directory not found: %s\nSome tests may fail.', h5Dir);
    end
end
