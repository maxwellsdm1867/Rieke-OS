% Test epicAnalysis class with real data
% Tests: detectSpikes, baselineCorrect, differenceOfGaussians, singleGaussian,
%        halfMaxSize, defaultParams, RFAnalysis

close all; clear; clc;

fprintf('=== Test epicAnalysis ===\n\n');

% Setup paths
baseDir = fileparts(mfilename('fullpath'));
projectDir = fileparts(baseDir);
addpath(fullfile(projectDir, 'src'));
addpath(fullfile(projectDir, 'src', 'tree'));
addpath(fullfile(projectDir, 'src', 'analysis'));

h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';
epicTreeConfig('h5_dir', h5Dir);

passed = 0;
failed = 0;

% --- Test 1: defaultParams returns valid struct ---
fprintf('Test 1: defaultParams ... ');
try
    params = epicAnalysis.defaultParams();
    assert(isstruct(params), 'Should return struct');
    assert(strcmp(params.Amp, 'Amp1'), 'Default Amp should be Amp1');
    assert(params.DOGfit == true, 'Default DOGfit should be true');
    assert(params.DecimatePts == 10, 'Default DecimatePts should be 10');
    fprintf('PASS\n'); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Test 2: baselineCorrect ---
fprintf('Test 2: baselineCorrect ... ');
try
    data = [10 10 10 20 30; 5 5 5 15 25];
    corrected = epicAnalysis.baselineCorrect(data, 1, 3);
    assert(all(abs(corrected(:,1:3)) < 1e-10, 'all'), 'Baseline region should be ~0');
    assert(abs(corrected(1,4) - 10) < 1e-10, 'Row 1 col 4 should be 10');
    assert(abs(corrected(2,5) - 20) < 1e-10, 'Row 2 col 5 should be 20');
    fprintf('PASS\n'); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Test 3: differenceOfGaussians ---
fprintf('Test 3: differenceOfGaussians ... ');
try
    x = [0 100 200 300 400 500];
    beta = [5 200 3.5 300];
    fit = epicAnalysis.differenceOfGaussians(beta, x);
    assert(length(fit) == length(x), 'Output length mismatch');
    assert(abs(fit(1)) < 1e-10, 'DOG at x=0 should be ~0');
    assert(fit(3) > 0, 'DOG should be positive at moderate x');
    fprintf('PASS\n'); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Test 4: singleGaussian ---
fprintf('Test 4: singleGaussian ... ');
try
    x = [0 100 200 300 400 500];
    beta = [5 200];
    fit = epicAnalysis.singleGaussian(beta, x);
    assert(length(fit) == length(x), 'Output length mismatch');
    assert(abs(fit(1)) < 1e-10, 'Gaussian at x=0 should be ~0');
    assert(all(diff(fit) >= 0), 'Single Gaussian should be monotonically increasing');
    fprintf('PASS\n'); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Test 5: halfMaxSize ---
fprintf('Test 5: halfMaxSize ... ');
try
    xVals = [40 80 120 160 200 240 280 320];
    yVals = [0.1 0.3 0.6 0.9 1.0 0.95 0.8 0.7];
    cs = epicAnalysis.halfMaxSize(xVals, yVals);
    assert(cs > 80 && cs < 120, sprintf('Expected center size between 80-120, got %.1f', cs));

    % Edge case: first point already above half-max
    cs2 = epicAnalysis.halfMaxSize([10 20 30], [1.0 0.9 0.8]);
    assert(cs2 == 10, 'Should return first x when first y > halfmax');
    fprintf('PASS\n'); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Test 6: detectSpikes with synthetic data ---
fprintf('Test 6: detectSpikes (synthetic) ... ');
try
    % Create trace with known spikes
    t = 1:10000;
    trace = randn(1, 10000) * 0.5;
    spikePositions = [1000, 3000, 5000, 7000, 9000];
    for sp = spikePositions
        trace(sp) = 20;
    end
    [times, amps] = epicAnalysis.detectSpikes(trace, 'MinPeakHeight', 10);
    assert(length(times) == 5, sprintf('Expected 5 spikes, got %d', length(times)));
    assert(all(amps > 10), 'All spike amplitudes should exceed threshold');
    fprintf('PASS\n'); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Test 7: detectSpikes with auto-threshold ---
fprintf('Test 7: detectSpikes (auto threshold) ... ');
try
    trace = randn(1, 10000) * 0.5;
    trace(2000) = 15;
    trace(6000) = 15;
    [times, ~] = epicAnalysis.detectSpikes(trace);
    assert(length(times) >= 2, sprintf('Expected >= 2 spikes, got %d', length(times)));
    fprintf('PASS\n'); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Test 8: baselineCorrect on real data ---
fprintf('Test 8: baselineCorrect on real data ... ');
try
    dataFile = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
    [data, ~] = loadEpicTreeData(dataFile);
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnProtocol});
    ssNode = tree.childBySplitValue('SingleSpot');
    assert(~isempty(ssNode), 'Should find SingleSpot protocol');
    [respData, ~, ~] = epicTreeTools.getSelectedData(ssNode, 'Amp1');
    assert(~isempty(respData), 'Should get response data');
    corrected = epicAnalysis.baselineCorrect(respData, 1, 2000);
    % Baseline region should be near zero
    baselineMeans = mean(corrected(:, 1:2000), 2);
    assert(all(abs(baselineMeans) < 1e-8), 'Baseline means should be ~0 after correction');
    fprintf('PASS\n'); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Test 9: RFAnalysis on ExpandingSpots ---
fprintf('Test 9: RFAnalysis on ExpandingSpots ... ');
try
    dataFile = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
    [data, ~] = loadEpicTreeData(dataFile);
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol, 'parameters.currentSpotSize'});

    esNode = [];
    for i = 1:tree.childrenLength()
        cellNode = tree.childAt(i);
        candidate = cellNode.childBySplitValue('ExpandingSpots');
        if ~isempty(candidate)
            esNode = candidate;
            break;
        end
    end
    assert(~isempty(esNode), 'Should find ExpandingSpots node');

    params = epicAnalysis.defaultParams();
    params.figureNum = 99;
    params.DOGfit = false;

    results = epicAnalysis.RFAnalysis(esNode, params);

    % Core fields
    assert(isfield(results, 'respAmp'), 'Should have respAmp');
    assert(isfield(results, 'meanResponse'), 'Should have meanResponse');
    assert(isfield(results, 'tme'), 'Should have tme');
    assert(isfield(results, 'splitValue'), 'Should have splitValue');
    assert(isfield(results, 'CenterSize'), 'Should have CenterSize');
    assert(length(results.respAmp) == length(esNode.leafNodes()), ...
        sprintf('respAmp length %d != leaf count %d', length(results.respAmp), length(esNode.leafNodes())));
    assert(all(results.respAmp >= 0), 'respAmp values should be non-negative');
    assert(results.CenterSize > 0, 'CenterSize should be positive');

    % Per-epoch statistics fields
    assert(isfield(results, 'respAmpStd'), 'Should have respAmpStd');
    assert(isfield(results, 'respAmpSem'), 'Should have respAmpSem');
    assert(isfield(results, 'numEpochs'), 'Should have numEpochs');
    assert(isfield(results, 'stdResponse'), 'Should have stdResponse');
    assert(isfield(results, 'semResponse'), 'Should have semResponse');
    assert(all(results.respAmpSem >= 0), 'SEM should be non-negative');
    assert(all(results.numEpochs > 0), 'Should have epochs at each condition');

    fprintf('PASS (CenterSize=%.1f, %d conditions, n=%s)\n', ...
        results.CenterSize, length(results.respAmp), mat2str(results.numEpochs));
    passed = passed + 1;
    close(99);
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
    if ishandle(99), close(99); end
end

% --- Test 10: DOG fit with nlinfit ---
fprintf('Test 10: DOG fitting with nlinfit ... ');
try
    % Synthetic area-summation curve: DOG shape
    x = [40 80 120 160 200 240 280 320 460 600 720];
    beta_true = [8 150 4 400];
    y_true = epicAnalysis.differenceOfGaussians(beta_true, x);
    y_noisy = y_true + randn(size(y_true)) * 0.05;

    coef0 = [5 200 3.5 300];
    fitcoef = nlinfit(x, y_noisy, @epicAnalysis.differenceOfGaussians, coef0);
    y_fit = epicAnalysis.differenceOfGaussians(fitcoef, x);
    residual = sqrt(mean((y_fit - y_noisy).^2));
    assert(residual < 0.5, sprintf('DOG fit residual too large: %.4f', residual));
    fprintf('PASS (RMSE=%.4f)\n', residual); passed = passed + 1;
catch ME
    fprintf('FAIL: %s\n', ME.message); failed = failed + 1;
end

% --- Summary ---
fprintf('\n=== Results: %d passed, %d failed out of %d ===\n', passed, failed, passed + failed);
if failed > 0
    error('epicAnalysis: %d test(s) failed', failed);
end
