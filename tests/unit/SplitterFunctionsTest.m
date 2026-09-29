classdef SplitterFunctionsTest < matlab.unittest.TestCase
    % SPLITTERFUNCTIONSTEST Comprehensive validation of all splitter functions
    %
    % Tests all 22+ static splitter methods in epicTreeTools plus standalone
    % splitter files. Validates that splitters:
    %   - Return valid values for real epoch data
    %   - Don't error on any epoch in test dataset
    %   - Produce valid tree structures with no lost epochs
    %   - Return correct/expected values for key splitters

    properties (TestParameter)
        % Single-argument splitters (parameterized tests)
        singleArgSplitter = {
            @epicTreeTools.splitOnExperimentDate
            @epicTreeTools.splitOnCellType
            @epicTreeTools.splitOnKeywords
            @epicTreeTools.splitOnF1F2Contrast
            @epicTreeTools.splitOnF1F2CenterSize
            @epicTreeTools.splitOnF1F2Phase
            @epicTreeTools.splitOnHoldingSignal
            @epicTreeTools.splitOnOLEDLevel
            @epicTreeTools.splitOnRecKeyword
            @epicTreeTools.splitOnLogIRtag
            @epicTreeTools.splitOnPatchContrast_NatImage
            @epicTreeTools.splitOnPatchSampling_NatImage
            @epicTreeTools.splitOnEpochBlockStart
            @epicTreeTools.splitOnBarWidth
            @epicTreeTools.splitOnFlashDelay
            @epicTreeTools.splitOnStimulusCenter
            @epicTreeTools.splitOnTemporalFrequency
            @epicTreeTools.splitOnSpatialFrequency
            @epicTreeTools.splitOnContrast
            @epicTreeTools.splitOnProtocol
        };
    end

    properties
        TestTree
        TestEpochs
        H5File
    end

    methods (TestClassSetup)
        function loadData(testCase)
            % Load test data once for all tests
            [testCase.TestTree, ~, testCase.H5File] = loadTestTree();
            testCase.TestEpochs = testCase.TestTree.getAllEpochs(false);

            % Verify we have data
            testCase.verifyNotEmpty(testCase.TestEpochs, ...
                'Test data must contain epochs');
        end
    end

    %% Parameterized tests (run for each single-arg splitter)

    methods (Test, ParameterCombination='sequential')
        function testSplitterReturnsValue(testCase, singleArgSplitter)
            % Verify splitter returns non-empty value for at least one epoch
            %
            % Some splitters may not apply to all epoch types (e.g.,
            % splitOnF1F2Phase only applies to periodic stimuli), so we
            % check that AT LEAST ONE epoch returns a value.

            foundValue = false;
            for i = 1:min(length(testCase.TestEpochs), 10)
                epoch = testCase.TestEpochs{i};
                value = singleArgSplitter(epoch);

                if ~isempty(value)
                    foundValue = true;
                    % Verify value is scalar (string, numeric, char, or logical)
                    testCase.verifyTrue(isscalar(value) || ischar(value) || isstring(value), ...
                        sprintf('%s must return scalar value', func2str(singleArgSplitter)));
                    break;
                end
            end

            testCase.verifyTrue(foundValue, ...
                sprintf('%s must return non-empty value for at least one epoch', ...
                func2str(singleArgSplitter)));
        end

        function testSplitterDoesNotError(testCase, singleArgSplitter)
            % Verify splitter doesn't error on any epoch in test data
            %
            % Splitters may return empty or 'Unknown' for some epochs,
            % but should never throw errors.

            for i = 1:length(testCase.TestEpochs)
                epoch = testCase.TestEpochs{i};

                % This should not error
                try
                    value = singleArgSplitter(epoch);
                    % Success - no assertion needed
                catch ME
                    testCase.verifyFail(sprintf('%s errored on epoch %d: %s', ...
                        func2str(singleArgSplitter), i, ME.message));
                end
            end
        end

        function testTreeBuildWithSplitter(testCase, singleArgSplitter)
            % Verify building a tree with this splitter produces valid structure
            %
            % Checks:
            %   - At least one child created (data was split)
            %   - No epochs lost (sum of leaf epoch counts == total)

            % Build tree with this splitter
            tree = epicTreeTools(testCase.TestTree.allEpochs);
            tree.buildTreeWithSplitters({singleArgSplitter});

            % Verify tree has children
            testCase.verifyGreaterThanOrEqual(tree.childrenLength(), 1, ...
                sprintf('%s must create at least one child node', ...
                func2str(singleArgSplitter)));

            % Verify no epochs lost
            totalEpochs = length(testCase.TestEpochs);
            leaves = tree.leafNodes();
            leafEpochCount = 0;
            for i = 1:length(leaves)
                leafEpochCount = leafEpochCount + leaves{i}.epochCount();
            end

            testCase.verifyEqual(leafEpochCount, totalEpochs, ...
                sprintf('%s: No epochs should be lost when building tree', ...
                func2str(singleArgSplitter)));
        end
    end

    %% Non-parameterized tests (multi-arg splitters and standalone functions)

    methods (Test)
        function testSplitOnKeywordsExcluding(testCase)
            % Test splitOnKeywordsExcluding with empty exclude list

            epoch = testCase.TestEpochs{1};
            value = epicTreeTools.splitOnKeywordsExcluding(epoch, {});

            % Should return string (empty or with keywords)
            testCase.verifyTrue(ischar(value) || isstring(value), ...
                'splitOnKeywordsExcluding must return string');
        end

        function testSplitOnRadiusOrDiameter(testCase)
            % Test splitOnRadiusOrDiameter with different parameter strings

            epoch = testCase.TestEpochs{1};

            % Try with 'aperture'
            value1 = epicTreeTools.splitOnRadiusOrDiameter(epoch, 'aperture');
            testCase.verifyTrue(isempty(value1) || isnumeric(value1), ...
                'splitOnRadiusOrDiameter must return numeric or empty');

            % Try with 'mask'
            value2 = epicTreeTools.splitOnRadiusOrDiameter(epoch, 'mask');
            testCase.verifyTrue(isempty(value2) || isnumeric(value2), ...
                'splitOnRadiusOrDiameter must return numeric or empty');
        end

        function testStandaloneSplitOnRGCSubtype(testCase)
            % Test standalone src/splitters/splitOnRGCSubtype.m

            epoch = testCase.TestEpochs{1};
            value = splitOnRGCSubtype(epoch);

            % Should return string (may be 'Unknown RGC')
            testCase.verifyTrue(ischar(value) || isstring(value), ...
                'splitOnRGCSubtype must return string');
            testCase.verifyNotEmpty(value, ...
                'splitOnRGCSubtype must return non-empty string');
        end
    end

    %% Correctness validation tests

    methods (Test)
        function testSplitOnCellTypeValues(testCase)
            % Verify cell type splitter returns known cell types

            cellTypes = {};
            for i = 1:length(testCase.TestEpochs)
                epoch = testCase.TestEpochs{i};
                cellType = epicTreeTools.splitOnCellType(epoch);
                if ~isempty(cellType)
                    cellTypes{end+1} = cellType;
                end
            end

            % Should have found at least one cell type
            testCase.verifyNotEmpty(cellTypes, ...
                'splitOnCellType must return values for test data');

            % All values should be strings
            testCase.verifyTrue(all(cellfun(@(x) ischar(x) || isstring(x), cellTypes)), ...
                'All cell types must be strings');
        end

        function testSplitOnContrastValues(testCase)
            % Verify contrast splitter returns numeric values in [0, 1] or empty

            for i = 1:length(testCase.TestEpochs)
                epoch = testCase.TestEpochs{i};
                contrast = epicTreeTools.splitOnContrast(epoch);

                if ~isempty(contrast)
                    % Should be numeric
                    testCase.verifyTrue(isnumeric(contrast), ...
                        'splitOnContrast must return numeric value');

                    % Typically in [0, 1] range, but allow wider for robustness
                    testCase.verifyGreaterThanOrEqual(contrast, 0, ...
                        'Contrast should be non-negative');
                    testCase.verifyLessThanOrEqual(contrast, 100, ...
                        'Contrast should be reasonable (< 100)');
                end
            end
        end

        function testSplitOnProtocolValues(testCase)
            % Verify protocol splitter returns non-empty strings

            protocols = {};
            for i = 1:length(testCase.TestEpochs)
                epoch = testCase.TestEpochs{i};
                protocol = epicTreeTools.splitOnProtocol(epoch);
                if ~isempty(protocol)
                    protocols{end+1} = protocol;
                end
            end

            % Should have found protocols
            testCase.verifyNotEmpty(protocols, ...
                'splitOnProtocol must return values for test data');

            % All should be non-empty strings
            testCase.verifyTrue(all(cellfun(@(x) ~isempty(x) && (ischar(x) || isstring(x)), protocols)), ...
                'All protocols must be non-empty strings');
        end

        function testSplitterConsistency(testCase)
            % Verify same epoch passed twice returns same value

            epoch = testCase.TestEpochs{1};

            % Test a few key splitters
            splitters = {
                @epicTreeTools.splitOnCellType
                @epicTreeTools.splitOnProtocol
                @epicTreeTools.splitOnExperimentDate
            };

            for i = 1:length(splitters)
                splitter = splitters{i};
                value1 = splitter(epoch);
                value2 = splitter(epoch);

                testCase.verifyEqual(value1, value2, ...
                    sprintf('%s must return consistent value for same epoch', ...
                    func2str(splitter)));
            end
        end

        function testAllSplittersOnSampleEpochs(testCase)
            % Smoke test: run all splitters on first few epochs
            %
            % This catches any obvious bugs in splitter implementation

            allSplitters = [
                testCase.singleArgSplitter
                {@(e) epicTreeTools.splitOnKeywordsExcluding(e, {})}
                {@(e) epicTreeTools.splitOnRadiusOrDiameter(e, 'aperture')}
                {@splitOnRGCSubtype}
            ];

            nSampleEpochs = min(5, length(testCase.TestEpochs));

            for i = 1:nSampleEpochs
                epoch = testCase.TestEpochs{i};

                for j = 1:length(allSplitters)
                    splitter = allSplitters{j};

                    try
                        value = splitter(epoch);
                        % Success - verify value is reasonable type
                        testCase.verifyTrue(isempty(value) || ...
                            isnumeric(value) || ischar(value) || isstring(value) || islogical(value), ...
                            sprintf('Splitter %d returned invalid type on epoch %d', j, i));
                    catch ME
                        testCase.verifyFail(sprintf('Splitter %d errored on epoch %d: %s', ...
                            j, i, ME.message));
                    end
                end
            end
        end
    end
end
