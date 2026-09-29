function generateBaselines()
% generateBaselines - Create golden output baselines for analysis functions
%
% This script generates reference output files for the 5 core analysis
% functions, used for regression testing. Baselines are saved as MAT files
% in tests/baselines/ directory.
%
% Usage:
%   generateBaselines()
%
% This function should be run:
%   - After implementing new analysis functions
%   - After intentionally changing analysis function behavior
%   - After updating test data
%
% DO NOT run this to "fix" failing tests unless you understand why the
% output changed and have verified the new output is correct.
%
% See also: tests/baselines/README.md

    fprintf('=== Generating Analysis Function Baselines ===\n\n');

    % Get paths
    repoRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    baselineDir = fullfile(repoRoot, 'tests', 'baselines');

    % Ensure baseline directory exists
    if ~exist(baselineDir, 'dir')
        mkdir(baselineDir);
        fprintf('Created baseline directory: %s\n\n', baselineDir);
    end

    % Load test data
    fprintf('Loading test data...\n');
    [tree, ~, h5File] = loadTestTree({'cellInfo.type', 'blockInfo.protocol_name'});

    % Get test nodes
    leaves = tree.leafNodes();
    if isempty(leaves)
        error('No leaf nodes in test tree - cannot generate baselines');
    end
    leafNode = leaves{1};

    firstChild = tree.childAt(1);
    multipleNodes = {};
    for i = 1:min(3, firstChild.childrenLength())
        multipleNodes{end+1} = firstChild.childAt(i);
    end

    fprintf('  Leaf node: %d epochs\n', leafNode.epochCount());
    fprintf('  Multiple nodes: %d nodes for comparison\n', length(multipleNodes));
    fprintf('Done.\n\n');

    %% Generate getMeanResponseTrace baseline

    fprintf('Generating getMeanResponseTrace baseline...\n');
    try
        baseline = epicTreeTools.getMeanResponseTrace(leafNode, 'Amp1');
        baselinePath = fullfile(baselineDir, 'getMeanResponseTrace_baseline.mat');
        save(baselinePath, 'baseline', '-v7.3');
        fprintf('  Saved: %s\n', baselinePath);
        fprintf('  Fields: %s\n', strjoin(fieldnames(baseline), ', '));
        fprintf('  Epochs: %d\n', baseline.n);
        if baseline.n > 0
            fprintf('  Sample rate: %.1f Hz\n', baseline.sampleRate);
            fprintf('  Trace length: %d samples\n', length(baseline.mean));
        end
    catch ME
        fprintf('  FAILED: %s\n', ME.message);
    end
    fprintf('Done.\n\n');

    %% Generate getResponseAmplitudeStats baseline

    fprintf('Generating getResponseAmplitudeStats baseline...\n');
    try
        baseline = epicTreeTools.getResponseAmplitudeStats(leafNode, 'Amp1');
        baselinePath = fullfile(baselineDir, 'getResponseAmplitudeStats_baseline.mat');
        save(baselinePath, 'baseline', '-v7.3');
        fprintf('  Saved: %s\n', baselinePath);
        fprintf('  Fields: %s\n', strjoin(fieldnames(baseline), ', '));
        fprintf('  Epochs: %d\n', baseline.n);
        if baseline.n > 0
            fprintf('  Mean peak: %.2f %s\n', baseline.mean_peak, baseline.units);
            fprintf('  Mean integrated: %.2f %s*s\n', baseline.mean_integrated, baseline.units);
        end
    catch ME
        fprintf('  FAILED: %s\n', ME.message);
    end
    fprintf('Done.\n\n');

    %% Generate getCycleAverageResponse baseline

    fprintf('Generating getCycleAverageResponse baseline...\n');
    try
        % Try with default frequency (may fail if data doesn't have it)
        baseline = epicTreeTools.getCycleAverageResponse(leafNode, 'Amp1', 'Frequency', 2);
        baselinePath = fullfile(baselineDir, 'getCycleAverageResponse_baseline.mat');
        save(baselinePath, 'baseline', '-v7.3');
        fprintf('  Saved: %s\n', baselinePath);
        fprintf('  Fields: %s\n', strjoin(fieldnames(baseline), ', '));
        fprintf('  Epochs: %d\n', baseline.n);
        if baseline.n > 0 && baseline.nCycles > 0
            fprintf('  Frequency: %.2f Hz\n', baseline.frequency);
            fprintf('  Cycles: %d\n', baseline.nCycles);
            fprintf('  F1 amplitude: %.2f\n', baseline.F1amplitude);
            fprintf('  F2 amplitude: %.2f\n', baseline.F2amplitude);
        end
    catch ME
        fprintf('  SKIPPED: %s\n', ME.message);
        fprintf('  (This is normal if test data has no periodic stimuli)\n');
    end
    fprintf('Done.\n\n');

    %% Generate getLinearFilterAndPrediction baseline

    fprintf('Generating getLinearFilterAndPrediction baseline...\n');
    try
        % Try with Stage stimulus (may fail if not available)
        baseline = epicTreeTools.getLinearFilterAndPrediction(leafNode, 'Stage', 'Amp1');
        baselinePath = fullfile(baselineDir, 'getLinearFilterAndPrediction_baseline.mat');
        save(baselinePath, 'baseline', '-v7.3');
        fprintf('  Saved: %s\n', baselinePath);
        fprintf('  Fields: %s\n', strjoin(fieldnames(baseline), ', '));
        fprintf('  Epochs: %d\n', baseline.n);
        if baseline.n > 0 && ~isempty(baseline.filter)
            fprintf('  Filter length: %d points\n', length(baseline.filter));
            fprintf('  Correlation: %.3f\n', baseline.correlation);
        end
    catch ME
        fprintf('  SKIPPED: %s\n', ME.message);
        fprintf('  (This is normal if test data has no stimulus streams)\n');
    end
    fprintf('Done.\n\n');

    %% Generate MeanSelectedNodes baseline

    fprintf('Generating MeanSelectedNodes baseline...\n');
    try
        % Create invisible figure to suppress display
        fig = figure('Visible', 'off');
        baseline = epicTreeTools.MeanSelectedNodes(multipleNodes, 'Amp1', 'Figure', fig);
        close(fig);

        baselinePath = fullfile(baselineDir, 'MeanSelectedNodes_baseline.mat');
        save(baselinePath, 'baseline', '-v7.3');
        fprintf('  Saved: %s\n', baselinePath);
        fprintf('  Fields: %s\n', strjoin(fieldnames(baseline), ', '));
        fprintf('  Nodes: %d\n', size(baseline.meanResponse, 1));
        if ~isempty(baseline.meanResponse)
            fprintf('  Total epochs: %d\n', sum(baseline.nEpochs));
            fprintf('  Trace length: %d samples\n', size(baseline.meanResponse, 2));
        end
    catch ME
        fprintf('  FAILED: %s\n', ME.message);
    end
    fprintf('Done.\n\n');

    %% Summary

    fprintf('=== Baseline Generation Complete ===\n\n');
    fprintf('Baseline files saved to: %s\n', baselineDir);
    fprintf('\n');
    fprintf('Next steps:\n');
    fprintf('  1. Review baseline files to ensure they look correct\n');
    fprintf('  2. Run tests: runtests(''tests/unit/AnalysisFunctionsTest'')\n');
    fprintf('  3. Commit baselines: git add tests/baselines/*.mat\n');
    fprintf('\n');
    fprintf('See tests/baselines/README.md for more information.\n');

end
