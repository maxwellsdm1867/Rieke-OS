function [matPath, h5Dir] = getTestDataPath()
% getTestDataPath - Get paths to test data for epicTreeGUI tests
%
% Returns:
%   matPath - Path to test .mat file
%   h5Dir   - Path to directory containing .h5 files
%
% This function provides centralized test data path resolution for all test
% scripts. Set RIEKE_TEST_MAT and RIEKE_H5_DIR to your local fixtures.
% Scientific recording exports are not distributed with the source package.
%
% Example:
%   [matPath, h5Dir] = getTestDataPath();
%   [data, h5File] = loadEpicTreeData(matPath);

    % Get path to test data file
    % Read explicit local fixture configuration; never guess a personal path.
    matPath = getenv('RIEKE_TEST_MAT');
    h5Dir = getenv('RIEKE_H5_DIR');

    % Verify file exists
    if ~isfile(matPath)
        error('epicTreeGUI:TestDataNotFound', ...
            ['Test data file not found: %s\n\n' ...
             'Set RIEKE_TEST_MAT to your local scientific fixture MAT file.\n' ...
             'See TESTING.md for data preparation instructions.'], matPath);
    end

    % Verify H5 directory exists
    if ~isfolder(h5Dir)
        warning('epicTreeGUI:H5DirNotFound', ...
            'H5 directory not found: %s\nSome tests may fail.', h5Dir);
    end
end
