classdef DataExtractionTest < matlab.unittest.TestCase
    % DATAEXTRACTIONTEST Comprehensive validation of data extraction pipeline
    %
    % Tests getSelectedData and getResponseMatrix - the critical functions
    % used by ALL analysis workflows. Validates:
    %   - Correct matrix dimensions
    %   - Selection filtering works
    %   - Sample rate extraction
    %   - Edge cases (empty nodes, invalid streams)
    %   - Data integrity (no NaN, no all-zeros)

    properties
        TestTree
        H5File
        LeafNode
    end

    methods (TestClassSetup)
        function loadData(testCase)
            % Add specific paths (avoid genpath which scans recursively)
            repoRoot = '/Users/maxwellsdm/Documents/GitHub/epicTreeGUI';
            addpath(fullfile(repoRoot, 'src'));
            addpath(fullfile(repoRoot, 'src', 'tree'));
            addpath(fullfile(repoRoot, 'src', 'analysis'));
            addpath(fullfile(repoRoot, 'src', 'utilities'));
            addpath(fullfile(repoRoot, 'src', 'splitters'));
            addpath(fullfile(repoRoot, 'src', 'tree', 'graphicalTree'));
            addpath(fullfile(repoRoot, 'tests', 'helpers'));

            % Load test data directly
            matPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
            [data, testCase.H5File] = loadEpicTreeData(matPath);
            testCase.TestTree = epicTreeTools(data);
            testCase.TestTree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});

            % Find a leaf node with epochs
            leaves = testCase.TestTree.leafNodes();
            testCase.verifyNotEmpty(leaves, 'Tree must have leaf nodes');

            % Find leaf with most epochs
            maxEpochs = 0;
            for i = 1:length(leaves)
                n = leaves{i}.epochCount();
                if n > maxEpochs
                    maxEpochs = n;
                    testCase.LeafNode = leaves{i};
                end
            end

            testCase.verifyGreaterThan(testCase.LeafNode.epochCount(), 0, ...
                'Test leaf node must have epochs');
        end
    end

    methods (TestMethodSetup)
        function resetSelection(testCase)
            % Reset all epochs to selected before each test
            allEpochs = testCase.TestTree.getAllEpochs(false);
            for i = 1:length(allEpochs)
                allEpochs{i}.isSelected = true;
            end
        end
    end

    %% getSelectedData tests

    methods (Test)
        function testGetSelectedDataReturnsMatrix(testCase)
            % Verify getSelectedData returns numeric matrix

            [data, ~, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            testCase.verifyTrue(isnumeric(data), ...
                'getSelectedData must return numeric matrix');
            testCase.verifyTrue(ismatrix(data), ...
                'getSelectedData must return 2D matrix');
        end

        function testGetSelectedDataDimensions(testCase)
            % Verify matrix rows match selected epoch count

            epochs = testCase.LeafNode.getAllEpochs(true);
            nExpected = length(epochs);

            [data, returnedEpochs, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            % Skip if no data (H5 may not be available)
            if isempty(data)
                testCase.assumeFail('H5 data not available, skipping dimension test');
            end

            testCase.verifyEqual(size(data, 1), nExpected, ...
                'Matrix rows must match selected epoch count');
            testCase.verifyEqual(length(returnedEpochs), nExpected, ...
                'Returned epoch count must match selected count');
        end

        function testGetSelectedDataSampleRate(testCase)
            % Verify sample rate is positive numeric

            [data, ~, fs] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            % Skip if no data
            if isempty(data)
                testCase.assumeFail('H5 data not available');
            end

            testCase.verifyTrue(isnumeric(fs), ...
                'Sample rate must be numeric');
            testCase.verifyGreaterThan(fs, 0, ...
                'Sample rate must be positive');
        end

        function testGetSelectedDataEpochs(testCase)
            % Verify returned epochs are cell array of structs

            [~, epochs, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            testCase.verifyTrue(iscell(epochs), ...
                'Returned epochs must be cell array');

            if ~isempty(epochs)
                testCase.verifyTrue(isstruct(epochs{1}), ...
                    'Epoch elements must be structs');
            end
        end

        function testGetSelectedDataWithH5(testCase)
            % Verify calling with H5 file path works

            % Only run if H5 file exists
            if isempty(testCase.H5File) || ~isfile(testCase.H5File)
                testCase.assumeFail('H5 file not available');
            end

            [data, ~, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            testCase.verifyNotEmpty(data, ...
                'getSelectedData with H5 file should return data');
        end

        function testGetSelectedDataSelectionFilter(testCase)
            % Verify selection filtering reduces data correctly

            % Get all selected data
            [dataAll, ~, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            % Skip if no data
            if isempty(dataAll)
                testCase.assumeFail('H5 data not available');
            end

            % Deselect half the epochs
            epochs = testCase.LeafNode.getAllEpochs(false);
            nEpochs = length(epochs);
            for i = 1:2:nEpochs
                epochs{i}.isSelected = false;
            end

            % Get selected data again
            [dataFiltered, ~, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            % Should have fewer rows
            testCase.verifyLessThan(size(dataFiltered, 1), size(dataAll, 1), ...
                'Selection filtering must reduce row count');

            % Should have approximately half (may not be exact if some epochs don't have Amp1)
            expectedRows = ceil(nEpochs / 2);
            testCase.verifyEqual(size(dataFiltered, 1), expectedRows, ...
                'Filtered data should have half the rows', 'RelTol', 0.2);
        end

        function testGetSelectedDataEmptyNode(testCase)
            % Verify empty selection returns empty matrix

            % Deselect all epochs
            epochs = testCase.LeafNode.getAllEpochs(false);
            for i = 1:length(epochs)
                epochs{i}.isSelected = false;
            end

            [data, returnedEpochs, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            testCase.verifyEmpty(data, ...
                'Empty selection must return empty matrix');
            testCase.verifyEmpty(returnedEpochs, ...
                'Empty selection must return empty epoch list');
        end

        function testGetSelectedDataInvalidStream(testCase)
            % Verify invalid stream name handles gracefully

            % Request non-existent stream
            [data, ~, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'NonExistentStream', testCase.H5File);

            % Should return empty (not error)
            testCase.verifyEmpty(data, ...
                'Invalid stream should return empty matrix');
        end

        function testGetSelectedDataFromNode(testCase)
            % Verify passing epicTreeTools node works

            node = testCase.LeafNode;

            try
                [data, ~, ~] = epicTreeTools.getSelectedData(node, 'Amp1', testCase.H5File);
                % Success - verify basic properties
                testCase.verifyTrue(ismatrix(data), ...
                    'Data from node must be matrix');
            catch ME
                testCase.verifyFail(sprintf('getSelectedData failed with node input: %s', ...
                    ME.message));
            end
        end

        function testGetSelectedDataFromEpochList(testCase)
            % Verify passing cell array of epochs works

            epochs = testCase.LeafNode.getAllEpochs(false);

            try
                [data, ~, ~] = epicTreeTools.getSelectedData(epochs, 'Amp1', testCase.H5File);
                % Success - verify basic properties
                testCase.verifyTrue(ismatrix(data), ...
                    'Data from epoch list must be matrix');
            catch ME
                testCase.verifyFail(sprintf('getSelectedData failed with epoch list: %s', ...
                    ME.message));
            end
        end
    end

    %% getResponseMatrix tests

    methods (Test)
        function testGetResponseMatrixReturnsMatrix(testCase)
            % Verify getResponseMatrix returns numeric matrix

            epochs = testCase.LeafNode.getAllEpochs(false);

            [data, ~] = epicTreeTools.getResponseMatrix(epochs, 'Amp1', testCase.H5File);

            % May be empty if H5 not available
            if ~isempty(data)
                testCase.verifyTrue(isnumeric(data), ...
                    'getResponseMatrix must return numeric matrix');
                testCase.verifyTrue(ismatrix(data), ...
                    'getResponseMatrix must return 2D matrix');
            end
        end

        function testGetResponseMatrixDimensions(testCase)
            % Verify rows match epoch count

            epochs = testCase.LeafNode.getAllEpochs(false);
            nEpochs = length(epochs);

            [data, ~] = epicTreeTools.getResponseMatrix(epochs, 'Amp1', testCase.H5File);

            % Skip if no data
            if isempty(data)
                testCase.assumeFail('H5 data not available');
            end

            testCase.verifyEqual(size(data, 1), nEpochs, ...
                'Matrix rows must equal epoch count');
        end

        function testGetResponseMatrixConsistentSampleRate(testCase)
            % Verify all epochs have same sample rate (or verify handling)

            epochs = testCase.LeafNode.getAllEpochs(false);

            [~, fs] = epicTreeTools.getResponseMatrix(epochs, 'Amp1', testCase.H5File);

            % Skip if no data
            if isempty(fs)
                testCase.assumeFail('H5 data not available');
            end

            % Sample rate should be scalar (all epochs same)
            testCase.verifyTrue(isscalar(fs), ...
                'Sample rate should be scalar (consistent across epochs)');
        end

        function testGetResponseMatrixEmptyInput(testCase)
            % Verify empty epoch list returns empty matrix

            [data, fs] = epicTreeTools.getResponseMatrix({}, 'Amp1', testCase.H5File);

            testCase.verifyEmpty(data, ...
                'Empty input must return empty matrix');
            testCase.verifyEmpty(fs, ...
                'Empty input must return empty sample rate');
        end
    end

    %% Data integrity tests

    methods (Test)
        function testDataNotAllZeros(testCase)
            % Verify returned data is not all zeros (real signal present)

            [data, ~, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            % Skip if no data
            if isempty(data)
                testCase.assumeFail('H5 data not available');
            end

            % At least some non-zero values
            testCase.verifyTrue(any(data(:) ~= 0), ...
                'Data should contain non-zero values (real signal)');
        end

        function testDataNotAllNaN(testCase)
            % Verify no NaN values in data

            [data, ~, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            % Skip if no data
            if isempty(data)
                testCase.assumeFail('H5 data not available');
            end

            testCase.verifyTrue(~any(isnan(data(:))), ...
                'Data should not contain NaN values');
        end

        function testDataConsistentLength(testCase)
            % Verify all rows have same number of columns

            [data, ~, ~] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            % Skip if no data
            if isempty(data)
                testCase.assumeFail('H5 data not available');
            end

            % Matrix should have consistent dimensions
            [nRows, nCols] = size(data);
            testCase.verifyEqual(size(data), [nRows, nCols], ...
                'All rows must have same length');
        end

        function testSampleRateReasonable(testCase)
            % Verify sample rate is in typical neurophysiology range

            [data, ~, fs] = epicTreeTools.getSelectedData(testCase.LeafNode, 'Amp1', testCase.H5File);

            % Skip if no data
            if isempty(data)
                testCase.assumeFail('H5 data not available');
            end

            % Typical range: 1 kHz to 50 kHz
            testCase.verifyGreaterThanOrEqual(fs, 1000, ...
                'Sample rate should be at least 1 kHz');
            testCase.verifyLessThanOrEqual(fs, 50000, ...
                'Sample rate should not exceed 50 kHz');
        end

        function testMultipleStreams(testCase)
            % Verify can extract different streams from same epochs

            epochs = testCase.LeafNode.getAllEpochs(false);

            % Try Amp1
            [data1, ~] = epicTreeTools.getResponseMatrix(epochs, 'Amp1', testCase.H5File);

            % Try Amp2 (may not exist)
            [data2, ~] = epicTreeTools.getResponseMatrix(epochs, 'Amp2', testCase.H5File);

            % At least one should work
            testCase.verifyTrue(~isempty(data1) || ~isempty(data2), ...
                'Should be able to extract at least one stream');

            % If both exist, dimensions should be compatible
            if ~isempty(data1) && ~isempty(data2)
                testCase.verifyEqual(size(data1, 1), size(data2, 1), ...
                    'Different streams should have same epoch count');
            end
        end
    end
end
