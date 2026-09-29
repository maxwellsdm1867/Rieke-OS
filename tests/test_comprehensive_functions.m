%% Comprehensive functional and performance test suite for epicTreeGUI
%
% 15 tests covering the full scientific workflow:
%   1.  Data loading performance
%   2.  Tree construction with 6 different splitter combos + timing
%   3.  Epoch count consistency (root = sum of leaves) across all combos
%   4.  Metadata completeness: every epoch has required fields
%   5.  Date/time: .NET tick conversion, epoch-within-block ordering
%   6.  Selection management: bulk select/deselect + parent propagation
%   7.  H5 data extraction from all leaves + per-epoch timing
%   8.  Scientific analysis: mean, std, peak, SNR + putCustom round-trip
%   9.  Tree rebuild preserves data integrity (bit-exact after 3 rebuilds)
%  10.  Navigation: parent-child links, childBySplitValue, depth checks
%  11.  getSelectedData respects isSelected flag
%  12.  Split on every universal metadata key path
%  13.  Multi-level split + full extraction end-to-end pipeline timing
%  14.  Waveform quality: no NaN/Inf, reasonable amplitudes, duration match
%  15.  Rapid rebuild benchmark (20 rebuilds)
%
% Protocol-specific parameters (preTime, spotIntensity, etc.) are only
% tested on nodes that have them, since not all protocols share the same
% parameter set (e.g., VariableMeanNoise has no preTime/tailTime).
%
% No GUI or user interaction needed.

close all; clear; clc;

fprintf('============================================================\n');
fprintf('  COMPREHENSIVE EPICTREETOOL TEST SUITE\n');
fprintf('  %s\n', datetime('now'));
fprintf('============================================================\n\n');

% Setup
baseDir = fileparts(mfilename('fullpath'));
projectDir = fileparts(baseDir);
addpath(fullfile(projectDir, 'src'));
addpath(fullfile(projectDir, 'src', 'tree'));

h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';
epicTreeConfig('h5_dir', h5Dir);
dataFile = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

nPass = 0;
nFail = 0;
nTests = 0;
timings = struct();

% =====================================================================
%  TEST 1: Data Loading Performance
% =====================================================================
fprintf('\n--- Test 1: Data loading performance ---\n');
nTests = nTests + 1;
try
    tic;
    [data, ~] = loadEpicTreeData(dataFile);
    timings.data_load = toc;
    % loadEpicTreeData returns the raw hierarchy; epicTreeTools flattens it
    % Verify by building a quick tree and checking epoch count
    tmpTree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tmpTree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});
    nEpochs = tmpTree.epochCount();
    assert(nEpochs == 1915, sprintf('Expected 1915 epochs, got %d', nEpochs));
    fprintf('  Loaded and flattened to %d epochs in %.3f s (%.1f epochs/s)\n', nEpochs, timings.data_load, nEpochs/timings.data_load);
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 2: Tree construction with different splitter combos + timing
% =====================================================================
fprintf('\n--- Test 2: Tree construction performance ---\n');
nTests = nTests + 1;
try
    splitterSets = {
        {{@epicTreeTools.splitOnCellType}, '1-level: CellType'};
        {{@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol}, '2-level: CellType > Protocol'};
        {{@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol, 'parameters.preTime'}, '3-level: CellType > Protocol > preTime'};
        {{'cellInfo.label', 'parameters.stimTime'}, '2-level: CellLabel > stimTime'};
        {{'blockInfo.protocol_name', 'parameters.spotIntensity'}, '2-level: Protocol > spotIntensity'};
        {{'cellInfo.label', 'blockInfo.protocol_name', 'parameters.numberOfAverages'}, '3-level: CellLabel > Protocol > nAvg'};
    };

    buildTimes = zeros(length(splitterSets), 1);
    for s = 1:length(splitterSets)
        tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
        tic;
        tree.buildTreeWithSplitters(splitterSets{s}{1});
        buildTimes(s) = toc;
        assert(tree.epochCount() == 1915, sprintf('Set %d: epoch count mismatch', s));
        leaves = tree.leafNodes();
        fprintf('  %-45s  %.3f s  (%d leaves)\n', splitterSets{s}{2}, buildTimes(s), length(leaves));
    end
    timings.tree_build_avg = mean(buildTimes);
    timings.tree_build_max = max(buildTimes);
    fprintf('  Avg build time: %.3f s, Max: %.3f s\n', timings.tree_build_avg, timings.tree_build_max);
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 3: Epoch count consistency across all splitter combos
% =====================================================================
fprintf('\n--- Test 3: Epoch count consistency ---\n');
nTests = nTests + 1;
try
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    for s = 1:length(splitterSets)
        tree.buildTreeWithSplitters(splitterSets{s}{1});
        leaves = tree.leafNodes();
        leafSum = 0;
        for i = 1:length(leaves)
            leafSum = leafSum + leaves{i}.epochCount();
        end
        assert(leafSum == 1915, sprintf('Set %d: leaf sum %d != 1915', s, leafSum));
        assert(tree.epochCount() == 1915, sprintf('Set %d: root count %d != 1915', s, tree.epochCount()));
    end
    fprintf('  All %d splitter combos: root count = leaf sum = 1915\n', length(splitterSets));
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 4: Metadata completeness on every epoch
% =====================================================================
fprintf('\n--- Test 4: Metadata completeness ---\n');
nTests = nTests + 1;
try
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});
    allEps = tree.getAllEpochs(false);

    requiredFields = {'id', 'parameters', 'responses', 'cellInfo', 'groupInfo', 'blockInfo', ...
                      'expInfo', 'h5_file', 'isSelected', 'start_time', 'end_time'};
    requiredCellInfo = {'id', 'type', 'label'};
    requiredBlockInfo = {'id', 'protocol_name', 'protocol_id', 'start_time', 'end_time'};
    requiredGroupInfo = {'id', 'label', 'start_time', 'end_time'};
    % Only check params that ALL protocols share (not protocol-specific like preTime/tailTime)
    requiredParams = {'sampleRate'};

    nMissing = 0;
    for i = 1:length(allEps)
        ep = allEps{i};
        for f = 1:length(requiredFields)
            if ~isfield(ep, requiredFields{f})
                fprintf('  Epoch %d missing field: %s\n', i, requiredFields{f});
                nMissing = nMissing + 1;
            end
        end
        for f = 1:length(requiredCellInfo)
            if ~isfield(ep.cellInfo, requiredCellInfo{f})
                fprintf('  Epoch %d missing cellInfo.%s\n', i, requiredCellInfo{f});
                nMissing = nMissing + 1;
            end
        end
        for f = 1:length(requiredBlockInfo)
            if ~isfield(ep.blockInfo, requiredBlockInfo{f})
                fprintf('  Epoch %d missing blockInfo.%s\n', i, requiredBlockInfo{f});
                nMissing = nMissing + 1;
            end
        end
        for f = 1:length(requiredGroupInfo)
            if ~isfield(ep.groupInfo, requiredGroupInfo{f})
                fprintf('  Epoch %d missing groupInfo.%s\n', i, requiredGroupInfo{f});
                nMissing = nMissing + 1;
            end
        end
        params = ep.parameters;
        for f = 1:length(requiredParams)
            if ~isfield(params, requiredParams{f})
                fprintf('  Epoch %d missing parameters.%s\n', i, requiredParams{f});
                nMissing = nMissing + 1;
            end
        end
    end
    assert(nMissing == 0, sprintf('%d missing fields found', nMissing));
    fprintf('  All %d epochs have complete metadata (%d fields checked per epoch)\n', ...
        length(allEps), length(requiredFields)+length(requiredCellInfo)+length(requiredBlockInfo)+length(requiredGroupInfo)+length(requiredParams));
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 5: Date/time conversion and ordering
% =====================================================================
fprintf('\n--- Test 5: Date/time conversion and ordering ---\n');
nTests = nTests + 1;
try
    allEps = tree.getAllEpochs(false);

    % Convert all epoch start times
    startTimes = zeros(length(allEps), 1);
    for i = 1:length(allEps)
        startTimes(i) = double(allEps{i}.start_time);
    end

    % Convert .NET ticks to datetime
    days = startTimes / (1e7 * 86400);
    dts = datetime(days, 'ConvertFrom', 'datenum') - calyears(1) + caldays(1);

    % All should be in reasonable range
    yrs = year(dts);
    assert(all(yrs >= 2020 & yrs <= 2030), 'Some epochs have unreasonable dates');

    % Check block-level dates are available
    ep1 = allEps{1};
    blockStart = datetime(double(ep1.blockInfo.start_time)/(1e7*86400), 'ConvertFrom', 'datenum') - calyears(1) + caldays(1);
    blockEnd = datetime(double(ep1.blockInfo.end_time)/(1e7*86400), 'ConvertFrom', 'datenum') - calyears(1) + caldays(1);
    assert(blockEnd > blockStart, 'Block end should be after start');

    groupStart = datetime(double(ep1.groupInfo.start_time)/(1e7*86400), 'ConvertFrom', 'datenum') - calyears(1) + caldays(1);
    groupEnd = datetime(double(ep1.groupInfo.end_time)/(1e7*86400), 'ConvertFrom', 'datenum') - calyears(1) + caldays(1);
    assert(groupEnd > groupStart, 'Group end should be after start');

    % Epoch start should be within block range
    epStart = datetime(double(ep1.start_time)/(1e7*86400), 'ConvertFrom', 'datenum') - calyears(1) + caldays(1);
    assert(epStart >= blockStart && epStart <= blockEnd, 'Epoch should be within block time range');

    fprintf('  Experiment date range: %s to %s\n', char(min(dts)), char(max(dts)));
    fprintf('  Duration: %.1f hours\n', hours(max(dts) - min(dts)));
    fprintf('  Block time range: %s to %s\n', char(blockStart), char(blockEnd));
    fprintf('  Group time range: %s to %s\n', char(groupStart), char(groupEnd));
    fprintf('  Epoch within block range: OK\n');
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 6: Selection management - bulk operations
% =====================================================================
fprintf('\n--- Test 6: Selection management ---\n');
nTests = nTests + 1;
try
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});

    % All start selected
    assert(length(tree.getAllEpochs(true)) == 1915, 'Should start all selected');

    % Deselect entire cell type
    cellNode = tree.childAt(1);
    cellCount = cellNode.epochCount();
    tic;
    cellNode.setSelected(false, true);
    timings.deselect = toc;
    selCount = length(tree.getAllEpochs(true));
    assert(selCount == 1915 - cellCount, sprintf('After deselect: expected %d, got %d', 1915-cellCount, selCount));

    % Re-select
    tic;
    cellNode.setSelected(true, true);
    timings.reselect = toc;
    assert(length(tree.getAllEpochs(true)) == 1915, 'Re-select failed');

    % Deselect individual leaf, check parent counts
    protNode = cellNode.childAt(1);
    protCount = protNode.epochCount();
    protNode.setSelected(false, true);
    parentSel = length(cellNode.getAllEpochs(true));
    assert(parentSel == cellCount - protCount, 'Parent selected count wrong');

    % Re-select all
    tree.childAt(1).setSelected(true, true);
    assert(length(tree.getAllEpochs(true)) == 1915, 'Final re-select failed');

    fprintf('  Deselect %d epochs: %.3f s\n', cellCount, timings.deselect);
    fprintf('  Reselect %d epochs: %.3f s\n', cellCount, timings.reselect);
    fprintf('  Parent count propagation: correct\n');
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 7: H5 data extraction - all leaves with timing
% =====================================================================
fprintf('\n--- Test 7: H5 data extraction from all leaves ---\n');
nTests = nTests + 1;
try
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
    leaves = tree.leafNodes();

    totalTraces = 0;
    totalSamples = 0;
    extractTimes = zeros(length(leaves), 1);
    leafInfo = {};

    for i = 1:length(leaves)
        leaf = leaves{i};
        tic;
        [leafData, epochs, fs] = epicTreeTools.getSelectedData(leaf, 'Amp1');
        extractTimes(i) = toc;

        assert(~isempty(leafData), sprintf('Leaf %d: empty data', i));
        assert(size(leafData,1) == leaf.epochCount(), sprintf('Leaf %d: count mismatch', i));
        assert(fs > 0, sprintf('Leaf %d: invalid sample rate', i));

        nTraces = size(leafData, 1);
        nSamples = size(leafData, 2);
        totalTraces = totalTraces + nTraces;
        totalSamples = totalSamples + nTraces * nSamples;

        % Build path
        node = leaf;
        path = char(string(leaf.splitValue));
        while ~isempty(node.parent) && ~isempty(node.parent.splitValue)
            node = node.parent;
            path = [char(string(node.splitValue)), ' / ', path];
        end

        leafInfo{end+1} = struct('path', path, 'traces', nTraces, 'samples', nSamples, ...
            'fs', double(fs), 'time', extractTimes(i), ...
            'ms_per_epoch', extractTimes(i)/nTraces*1000); %#ok<AGROW>
    end

    assert(totalTraces == 1915, sprintf('Expected 1915 traces, got %d', totalTraces));
    timings.extract_total = sum(extractTimes);
    timings.extract_per_epoch = timings.extract_total / totalTraces * 1000;

    for i = 1:length(leafInfo)
        li = leafInfo{i};
        fprintf('  %-40s %4d x %5d  fs=%5.0f  %.3fs (%.1f ms/ep)\n', ...
            li.path, li.traces, li.samples, li.fs, li.time, li.ms_per_epoch);
    end
    fprintf('  ---\n');
    fprintf('  Total: %d traces, %.1f M samples\n', totalTraces, totalSamples/1e6);
    fprintf('  Total extraction: %.3f s (%.1f ms/epoch avg)\n', timings.extract_total, timings.extract_per_epoch);
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 8: Scientific analysis pattern - mean, std, peak, SNR
% =====================================================================
fprintf('\n--- Test 8: Scientific analysis patterns ---\n');
nTests = nTests + 1;
try
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
    leaves = tree.leafNodes();

    for i = 1:length(leaves)
        leaf = leaves{i};
        [leafData, ~, fs] = epicTreeTools.getSelectedData(leaf, 'Amp1');
        leafData = double(leafData);
        fs = double(fs);

        % Compute standard analysis metrics
        meanTrace = mean(leafData, 1);
        stdTrace = std(leafData, 0, 1);
        peakResp = max(abs(meanTrace));
        baselineWindow = 1:round(0.1 * fs); % first 100ms
        if ~isempty(baselineWindow)
            baseline = mean(meanTrace(baselineWindow));
            baselineNoise = std(meanTrace(baselineWindow));
        else
            baseline = 0;
            baselineNoise = 1;
        end
        snr = peakResp / max(baselineNoise, eps);

        % Verify no NaN/Inf
        assert(~any(isnan(meanTrace)), sprintf('Leaf %d: NaN in mean', i));
        assert(~any(isinf(meanTrace)), sprintf('Leaf %d: Inf in mean', i));
        assert(peakResp > 0, sprintf('Leaf %d: zero peak', i));
        assert(isfinite(snr), sprintf('Leaf %d: non-finite SNR', i));

        % Store results at node
        results = struct('meanTrace', meanTrace, 'stdTrace', stdTrace, ...
            'peakResponse', peakResp, 'baseline', baseline, 'snr', snr, ...
            'nEpochs', size(leafData,1), 'fs', fs);
        leaf.putCustom('analysisResults', results);

        node = leaf;
        path = char(string(leaf.splitValue));
        while ~isempty(node.parent) && ~isempty(node.parent.splitValue)
            node = node.parent;
            path = [char(string(node.splitValue)), ' / ', path];
        end
        fprintf('  %-40s peak=%.1f pA  baseline=%.1f pA  SNR=%.1f  n=%d\n', ...
            path, peakResp, baseline, snr, size(leafData,1));
    end

    % Verify putCustom/getCustom round-trip
    for i = 1:length(leaves)
        r = leaves{i}.getCustom('analysisResults');
        assert(~isempty(r), sprintf('Leaf %d: getCustom failed', i));
        assert(r.nEpochs == leaves{i}.epochCount(), sprintf('Leaf %d: stored count mismatch', i));
    end
    fprintf('  putCustom/getCustom round-trip: OK\n');
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 9: Tree rebuild preserves data integrity
% =====================================================================
fprintf('\n--- Test 9: Tree rebuild preserves data integrity ---\n');
nTests = nTests + 1;
try
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
    ssNode = tree.childAt(1).childBySplitValue('SingleSpot');
    [data1, ~, fs1] = epicTreeTools.getSelectedData(ssNode, 'Amp1');

    % Rebuild with totally different splitters
    tree.buildTreeWithSplitters({'cellInfo.label', 'parameters.stimTime'});

    % Rebuild back to original
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
    ssNode2 = tree.childAt(1).childBySplitValue('SingleSpot');
    [data2, ~, fs2] = epicTreeTools.getSelectedData(ssNode2, 'Amp1');

    % Data should be identical
    assert(isequal(size(data1), size(data2)), 'Size changed after rebuild');
    assert(fs1 == fs2, 'Sample rate changed after rebuild');
    maxDiff = max(abs(double(data1(:)) - double(data2(:))));
    assert(maxDiff == 0, sprintf('Data changed after rebuild, max diff=%.6f', maxDiff));

    fprintf('  Rebuild 3x: data identical (max diff = 0)\n');
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 10: Navigation - parent/child/leaf consistency
% =====================================================================
fprintf('\n--- Test 10: Navigation consistency ---\n');
nTests = nTests + 1;
try
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol, 'parameters.preTime'});

    % Every leaf should trace back to root
    leaves = tree.leafNodes();
    for i = 1:length(leaves)
        node = leaves{i};
        depth = 0;
        while ~isempty(node.parent)
            parentNode = node.parent;
            found = false;
            for j = 1:parentNode.childrenLength()
                if parentNode.childAt(j) == node
                    found = true;
                    break;
                end
            end
            assert(found, sprintf('Leaf %d: child not found in parent', i));
            node = parentNode;
            depth = depth + 1;
        end
        assert(depth == 3, sprintf('Leaf %d: expected depth 3, got %d', i, depth));
        assert(node.epochCount() == 1915, sprintf('Leaf %d: root count wrong', i));
    end

    % childBySplitValue should match childAt
    for i = 1:tree.childrenLength()
        child = tree.childAt(i);
        found = tree.childBySplitValue(child.splitValue);
        assert(~isempty(found), sprintf('childBySplitValue failed for child %d', i));
        assert(found.epochCount() == child.epochCount(), 'childBySplitValue count mismatch');
    end

    fprintf('  %d leaves, all trace to root at depth 3\n', length(leaves));
    fprintf('  Parent-child bidirectional links: consistent\n');
    fprintf('  childBySplitValue matches childAt: OK\n');
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 11: getSelectedData respects selection
% =====================================================================
fprintf('\n--- Test 11: getSelectedData respects selection ---\n');
nTests = nTests + 1;
try
    % Use a small leaf node to keep extraction fast
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
    cellNode = tree.childAt(1);
    ssNode = cellNode.childBySplitValue('SingleSpot');
    fullCount = ssNode.epochCount();
    assert(fullCount >= 2, 'Need at least 2 epochs for this test');

    % Extract all
    [dataAll, ~, ~] = epicTreeTools.getSelectedData(ssNode, 'Amp1');
    assert(size(dataAll,1) == fullCount, 'Full extraction count wrong');

    % Deselect via node method (setSelected propagates to actual epochs)
    ssNode.setSelected(false, true);
    [dataNone, ~, ~] = epicTreeTools.getSelectedData(ssNode, 'Amp1');
    assert(isempty(dataNone), sprintf('Expected 0 after deselect, got %d', size(dataNone,1)));

    % Re-select all
    ssNode.setSelected(true, true);
    [dataResel, ~, ~] = epicTreeTools.getSelectedData(ssNode, 'Amp1');
    assert(size(dataResel,1) == fullCount, 'Re-select full count wrong');

    fprintf('  Full: %d epochs -> %d traces\n', fullCount, size(dataAll,1));
    fprintf('  All deselected: 0 traces\n');
    fprintf('  Re-selected: %d traces\n', size(dataResel,1));
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 12: Split on every metadata key path
% =====================================================================
fprintf('\n--- Test 12: Split on every metadata key path ---\n');
nTests = nTests + 1;
try
    % Only use key paths that exist on ALL epochs (universal fields)
    % Protocol-specific params (preTime, spotIntensity, etc.) don't exist on all protocols
    keyPaths = {
        'cellInfo.type', 'cellInfo.label', 'cellInfo.id', ...
        'blockInfo.protocol_name', 'blockInfo.protocol_id', ...
        'groupInfo.label', ...
        'parameters.sampleRate', 'parameters.numberOfAverages', ...
        'parameters.amp', ...
        'expInfo.exp_name'
    };

    for k = 1:length(keyPaths)
        kp = keyPaths{k};
        tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
        tree.buildTreeWithSplitters({kp});
        nChildren = tree.childrenLength();
        assert(nChildren > 0, sprintf('Key %s produced 0 children', kp));
        assert(tree.epochCount() == 1915, sprintf('Key %s: epoch count wrong', kp));

        vals = {};
        for c = 1:nChildren
            vals{end+1} = char(string(tree.childAt(c).splitValue)); %#ok<AGROW>
        end
        fprintf('  %-35s -> %d groups: %s\n', kp, nChildren, strjoin(vals, ', '));
    end
    fprintf('  All %d key paths produce valid splits\n', length(keyPaths));
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 12b: Protocol-specific parameter splits (only on matching nodes)
% =====================================================================
fprintf('\n--- Test 12b: Protocol-specific parameter splits ---\n');
nTests = nTests + 1;
try
    % Build tree by protocol first, then split each protocol on its own params
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnProtocol});

    % Define protocol-specific parameters to test
    protoParams = {
        'SingleSpot',          {'parameters.preTime', 'parameters.stimTime', 'parameters.tailTime', 'parameters.spotIntensity', 'parameters.spotDiameter'};
        'ExpandingSpots',      {'parameters.preTime', 'parameters.stimTime', 'parameters.tailTime'};
        'SplitFieldCentering', {'parameters.preTime', 'parameters.stimTime', 'parameters.tailTime'};
        'VariableMeanNoise',   {'parameters.sampleRate', 'parameters.numberOfAverages'};
    };

    for p = 1:size(protoParams, 1)
        protoName = protoParams{p, 1};
        paramKeys = protoParams{p, 2};
        protoNode = tree.childBySplitValue(protoName);
        if isempty(protoNode), continue; end

        % Check that every epoch in this protocol has the expected params
        eps = protoNode.getAllEpochs(false);
        for k = 1:length(paramKeys)
            kp = paramKeys{k};
            nHave = 0;
            for e = 1:length(eps)
                val = epicTreeTools.getNestedValue(eps{e}, kp);
                if ~isempty(val), nHave = nHave + 1; end
            end
            assert(nHave == length(eps), ...
                sprintf('%s: only %d/%d epochs have %s', protoName, nHave, length(eps), kp));
        end
        fprintf('  %-25s %d epochs x %d params: all present\n', protoName, length(eps), length(paramKeys));
    end
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 13: Multi-level split + data extraction end-to-end
% =====================================================================
fprintf('\n--- Test 13: Multi-level split + extraction end-to-end ---\n');
nTests = nTests + 1;
try
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tic;
    tree.buildTreeWithSplitters({'cellInfo.label', 'blockInfo.protocol_name', 'parameters.preTime'});
    timings.build_3level = toc;

    leaves = tree.leafNodes();
    totalExtracted = 0;

    tic;
    for i = 1:length(leaves)
        leaf = leaves{i};
        [leafData, ~, fs] = epicTreeTools.getSelectedData(leaf, 'Amp1');
        assert(~isempty(leafData), sprintf('Leaf %d: empty', i));
        assert(size(leafData,1) == leaf.epochCount(), sprintf('Leaf %d: count mismatch', i));
        totalExtracted = totalExtracted + size(leafData, 1);
    end
    timings.extract_all_leaves = toc;
    timings.full_pipeline = timings.build_3level + timings.extract_all_leaves;

    assert(totalExtracted == 1915, sprintf('Total extracted %d != 1915', totalExtracted));
    fprintf('  3-level tree: %d leaves, %d epochs extracted\n', length(leaves), totalExtracted);
    fprintf('  Build: %.3f s, Extract: %.3f s, Total: %.3f s\n', ...
        timings.build_3level, timings.extract_all_leaves, timings.full_pipeline);
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 14: Waveform data quality checks
% =====================================================================
fprintf('\n--- Test 14: Waveform data quality ---\n');
nTests = nTests + 1;
try
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
    leaves = tree.leafNodes();

    for i = 1:length(leaves)
        leaf = leaves{i};
        [leafData, ~, fs] = epicTreeTools.getSelectedData(leaf, 'Amp1');
        leafData = double(leafData);
        fs = double(fs);

        % No NaN or Inf
        assert(~any(isnan(leafData(:))), sprintf('Leaf %d: NaN found', i));
        assert(~any(isinf(leafData(:))), sprintf('Leaf %d: Inf found', i));

        % Reasonable amplitudes (electrophysiology: < 10 nA = 10000 pA)
        maxAmp = max(abs(leafData(:)));
        assert(maxAmp < 10000, sprintf('Leaf %d: unreasonable amplitude %.1f pA', i, maxAmp));
        assert(maxAmp > 0, sprintf('Leaf %d: all zeros', i));

        % Reasonable sample rate
        assert(fs >= 1000 && fs <= 100000, sprintf('Leaf %d: unreasonable fs=%.0f', i, fs));

        % Sufficient samples
        assert(size(leafData,2) > 100, sprintf('Leaf %d: too few samples (%d)', i, size(leafData,2)));

        % Duration matches preTime + stimTime + tailTime
        epList = leaf.getAllEpochs(false);
        ep1 = epList{1};
        if isfield(ep1.parameters, 'preTime') && isfield(ep1.parameters, 'stimTime') && isfield(ep1.parameters, 'tailTime')
            expectedDur = (ep1.parameters.preTime + ep1.parameters.stimTime + ep1.parameters.tailTime) / 1000;
            actualDur = size(leafData, 2) / fs;
            assert(abs(expectedDur - actualDur) < 0.01, ...
                sprintf('Leaf %d: duration mismatch (expected %.3f, got %.3f s)', i, expectedDur, actualDur));
        end

        node = leaf;
        path = char(string(leaf.splitValue));
        while ~isempty(node.parent) && ~isempty(node.parent.splitValue)
            node = node.parent;
            path = [char(string(node.splitValue)), ' / ', path];
        end
        fprintf('  %-40s max=%.1f pA  dur=%.0f ms  fs=%.0f  [OK]\n', ...
            path, maxAmp, size(leafData,2)/fs*1000, fs);
    end
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  TEST 15: Rapid tree rebuild benchmark
% =====================================================================
fprintf('\n--- Test 15: Rapid tree rebuild benchmark ---\n');
nTests = nTests + 1;
try
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    nRebuilds = 10;
    tic;
    for r = 1:nRebuilds
        tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
        tree.buildTreeWithSplitters({'cellInfo.label', 'parameters.stimTime'});
    end
    timings.rebuild_20x = toc;
    timings.rebuild_avg = timings.rebuild_20x / (nRebuilds * 2);

    fprintf('  %d rebuilds in %.3f s (%.1f ms/rebuild avg)\n', ...
        nRebuilds*2, timings.rebuild_20x, timings.rebuild_avg*1000);
    fprintf('  [PASS]\n');
    nPass = nPass + 1;
catch ME
    fprintf('  [FAIL] %s\n', ME.message);
    nFail = nFail + 1;
end

% =====================================================================
%  SUMMARY
% =====================================================================
fprintf('\n============================================================\n');
fprintf('  TEST SUMMARY: %d/%d PASSED', nPass, nTests);
if nFail > 0
    fprintf(', %d FAILED', nFail);
end
fprintf('\n============================================================\n');

fprintf('\n  PERFORMANCE BENCHMARKS:\n');
fprintf('  %-40s %.3f s\n', 'Data load (1915 epochs):', timings.data_load);
fprintf('  %-40s %.3f s\n', 'Tree build (avg):', timings.tree_build_avg);
fprintf('  %-40s %.1f ms\n', 'Tree rebuild (avg):', timings.rebuild_avg*1000);
fprintf('  %-40s %.3f s\n', 'H5 extraction (1915 epochs):', timings.extract_total);
fprintf('  %-40s %.1f ms\n', 'Per-epoch H5 read:', timings.extract_per_epoch);
fprintf('  %-40s %.3f s\n', 'Full pipeline (build+extract all):', timings.full_pipeline);
fprintf('  %-40s %.3f s\n', 'Select/deselect (bulk):', timings.deselect + timings.reselect);
fprintf('\n============================================================\n');
