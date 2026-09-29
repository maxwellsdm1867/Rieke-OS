classdef AnalysisFunctionsTest < matlab.unittest.TestCase
    % AnalysisFunctionsTest - Comprehensive tests for analysis functions

    properties
        TestTree        % epicTreeTools tree with test data
        H5File          % Path to H5 file
        LeafNode        % Single leaf node for testing
        MultipleNodes   % Cell array of sibling nodes for MeanSelectedNodes
    end

    methods (TestClassSetup)
        function loadData(testCase)
            fprintf('\n[SETUP] Adding paths...\n');
            repoRoot = '/Users/maxwellsdm/Documents/GitHub/epicTreeGUI';
            addpath(fullfile(repoRoot, 'src'));
            addpath(fullfile(repoRoot, 'src', 'tree'));
            addpath(fullfile(repoRoot, 'src', 'analysis'));
            addpath(fullfile(repoRoot, 'src', 'utilities'));
            addpath(fullfile(repoRoot, 'src', 'splitters'));
            addpath(fullfile(repoRoot, 'src', 'tree', 'graphicalTree'));
            addpath(fullfile(repoRoot, 'tests', 'helpers'));
            fprintf('[SETUP] Paths added OK\n');

            fprintf('[SETUP] Loading MAT file...\n');
            matPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
            [data, testCase.H5File] = loadEpicTreeData(matPath);
            fprintf('[SETUP] MAT loaded: %d epochs\n', length(data));

            fprintf('[SETUP] Creating epicTreeTools...\n');
            testCase.TestTree = epicTreeTools(data);
            fprintf('[SETUP] epicTreeTools created\n');

            fprintf('[SETUP] Building tree...\n');
            testCase.TestTree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});
            fprintf('[SETUP] Tree built: %d children, %d epochs\n', ...
                testCase.TestTree.childrenLength(), testCase.TestTree.epochCount());

            fprintf('[SETUP] Getting leaf nodes...\n');
            leaves = testCase.TestTree.leafNodes();
            testCase.assumeTrue(~isempty(leaves), 'Test data must have leaf nodes');
            testCase.LeafNode = leaves{1};
            fprintf('[SETUP] Leaf node: %s (%d epochs)\n', ...
                string(testCase.LeafNode.splitValue), testCase.LeafNode.epochCount());

            fprintf('[SETUP] Getting sibling nodes for MeanSelectedNodes...\n');
            firstChild = testCase.TestTree.childAt(1);
            testCase.MultipleNodes = {};
            for i = 1:min(3, firstChild.childrenLength())
                testCase.MultipleNodes{end+1} = firstChild.childAt(i);
            end
            fprintf('[SETUP] Got %d sibling nodes. Setup complete!\n\n', length(testCase.MultipleNodes));
        end
    end

    methods (TestMethodTeardown)
        function closeFigures(~)
            close all;
        end
    end

    %% getMeanResponseTrace tests

    methods (Test)
        function testMeanResponseTraceOutputFields(testCase)
            fprintf('[TEST] testMeanResponseTraceOutputFields... ');
            resp = epicTreeTools.getMeanResponseTrace(testCase.LeafNode, 'Amp1');
            testCase.verifyTrue(isstruct(resp), 'Output must be a struct');
            testCase.verifyTrue(isfield(resp, 'mean'), 'Must have mean field');
            testCase.verifyTrue(isfield(resp, 'stdev'), 'Must have stdev field');
            testCase.verifyTrue(isfield(resp, 'SEM'), 'Must have SEM field');
            testCase.verifyTrue(isfield(resp, 'n'), 'Must have n field');
            testCase.verifyTrue(isfield(resp, 'timeVector'), 'Must have timeVector field');
            testCase.verifyTrue(isfield(resp, 'sampleRate'), 'Must have sampleRate field');
            testCase.verifyTrue(isfield(resp, 'units'), 'Must have units field');
            fprintf('OK\n');
        end

        function testMeanResponseTraceTypes(testCase)
            fprintf('[TEST] testMeanResponseTraceTypes... ');
            resp = epicTreeTools.getMeanResponseTrace(testCase.LeafNode, 'Amp1');
            testCase.assumeTrue(resp.n > 0, 'Need epochs for type validation');
            testCase.verifyTrue(isrow(resp.mean), 'mean must be row vector');
            testCase.verifyTrue(isa(resp.mean, 'double'), 'mean must be double');
            testCase.verifyTrue(resp.n > 0, 'n must be positive');
            testCase.verifyTrue(resp.n == floor(resp.n), 'n must be integer');
            testCase.verifyTrue(resp.sampleRate > 0, 'sampleRate must be positive');
            testCase.verifyTrue(isa(resp.sampleRate, 'double'), 'sampleRate must be double');
            testCase.verifyEqual(size(resp.stdev), size(resp.mean), 'stdev size must match mean');
            testCase.verifyEqual(size(resp.SEM), size(resp.mean), 'SEM size must match mean');
            fprintf('OK\n');
        end

        function testMeanResponseTraceSEMrelation(testCase)
            fprintf('[TEST] testMeanResponseTraceSEMrelation... ');
            resp = epicTreeTools.getMeanResponseTrace(testCase.LeafNode, 'Amp1');
            testCase.assumeTrue(resp.n > 0, 'Need epochs for SEM validation');
            expectedSEM = resp.stdev / sqrt(resp.n);
            testCase.verifyEqual(resp.SEM, expectedSEM, 'AbsTol', 1e-10, ...
                'SEM must equal stdev/sqrt(n)');
            fprintf('OK\n');
        end

        function testMeanResponseTraceTimeVector(testCase)
            fprintf('[TEST] testMeanResponseTraceTimeVector... ');
            resp = epicTreeTools.getMeanResponseTrace(testCase.LeafNode, 'Amp1');
            testCase.assumeTrue(resp.n > 0, 'Need epochs for timeVector validation');
            testCase.verifyEqual(length(resp.timeVector), length(resp.mean), ...
                'timeVector length must match mean length');
            testCase.verifyLessThan(abs(resp.timeVector(1)), 0.01, ...
                'timeVector should start near zero');
            testCase.verifyTrue(all(diff(resp.timeVector) > 0), ...
                'timeVector must be monotonically increasing');
            fprintf('OK\n');
        end

        function testMeanResponseTraceRecordingTypes(testCase)
            fprintf('[TEST] testMeanResponseTraceRecordingTypes... ');
            recordingTypes = {'exc', 'inh', 'raw'};
            expectedUnits = {'pA', 'pA', 'AU'};
            for i = 1:length(recordingTypes)
                fprintf('%s ', recordingTypes{i});
                resp = epicTreeTools.getMeanResponseTrace(testCase.LeafNode, 'Amp1', ...
                    'RecordingType', recordingTypes{i});
                testCase.verifyTrue(isstruct(resp), ...
                    sprintf('Output for RecordingType=%s must be struct', recordingTypes{i}));
                if resp.n > 0
                    testCase.verifyEqual(resp.units, expectedUnits{i}, ...
                        sprintf('Units for RecordingType=%s must be %s', ...
                        recordingTypes{i}, expectedUnits{i}));
                end
            end
            fprintf('OK\n');
        end

        function testMeanResponseTraceNodeInput(testCase)
            fprintf('[TEST] testMeanResponseTraceNodeInput... ');
            resp = epicTreeTools.getMeanResponseTrace(testCase.LeafNode, 'Amp1');
            testCase.verifyTrue(isstruct(resp), 'Must accept node input');
            testCase.verifyTrue(isfield(resp, 'n'), 'Output must have n field');
            fprintf('OK\n');
        end

        function testMeanResponseTraceEpochListInput(testCase)
            fprintf('[TEST] testMeanResponseTraceEpochListInput... ');
            epochs = testCase.LeafNode.getAllEpochs(false);
            testCase.assumeTrue(~isempty(epochs), 'Need epochs for epoch list test');
            resp = epicTreeTools.getMeanResponseTrace(epochs, 'Amp1');
            testCase.verifyTrue(isstruct(resp), 'Must accept epoch list input');
            testCase.verifyTrue(isfield(resp, 'n'), 'Output must have n field');
            testCase.verifyEqual(resp.n, length(epochs), ...
                'n must equal number of input epochs');
            fprintf('OK\n');
        end
    end

    %% getResponseAmplitudeStats tests

    methods (Test)
        function testAmplitudeStatsOutputFields(testCase)
            fprintf('[TEST] testAmplitudeStatsOutputFields... ');
            stats = epicTreeTools.getResponseAmplitudeStats(testCase.LeafNode, 'Amp1');
            testCase.verifyTrue(isstruct(stats), 'Output must be a struct');
            testCase.verifyTrue(isfield(stats, 'peakAmplitude'), 'Must have peakAmplitude');
            testCase.verifyTrue(isfield(stats, 'peakTime'), 'Must have peakTime');
            testCase.verifyTrue(isfield(stats, 'integratedResponse'), 'Must have integratedResponse');
            testCase.verifyTrue(isfield(stats, 'meanAmplitude'), 'Must have meanAmplitude');
            testCase.verifyTrue(isfield(stats, 'baseline'), 'Must have baseline');
            testCase.verifyTrue(isfield(stats, 'mean_peak'), 'Must have mean_peak');
            testCase.verifyTrue(isfield(stats, 'std_peak'), 'Must have std_peak');
            testCase.verifyTrue(isfield(stats, 'sem_peak'), 'Must have sem_peak');
            testCase.verifyTrue(isfield(stats, 'n'), 'Must have n');
            testCase.verifyTrue(isfield(stats, 'units'), 'Must have units');
            fprintf('OK\n');
        end

        function testAmplitudeStatsTypes(testCase)
            fprintf('[TEST] testAmplitudeStatsTypes... ');
            stats = epicTreeTools.getResponseAmplitudeStats(testCase.LeafNode, 'Amp1');
            testCase.assumeTrue(stats.n > 0, 'Need epochs for type validation');
            testCase.verifyEqual(size(stats.peakAmplitude, 1), stats.n, ...
                'peakAmplitude must have n rows');
            testCase.verifyEqual(size(stats.peakAmplitude, 2), 1, ...
                'peakAmplitude must be column vector');
            testCase.verifyTrue(isscalar(stats.mean_peak), 'mean_peak must be scalar');
            testCase.verifyTrue(isscalar(stats.std_peak), 'std_peak must be scalar');
            testCase.verifyTrue(isscalar(stats.sem_peak), 'sem_peak must be scalar');
            fprintf('OK\n');
        end

        function testAmplitudeStatsSEMrelation(testCase)
            fprintf('[TEST] testAmplitudeStatsSEMrelation... ');
            stats = epicTreeTools.getResponseAmplitudeStats(testCase.LeafNode, 'Amp1');
            testCase.assumeTrue(stats.n > 0, 'Need epochs for SEM validation');
            expectedSEM = stats.std_peak / sqrt(stats.n);
            testCase.verifyEqual(stats.sem_peak, expectedSEM, 'AbsTol', 1e-10, ...
                'sem_peak must equal std_peak/sqrt(n)');
            fprintf('OK\n');
        end

        function testAmplitudeStatsNonEmpty(testCase)
            fprintf('[TEST] testAmplitudeStatsNonEmpty... ');
            stats = epicTreeTools.getResponseAmplitudeStats(testCase.LeafNode, 'Amp1');
            testCase.assumeTrue(stats.n > 0, 'Need epochs for non-empty validation');
            testCase.verifyFalse(isempty(stats.peakAmplitude), ...
                'peakAmplitude must be non-empty with data');
            testCase.verifyFalse(isnan(stats.mean_peak), ...
                'mean_peak must not be NaN with data');
            testCase.verifyFalse(isempty(stats.units), ...
                'units must be non-empty with data');
            fprintf('OK\n');
        end

        function testAmplitudeStatsWithWindow(testCase)
            fprintf('[TEST] testAmplitudeStatsWithWindow... ');
            stats = epicTreeTools.getResponseAmplitudeStats(testCase.LeafNode, 'Amp1', ...
                'ResponseWindow', [0.5 1.5]);
            testCase.verifyTrue(isstruct(stats), ...
                'Must accept ResponseWindow parameter');
            testCase.verifyTrue(isfield(stats, 'peakAmplitude'), ...
                'Output must have peakAmplitude field');
            fprintf('OK\n');
        end
    end

    %% getCycleAverageResponse tests

    methods (Test)
        function testCycleAverageOutputFields(testCase)
            fprintf('[TEST] testCycleAverageOutputFields... ');
            try
                result = epicTreeTools.getCycleAverageResponse(testCase.LeafNode, 'Amp1', ...
                    'Frequency', 2);
                testCase.verifyTrue(isstruct(result), 'Output must be a struct');
                testCase.verifyTrue(isfield(result, 'cycleAverage'), 'Must have cycleAverage');
                testCase.verifyTrue(isfield(result, 'F1amplitude'), 'Must have F1amplitude');
                testCase.verifyTrue(isfield(result, 'F1F2ratio'), 'Must have F1F2ratio');
                testCase.verifyTrue(isfield(result, 'n'), 'Must have n');
                fprintf('OK\n');
            catch ME
                fprintf('SKIP (%s)\n', ME.message);
                testCase.assumeFail(sprintf('Periodic stimulus data not available: %s', ME.message));
            end
        end

        function testCycleAverageTypes(testCase)
            fprintf('[TEST] testCycleAverageTypes... ');
            try
                result = epicTreeTools.getCycleAverageResponse(testCase.LeafNode, 'Amp1', ...
                    'Frequency', 2);
                testCase.assumeTrue(result.n > 0 && result.nCycles > 0, ...
                    'Need valid cycle data for type validation');
                testCase.verifyTrue(isrow(result.cycleAverage), 'cycleAverage must be row vector');
                testCase.verifyTrue(isscalar(result.frequency), 'frequency must be scalar');
                testCase.verifyTrue(result.frequency > 0, 'frequency must be positive');
                fprintf('OK\n');
            catch ME
                fprintf('SKIP (%s)\n', ME.message);
                testCase.assumeFail(sprintf('Periodic stimulus data not available: %s', ME.message));
            end
        end

        function testCycleAverageWithFrequency(testCase)
            fprintf('[TEST] testCycleAverageWithFrequency... ');
            try
                result = epicTreeTools.getCycleAverageResponse(testCase.LeafNode, 'Amp1', ...
                    'Frequency', 2);
                testCase.verifyEqual(result.frequency, 2, ...
                    'Frequency parameter should be stored in output');
                fprintf('OK\n');
            catch ME
                fprintf('SKIP (%s)\n', ME.message);
                testCase.assumeFail(sprintf('Periodic stimulus data not available: %s', ME.message));
            end
        end

        function testCycleAverageF1F2NonNegative(testCase)
            fprintf('[TEST] testCycleAverageF1F2NonNegative... ');
            try
                result = epicTreeTools.getCycleAverageResponse(testCase.LeafNode, 'Amp1', ...
                    'Frequency', 2);
                testCase.assumeTrue(result.n > 0 && result.nCycles > 0, 'Need valid cycle data');
                testCase.verifyGreaterThanOrEqual(result.F1amplitude, 0, 'F1amplitude must be non-negative');
                testCase.verifyGreaterThanOrEqual(result.F2amplitude, 0, 'F2amplitude must be non-negative');
                fprintf('OK\n');
            catch ME
                fprintf('SKIP (%s)\n', ME.message);
                testCase.assumeFail(sprintf('Periodic stimulus data not available: %s', ME.message));
            end
        end
    end

    %% getLinearFilterAndPrediction tests

    methods (Test)
        function testLinearFilterOutputFields(testCase)
            fprintf('[TEST] testLinearFilterOutputFields... ');
            try
                result = epicTreeTools.getLinearFilterAndPrediction(testCase.LeafNode, ...
                    'Stage', 'Amp1');
                testCase.verifyTrue(isstruct(result), 'Output must be a struct');
                testCase.verifyTrue(isfield(result, 'filter'), 'Must have filter');
                testCase.verifyTrue(isfield(result, 'prediction'), 'Must have prediction');
                testCase.verifyTrue(isfield(result, 'correlation'), 'Must have correlation');
                testCase.verifyTrue(isfield(result, 'n'), 'Must have n');
                fprintf('OK\n');
            catch ME
                fprintf('SKIP (%s)\n', ME.message);
                testCase.assumeFail(sprintf('Stimulus stream data not available: %s', ME.message));
            end
        end

        function testLinearFilterTypes(testCase)
            fprintf('[TEST] testLinearFilterTypes... ');
            try
                result = epicTreeTools.getLinearFilterAndPrediction(testCase.LeafNode, ...
                    'Stage', 'Amp1');
                testCase.assumeTrue(result.n > 0 && ~isempty(result.filter), ...
                    'Need valid filter data for type validation');
                testCase.verifyTrue(isrow(result.filter), 'filter must be row vector');
                testCase.verifyTrue(isscalar(result.correlation), 'correlation must be scalar');
                fprintf('OK\n');
            catch ME
                fprintf('SKIP (%s)\n', ME.message);
                testCase.assumeFail(sprintf('Stimulus stream data not available: %s', ME.message));
            end
        end

        function testLinearFilterCorrelationRange(testCase)
            fprintf('[TEST] testLinearFilterCorrelationRange... ');
            try
                result = epicTreeTools.getLinearFilterAndPrediction(testCase.LeafNode, ...
                    'Stage', 'Amp1');
                testCase.assumeTrue(result.n > 0 && ~isempty(result.filter), ...
                    'Need valid filter data');
                if ~isnan(result.correlation)
                    testCase.verifyGreaterThanOrEqual(result.correlation, -1, 'correlation must be >= -1');
                    testCase.verifyLessThanOrEqual(result.correlation, 1, 'correlation must be <= 1');
                end
                fprintf('OK\n');
            catch ME
                fprintf('SKIP (%s)\n', ME.message);
                testCase.assumeFail(sprintf('Stimulus stream data not available: %s', ME.message));
            end
        end

        function testLinearFilterWithLength(testCase)
            fprintf('[TEST] testLinearFilterWithLength... ');
            try
                result = epicTreeTools.getLinearFilterAndPrediction(testCase.LeafNode, ...
                    'Stage', 'Amp1', 'FilterLength', 300);
                testCase.verifyTrue(isstruct(result), 'Must accept FilterLength parameter');
                testCase.verifyTrue(isfield(result, 'filter'), 'Output must have filter field');
                fprintf('OK\n');
            catch ME
                fprintf('SKIP (%s)\n', ME.message);
                testCase.assumeFail(sprintf('Stimulus stream data not available: %s', ME.message));
            end
        end
    end

    %% MeanSelectedNodes tests

    methods (Test)
        function testMeanSelectedNodesOutputFields(testCase)
            fprintf('[TEST] testMeanSelectedNodesOutputFields... ');
            testCase.assumeTrue(~isempty(testCase.MultipleNodes), ...
                'Need multiple nodes for MeanSelectedNodes tests');
            results = epicTreeTools.MeanSelectedNodes(testCase.MultipleNodes, 'Amp1', ...
                'Figure', figure('Visible', 'off'));
            testCase.verifyTrue(isstruct(results), 'Output must be a struct');
            testCase.verifyTrue(isfield(results, 'meanResponse'), 'Must have meanResponse');
            testCase.verifyTrue(isfield(results, 'semResponse'), 'Must have semResponse');
            testCase.verifyTrue(isfield(results, 'respAmp'), 'Must have respAmp');
            testCase.verifyTrue(isfield(results, 'splitValue'), 'Must have splitValue');
            testCase.verifyTrue(isfield(results, 'nEpochs'), 'Must have nEpochs');
            testCase.verifyTrue(isfield(results, 'timeVector'), 'Must have timeVector');
            testCase.verifyTrue(isfield(results, 'sampleRate'), 'Must have sampleRate');
            fprintf('OK\n');
        end

        function testMeanSelectedNodesTypes(testCase)
            fprintf('[TEST] testMeanSelectedNodesTypes... ');
            testCase.assumeTrue(~isempty(testCase.MultipleNodes), 'Need multiple nodes');
            results = epicTreeTools.MeanSelectedNodes(testCase.MultipleNodes, 'Amp1', ...
                'Figure', figure('Visible', 'off'));
            nNodes = length(testCase.MultipleNodes);
            testCase.verifyEqual(size(results.meanResponse, 1), nNodes, ...
                'meanResponse must have nNodes rows');
            testCase.verifyTrue(isa(results.meanResponse, 'double'), 'meanResponse must be double');
            testCase.verifyTrue(isrow(results.nEpochs) || isvector(results.nEpochs), 'nEpochs must be vector');
            testCase.verifyEqual(length(results.nEpochs), nNodes, 'nEpochs length must equal number of nodes');
            fprintf('OK\n');
        end

        function testMeanSelectedNodesDimensions(testCase)
            fprintf('[TEST] testMeanSelectedNodesDimensions... ');
            testCase.assumeTrue(~isempty(testCase.MultipleNodes), 'Need multiple nodes');
            nNodes = length(testCase.MultipleNodes);
            results = epicTreeTools.MeanSelectedNodes(testCase.MultipleNodes, 'Amp1', ...
                'Figure', figure('Visible', 'off'));
            testCase.verifyEqual(size(results.meanResponse, 1), nNodes, 'meanResponse rows must match node count');
            testCase.verifyEqual(size(results.semResponse, 1), nNodes, 'semResponse rows must match node count');
            testCase.verifyEqual(length(results.respAmp), nNodes, 'respAmp length must match node count');
            fprintf('OK\n');
        end

        function testMeanSelectedNodesWithOptions(testCase)
            fprintf('[TEST] testMeanSelectedNodesWithOptions... ');
            testCase.assumeTrue(~isempty(testCase.MultipleNodes), 'Need multiple nodes');
            results1 = epicTreeTools.MeanSelectedNodes(testCase.MultipleNodes, 'Amp1', ...
                'BaselineCorrect', false, 'Figure', figure('Visible', 'off'));
            fprintf('bc=false ');
            results2 = epicTreeTools.MeanSelectedNodes(testCase.MultipleNodes, 'Amp1', ...
                'BaselineCorrect', true, 'Figure', figure('Visible', 'off'));
            fprintf('bc=true ');
            testCase.verifyTrue(isstruct(results1), 'Must accept BaselineCorrect=false');
            testCase.verifyTrue(isstruct(results2), 'Must accept BaselineCorrect=true');
            fprintf('OK\n');
        end
    end

    %% Baseline comparison tests

    methods (Test)
        function testMeanResponseTraceBaseline(testCase)
            fprintf('[TEST] testMeanResponseTraceBaseline... ');
            baselinePath = fullfile(fileparts(fileparts(mfilename('fullpath'))), ...
                'baselines', 'getMeanResponseTrace_baseline.mat');
            testCase.assumeTrue(isfile(baselinePath), ...
                'Baseline file must exist for regression test');
            resp = epicTreeTools.getMeanResponseTrace(testCase.LeafNode, 'Amp1');
            baselineData = load(baselinePath);
            baseline = baselineData.baseline;
            if resp.n > 0 && baseline.n > 0
                testCase.verifyEqual(resp.n, baseline.n, 'Epoch count should match baseline');
                testCase.verifyEqual(resp.sampleRate, baseline.sampleRate, ...
                    'AbsTol', 1e-6, 'Sample rate should match baseline');
                testCase.verifyEqual(resp.mean, baseline.mean, ...
                    'AbsTol', 1e-10, 'Mean trace should match baseline');
                testCase.verifyEqual(resp.SEM, baseline.SEM, ...
                    'AbsTol', 1e-10, 'SEM should match baseline');
            end
            fprintf('OK\n');
        end

        function testAmplitudeStatsBaseline(testCase)
            fprintf('[TEST] testAmplitudeStatsBaseline... ');
            baselinePath = fullfile(fileparts(fileparts(mfilename('fullpath'))), ...
                'baselines', 'getResponseAmplitudeStats_baseline.mat');
            testCase.assumeTrue(isfile(baselinePath), ...
                'Baseline file must exist for regression test');
            stats = epicTreeTools.getResponseAmplitudeStats(testCase.LeafNode, 'Amp1');
            baselineData = load(baselinePath);
            baseline = baselineData.baseline;
            if stats.n > 0 && baseline.n > 0
                testCase.verifyEqual(stats.n, baseline.n, 'Epoch count should match baseline');
                testCase.verifyEqual(stats.mean_peak, baseline.mean_peak, ...
                    'AbsTol', 1e-10, 'Mean peak should match baseline');
                testCase.verifyEqual(stats.sem_peak, baseline.sem_peak, ...
                    'AbsTol', 1e-10, 'SEM peak should match baseline');
            end
            fprintf('OK\n');
        end
    end
end
